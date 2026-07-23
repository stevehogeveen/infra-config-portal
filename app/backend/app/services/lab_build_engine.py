from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from sqlalchemy.orm import Session

from app.providers.redaction import redact_sensitive
from app.services.control_actions import REPO_ROOT
from app.services.ilo_access_settings import IloAccessSettingsError, read_ilo_access_settings
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.lab_profiles import (
    active_lab_profile_context,
    lab_profile_context_fingerprint,
)
from app.services.path_utils import display_path, glob_paths
from app.services.status_source import DEFAULT_STALE_AFTER_SECONDS
from app.services.workflow_action_run_store import (
    latest_workflow_action_run_trace,
    workflow_action_run_trace,
)
from app.services.workflow_action_runner import run_workflow_action

BuildStepStatus = Literal[
    "not_started",
    "preflight",
    "ready",
    "running",
    "waiting",
    "succeeded",
    "warning",
    "failed",
    "skipped",
    "blocked",
]
BuildRunStatus = Literal["planned", "running", "waiting", "completed", "warning", "failed"]
SAFE_AUTO_RUN_MODES = {"read_only", "report_only"}
SUCCESS_STATUSES = {"succeeded", "warning", "skipped"}
TERMINAL_STEP_STATUSES = SUCCESS_STATUSES | {"failed", "blocked"}
RUN_LOCK_TIMEOUT_SECONDS = 5.0
RUN_LEASE_SECONDS = 30 * 60
EVIDENCE_CLAIMS_FILENAME = "evidence-claims.json"
LAB_BUILD_RUN_DIR = Path(
    os.environ.get(
        "LAB_BUILD_RUN_DIR",
        REPO_ROOT / "artifacts" / "codex-runs" / "lab-build-runs",
    )
)


class LabBuildRunNotFoundError(LookupError):
    pass


class LabBuildRunStateError(ValueError):
    pass


class LabBuildStepNotFoundError(LookupError):
    pass


class LabBuildStepRetryError(ValueError):
    pass


class LabBuildPlanError(ValueError):
    pass


@dataclass(frozen=True)
class BuildStepDefinition:
    step_id: str
    label: str
    description: str
    action_id: str
    mode: str
    depends_on: tuple[str, ...]
    provides: tuple[str, ...]
    operator_path: str
    suggested_action: str
    rationale: str | None = None
    can_retry: bool = True
    optional: bool = False
    preflight_blocker: str | None = None


@dataclass(frozen=True)
class BuildStartEvidenceRequirement:
    action_id: str
    accepted_evidence_statuses: frozenset[str]
    blocker: str


BUILD_START_EVIDENCE_REQUIREMENTS = (
    BuildStartEvidenceRequirement(
        "cisco.current-intent-diff",
        frozenset({"ready"}),
        (
            "Complete the switch's initial setup, then run the Cisco current-to-intent "
            "read-only check with no remaining drift before starting the ESXi build."
        ),
    ),
    BuildStartEvidenceRequirement(
        "ilo.reachability",
        frozenset({"ok"}),
        (
            "Complete iLO first contact, then run Check this iLO IP for the current "
            "access address before starting the ESXi build."
        ),
    ),
    BuildStartEvidenceRequirement(
        "raid.validate",
        frozenset({"succeeded"}),
        (
            "Complete local-storage initial setup, then run RAID validation against "
            "the saved layout before starting the ESXi build."
        ),
    ),
)


ActionRunner = Callable[[str, Session | None, dict[str, Any] | None], dict[str, Any]]


def get_lab_build_plan(
    *,
    context: dict[str, Any] | None = None,
    definitions: tuple[BuildStepDefinition, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = context or active_lab_profile_context()
    using_default_definitions = definitions is None
    resolved_definitions = (
        _kit_step_definitions(resolved_context)
        if using_default_definitions
        else definitions
    )
    ordered = _ordered_definitions(resolved_definitions)
    profile = _active_profile(resolved_context)
    blockers = _plan_blockers(profile, ordered)
    if using_default_definitions:
        blockers.extend(_build_start_evidence_blockers(resolved_context))
    return {
        "kit_id": str(profile.get("id") or "runtime-profile"),
        "kit_name": str(profile.get("name") or "Current lab"),
        "deployment_mode": _deployment_mode(resolved_context),
        "status": "blocked" if blockers else "ready",
        "headline": (
            "Resolve the open item before starting this build."
            if blockers
            else "This lab is ready to follow one ordered build plan."
        ),
        "supporting_message": (
            blockers[0]
            if blockers
            else f"{len(ordered)} steps will run in dependency order and pause at guarded changes."
        ),
        "blockers": blockers,
        "steps": [_planned_step(index, item) for index, item in enumerate(ordered, start=1)],
        "primary_action": "Start Build",
    }


def start_lab_build(
    session: Session | None = None,
    *,
    context: dict[str, Any] | None = None,
    definitions: tuple[BuildStepDefinition, ...] | None = None,
    action_runner: ActionRunner = run_workflow_action,
) -> dict[str, Any]:
    resolved_context = context or active_lab_profile_context()
    plan = get_lab_build_plan(context=resolved_context, definitions=definitions)
    if plan["blockers"]:
        raise LabBuildPlanError(plan["blockers"][0])

    now = _now()
    run = {
        "run_id": f"lab-build:{uuid.uuid4().hex[:12]}",
        "revision": 0,
        "kit_id": plan["kit_id"],
        "kit_name": plan["kit_name"],
        "profile_fingerprint": _profile_fingerprint(resolved_context),
        "deployment_mode": plan["deployment_mode"],
        "status": "planned",
        "headline": "Build plan created.",
        "operator_message": "The lab build is ready to start.",
        "suggested_action": "Start the build.",
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "current_step_id": None,
        "steps": plan["steps"],
        "report_artifact": None,
    }
    _save_run(run)
    return _advance_run(run, session=session, action_runner=action_runner)


def resume_lab_build(
    run_id: str,
    session: Session | None = None,
    *,
    run_revision: int,
    action_run_id: str | None = None,
    waiting_nonce: str | None = None,
    context: dict[str, Any] | None = None,
    action_runner: ActionRunner = run_workflow_action,
) -> dict[str, Any]:
    with _run_lock(run_id):
        run = _load_run(run_id)
        _assert_revision(run, run_revision)
        _assert_profile_unchanged(run, context or active_lab_profile_context())
        if run.get("status") != "waiting":
            raise LabBuildRunStateError("Only a waiting build can be resumed.")
        waiting_step = _current_step(run)
        if not waiting_step:
            raise LabBuildRunStateError("The waiting build step could not be found.")
        if (
            waiting_step.get("status") == "not_started"
            and waiting_step.get("action_mode") in SAFE_AUTO_RUN_MODES
        ):
            return _advance_run(run, session=session, action_runner=action_runner)
        if waiting_step.get("status") != "waiting":
            raise LabBuildRunStateError("The waiting build step could not be found.")
        if not action_run_id or not waiting_nonce:
            raise LabBuildRunStateError("Select the completed guarded action before resuming this build.")
        if waiting_step.get("waiting_nonce") != waiting_nonce:
            raise LabBuildRunStateError(
                "This build changed after the approval screen was opened. Refresh and try again."
            )

        trace = workflow_action_run_trace(str(waiting_step["action_id"]), action_run_id)
        if (
            not trace
            or not _trace_is_new_enough(trace, waiting_step.get("started_at"))
            or not _trace_matches_run(trace, run)
        ):
            raise LabBuildRunStateError(
                "The selected guarded action evidence is not valid for this build step."
            )
        _claim_guarded_evidence(trace, run, waiting_step)
        _apply_action_result(waiting_step, trace)
        waiting_step["waiting_nonce"] = None
        run["updated_at"] = _now()
        _save_run(run)
        if waiting_step["status"] in {"failed", "blocked"}:
            return _stop_run(run, waiting_step, "failed")
        if waiting_step["status"] == "waiting":
            return _stop_run(run, waiting_step, "waiting")
        return _advance_run(run, session=session, action_runner=action_runner)


def retry_lab_build_step(
    run_id: str,
    step_id: str,
    session: Session | None = None,
    *,
    action_runner: ActionRunner = run_workflow_action,
) -> dict[str, Any]:
    with _run_lock(run_id):
        run = _load_run(run_id)
        steps = _steps(run)
        step_index = next((index for index, step in enumerate(steps) if step["step_id"] == step_id), None)
        if step_index is None:
            raise LabBuildStepNotFoundError(step_id)
        step = steps[step_index]
        if step.get("summary") == "dependency_not_ready":
            raise LabBuildStepRetryError("Retry the failed owning step instead of a dependent step.")
        if not step.get("can_retry"):
            raise LabBuildStepRetryError(f"{step['label']} cannot be retried from this build.")
        if step["status"] not in {"succeeded", "warning", "failed", "blocked"}:
            raise LabBuildStepRetryError(f"{step['label']} is not in a retryable state.")

        _reset_step(step)
        provided = set(_string_list(step.get("provides")))
        for downstream in steps[step_index + 1 :]:
            if provided.intersection(_string_list(downstream.get("depends_on"))):
                _reset_step(downstream)
                provided.update(_string_list(downstream.get("provides")))

        run.update(
            {
                "status": "waiting",
                "headline": f"{step['label']} is ready to retry.",
                "operator_message": "Downstream steps returned to not ready until this check finishes again.",
                "suggested_action": "Resume the build to run the check again.",
                "current_step_id": step_id,
                "finished_at": None,
                "updated_at": _now(),
                "report_artifact": None,
            }
        )
        _save_run(run)
        return _refresh_run_summary(run)


def get_lab_build_run(run_id: str) -> dict[str, Any]:
    with _run_lock(run_id):
        payload = _load_run(run_id)
        if _reconcile_stale_run(payload):
            _save_run(payload)
        return _refresh_run_summary(payload)


def get_latest_lab_build_run(kit_id: str | None = None) -> dict[str, Any] | None:
    runs = [read_json_object(path) for path in glob_paths(_run_dir(), "*.json")]
    valid = [
        run
        for run in runs
        if run.get("run_id") and (kit_id is None or str(run.get("kit_id")) == kit_id)
    ]
    if not valid:
        return None
    latest = max(valid, key=lambda run: str(run.get("updated_at") or ""))
    return get_lab_build_run(str(latest["run_id"]))


def _kit_step_definitions(context: dict[str, Any]) -> tuple[BuildStepDefinition, ...]:
    features = context.get("enabled_features") if isinstance(context.get("enabled_features"), dict) else {}
    netapp_enabled = features.get("netapp_enabled") is not False
    vcenter_enabled = netapp_enabled and features.get("vcenter_enabled") is True
    storage_protocol = str(features.get("storage_protocol") or "nfs").lower()

    definitions = [
        BuildStepDefinition(
            "esxi-installer-boot",
            "Boot the ESXi installer",
            (
                "Run the guarded server power/reset stage that requests a boot from previously prepared "
                "ESXi installer media. This stage does not install or configure ESXi."
            ),
            "esxi.rebuild-install",
            "destructive",
            (),
            ("esxi-installer-boot-requested",),
            "/virtualization",
            (
                "Open Virtualization Setup, review the installer-media and boot prerequisites, approve "
                "only the guarded installer boot, then resume this build."
            ),
            rationale=(
                "The existing guarded action requests installer boot through iLO; it is not proof that "
                "ESXi was installed or configured."
            ),
            can_retry=False,
        ),
        BuildStepDefinition(
            "hypervisor",
            "Validate ESXi management",
            (
                "After the operator completes ESXi installation and initial host configuration, confirm "
                "target-bound management evidence before treating the compute host as ready."
            ),
            "esxi.management-validation",
            "read_only",
            ("esxi-installer-boot-requested",),
            ("hypervisor",),
            "/virtualization",
            (
                "Complete the ESXi installer and initial management configuration, then retry this "
                "read-only validation."
            ),
            rationale="An installer boot request alone never establishes a usable ESXi host.",
        ),
    ]

    completion_dependencies = ["hypervisor"]
    if netapp_enabled:
        definitions.extend(
            [
                BuildStepDefinition(
                    "storage-system",
                    "Configure shared storage",
                    "Apply the saved storage system identity, network, and service plan.",
                    "netapp.setup-apply",
                    "write",
                    ("hypervisor",),
                    ("storage-system",),
                    "/storage",
                    "Open Storage Setup, approve the guarded setup, then resume this build.",
                ),
                BuildStepDefinition(
                    "storage-service",
                    f"Configure {storage_protocol.upper()} storage",
                    "Create the selected shared-storage service for this kit.",
                    "netapp.iscsi-setup-apply" if storage_protocol == "iscsi" else "netapp.nfs-setup-apply",
                    "write",
                    ("storage-system",),
                    ("shared-storage",),
                    "/storage",
                    f"Open Storage Setup, approve the guarded {storage_protocol.upper()} setup, then resume this build.",
                ),
                BuildStepDefinition(
                    "datastore",
                    (
                        "Confirm the iSCSI datastore is attached"
                        if storage_protocol == "iscsi"
                        else "Connect shared storage to the compute host"
                    ),
                    (
                        "Check that the iSCSI datastore is attached to the compute host. "
                        "Attaching it is a manual step in Virtualization Setup; this app "
                        "validates the connection but does not apply it."
                        if storage_protocol == "iscsi"
                        else "Make the selected shared storage available to the compute host."
                    ),
                    "esxi.iscsi-datastore-validate" if storage_protocol == "iscsi" else "esxi.netapp-datastore-apply",
                    "read_only" if storage_protocol == "iscsi" else "write",
                    ("hypervisor", "shared-storage"),
                    ("datastore",),
                    "/virtualization",
                    (
                        "Attach the iSCSI datastore in Virtualization Setup yourself, then retry. "
                        "This app validates the connection but does not apply it."
                        if storage_protocol == "iscsi"
                        else "Open Virtualization Setup, finish the storage connection, then retry."
                    ),
                    rationale="Shared storage must be ready before the compute host can use it.",
                ),
            ]
        )
        completion_dependencies = ["datastore"]

    if vcenter_enabled:
        definitions.extend(
            [
                BuildStepDefinition(
                    "vcenter",
                    "Deploy central management",
                    "Deploy the saved central management appliance to the ready datastore.",
                    "vcenter.install-apply",
                    "write",
                    ("datastore",),
                    ("vcenter",),
                    "/virtualization",
                    "Open Virtualization Setup, approve the deployment, then resume this build.",
                ),
                BuildStepDefinition(
                    "vcenter-attach",
                    "Add the compute host",
                    "Add the compute host to central management after both are ready.",
                    "vcenter.attach-esxi-apply",
                    "write",
                    ("hypervisor", "vcenter"),
                    ("managed-hypervisor",),
                    "/virtualization",
                    "Open Virtualization Setup, approve the host attachment, then resume this build.",
                ),
            ]
        )
        completion_dependencies.append("managed-hypervisor")

    definitions.append(
        BuildStepDefinition(
            "handoff",
            "Verify and prepare handoff",
            "Run the final checks and prepare the build summary.",
            "full-lab.validation",
            "read_only",
            tuple(completion_dependencies),
            ("handoff-ready",),
            "/validation",
            "Review the failed check, correct it, then retry verification.",
        )
    )
    return tuple(definitions)


def _ordered_definitions(definitions: tuple[BuildStepDefinition, ...]) -> list[BuildStepDefinition]:
    provided_by: dict[str, str] = {}
    definition_by_id = {item.step_id: item for item in definitions}
    if len(definition_by_id) != len(definitions):
        raise LabBuildPlanError("Build step ids must be unique.")
    for item in definitions:
        for capability in item.provides:
            if capability in provided_by:
                raise LabBuildPlanError(f"Capability {capability} has more than one owner.")
            provided_by[capability] = item.step_id

    missing = sorted(
        {
            capability
            for item in definitions
            for capability in item.depends_on
            if capability not in provided_by
        }
    )
    if missing:
        raise LabBuildPlanError(f"Build plan is missing capabilities: {', '.join(missing)}")

    remaining = list(definitions)
    ordered: list[BuildStepDefinition] = []
    ready_capabilities: set[str] = set()
    while remaining:
        ready = [item for item in remaining if set(item.depends_on).issubset(ready_capabilities)]
        if not ready:
            raise LabBuildPlanError("Build plan contains a dependency cycle.")
        for item in ready:
            ordered.append(item)
            ready_capabilities.update(item.provides)
            remaining.remove(item)
    return ordered


def _planned_step(index: int, definition: BuildStepDefinition) -> dict[str, Any]:
    return {
        "step_id": definition.step_id,
        "order": index,
        "label": definition.label,
        "description": definition.description,
        "status": "not_started",
        "summary": "not_started",
        "operator_message": "Waiting for the build to start.",
        "technical_details": "",
        "suggested_action": definition.suggested_action,
        "can_retry": definition.can_retry and definition.mode in SAFE_AUTO_RUN_MODES,
        "optional": definition.optional,
        "depends_on": list(definition.depends_on),
        "provides": list(definition.provides),
        "action_id": definition.action_id,
        "action_mode": definition.mode,
        "operator_path": definition.operator_path,
        "rationale": definition.rationale,
        "started_at": None,
        "finished_at": None,
        "action_run_id": None,
        "waiting_nonce": None,
        "lease_expires_at": None,
    }


def _advance_run(
    run: dict[str, Any],
    *,
    session: Session | None,
    action_runner: ActionRunner,
) -> dict[str, Any]:
    run.update(
        {
            "status": "running",
            "headline": "Building the lab.",
            "operator_message": "The next ready step is starting.",
            "suggested_action": "Keep this window open while the build continues.",
            "finished_at": None,
            "updated_at": _now(),
        }
    )
    _save_run(run)

    for step in _steps(run):
        if step["status"] in SUCCESS_STATUSES:
            continue
        blocker = _dependency_blocker(step, _steps(run))
        if blocker:
            step.update(
                {
                    **_dependency_block_update(blocker),
                    "finished_at": _now(),
                }
            )
            return _stop_run(run, step, "failed")

        run["current_step_id"] = step["step_id"]
        step.update(
            {
                "status": "preflight",
                "summary": "preflight",
                "operator_message": f"Checking whether {step['label'].lower()} can start.",
                "started_at": step.get("started_at") or _now(),
                "finished_at": None,
            }
        )
        run["updated_at"] = _now()
        _save_run(run)

        if step.get("action_mode") not in SAFE_AUTO_RUN_MODES:
            step.update(
                {
                    "status": "waiting",
                    "summary": "operator_approval_required",
                    "operator_message": f"Waiting for approval: {step['label']}.",
                    "technical_details": (
                        f"Action {step['action_id']} remains protected by its existing confirmation and safety gates."
                    ),
                    "waiting_nonce": uuid.uuid4().hex,
                    "lease_expires_at": None,
                }
            )
            return _stop_run(run, step, "waiting")

        step.update(
            {
                "status": "ready",
                "summary": "ready",
                "operator_message": f"{step['label']} is ready to run.",
            }
        )
        run["updated_at"] = _now()
        _save_run(run)
        step.update(
            {
                "status": "running",
                "summary": "running",
                "operator_message": f"{step['label']} is running.",
                "lease_expires_at": _lease_expiry(),
            }
        )
        run["updated_at"] = _now()
        _save_run(run)
        try:
            result = action_runner(str(step["action_id"]), session, None)
        except Exception as exc:
            result = {
                "status": "failed",
                "summary": "action_runner_error",
                "blockers": ["The build action stopped unexpectedly."],
                "warnings": [],
                "error_type": type(exc).__name__,
            }
        _apply_action_result(step, result)
        step["lease_expires_at"] = None
        run["updated_at"] = _now()
        _save_run(run)
        if step["status"] in {"failed", "blocked"}:
            return _stop_run(run, step, "failed")
        if step["status"] == "waiting":
            return _stop_run(run, step, "waiting")

    return _complete_run(run)


def _apply_action_result(step: dict[str, Any], result: dict[str, Any]) -> None:
    safe_result = redact_sensitive(result)
    if not isinstance(safe_result, dict):
        safe_result = {"status": "failed", "summary": "invalid_action_result"}
    raw_status = str(safe_result.get("status") or "failed").lower()
    blockers = _string_list(safe_result.get("blockers"))
    warnings = _string_list(safe_result.get("warnings"))
    if raw_status == "waiting":
        status: BuildStepStatus = "waiting"
        message = str(safe_result.get("operator_message") or f"Waiting on: {step['label'].lower()}.")
    elif blockers or raw_status == "blocked":
        status = "blocked"
        message = f"{step['label']} could not start."
    elif raw_status in {"completed", "succeeded", "success", "ready", "ok"}:
        status = "warning" if warnings else "succeeded"
        message = (
            f"{step['label']} finished with a warning."
            if warnings
            else f"{step['label']} completed."
        )
    elif raw_status == "skipped":
        if step.get("optional"):
            status = "skipped"
            message = f"{step['label']} is not required for this kit."
        else:
            status = "blocked"
            message = f"{step['label']} did not produce the required result."
            blockers = [*blockers, "A required build step was skipped."]
    else:
        status = "failed"
        message = f"{step['label']} failed."

    technical = {
        "status": raw_status,
        "summary": safe_result.get("summary"),
        "blockers": blockers,
        "warnings": warnings,
        "next_action": safe_result.get("next_action"),
        "error_type": safe_result.get("error_type"),
        "trace_artifact": safe_result.get("trace_artifact"),
        "report_artifacts": safe_result.get("report_artifacts"),
    }
    step.update(
        {
            "status": status,
            "summary": str(safe_result.get("summary") or raw_status),
            "operator_message": message,
            "technical_details": json.dumps(technical, indent=2, default=str),
            "suggested_action": step["suggested_action"],
            "can_retry": bool(step.get("can_retry")) and status != "waiting",
            "finished_at": None if status == "waiting" else _now(),
            "action_run_id": safe_result.get("run_id"),
        }
    )


def _trace_is_new_enough(trace: dict[str, Any], started_at: Any) -> bool:
    trace_time = _parse_datetime(trace.get("finished_at") or trace.get("started_at"))
    waiting_time = _parse_datetime(started_at)
    return bool(trace_time and waiting_time and trace_time >= waiting_time)


def _trace_matches_run(trace: dict[str, Any], run: dict[str, Any]) -> bool:
    return (
        str(trace.get("lab_profile_id") or "") == str(run.get("kit_id") or "")
        and str(trace.get("lab_profile_fingerprint") or "") == str(run.get("profile_fingerprint") or "")
    )


def _dependency_blocker(step: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    required = set(_string_list(step.get("depends_on")))
    ordered_steps = sorted(steps, key=lambda item: int(item.get("order") or 0))
    owned_capabilities: set[str] = set()
    for candidate in ordered_steps:
        for capability in _string_list(candidate.get("provides")):
            owned_capabilities.add(capability)
            if capability in required and candidate.get("status") not in SUCCESS_STATUSES:
                return {
                    "label": str(candidate.get("label") or capability.replace("-", " ")),
                    "step_id": str(candidate.get("step_id") or ""),
                    "capability": capability,
                }
    for capability in _string_list(step.get("depends_on")):
        if capability not in owned_capabilities:
            return {
                "label": capability.replace("-", " "),
                "step_id": None,
                "capability": capability,
            }
    return None


def _dependency_block_update(blocker: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "summary": "dependency_not_ready",
        "operator_message": f"Blocked by: {blocker['label']}.",
        "technical_details": json.dumps(
            {
                "blocked_by": {
                    "step_id": blocker.get("step_id"),
                    "capability": blocker["capability"],
                }
            },
            indent=2,
        ),
    }


def _stop_run(run: dict[str, Any], step: dict[str, Any], status: BuildRunStatus) -> dict[str, Any]:
    _mark_downstream_blocked(run, step)
    run.update(
        {
            "status": status,
            "headline": (
                f"Waiting at step {step['order']} of {len(_steps(run))}."
                if status == "waiting"
                else f"Build stopped at step {step['order']} of {len(_steps(run))}."
            ),
            "operator_message": step["operator_message"],
            "suggested_action": step["suggested_action"],
            "current_step_id": step["step_id"],
            "updated_at": _now(),
        }
    )
    _save_run(run)
    return _refresh_run_summary(run)


def _mark_downstream_blocked(run: dict[str, Any], current: dict[str, Any]) -> None:
    current_order = int(current.get("order") or 0)
    for step in _steps(run):
        if int(step.get("order") or 0) <= current_order or step.get("status") in SUCCESS_STATUSES:
            continue
        blocker = _dependency_blocker(step, _steps(run))
        if not blocker:
            continue
        step.update(
            {
                **_dependency_block_update(blocker),
                "finished_at": None,
            }
        )


def _complete_run(run: dict[str, Any]) -> dict[str, Any]:
    steps = _steps(run)
    warnings = sum(step["status"] == "warning" for step in steps)
    run.update(
        {
            "status": "warning" if warnings else "completed",
            "headline": "Lab build completed with a warning." if warnings else "Lab build completed.",
            "operator_message": (
                "Review the warning before handoff."
                if warnings
                else "The selected kit completed every build step."
            ),
            "suggested_action": "Review and export the completion report.",
            "current_step_id": None,
            "updated_at": _now(),
            "finished_at": _now(),
        }
    )
    try:
        run["report_artifact"] = _write_completion_report(run)
    except OSError:
        run.update(
            {
                "status": "warning",
                "headline": "Lab build completed, but its report is unavailable.",
                "operator_message": "The lab steps finished. Regenerate the handoff report from Details.",
                "suggested_action": "Open Details and regenerate the handoff report.",
                "report_artifact": None,
            }
        )
    _save_run(run)
    return _refresh_run_summary(run)


def _refresh_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    steps = _steps(run)
    completed = sum(step.get("status") in SUCCESS_STATUSES for step in steps)
    run["progress"] = {
        "completed": completed,
        "total": len(steps),
        "percent": round((completed / len(steps)) * 100) if steps else 0,
    }
    run["counts"] = {
        "completed": sum(step.get("status") in {"succeeded", "skipped"} for step in steps),
        "warnings": sum(step.get("status") == "warning" for step in steps),
        "failed": sum(step.get("status") in {"failed", "blocked"} for step in steps),
    }
    return run


def _write_completion_report(run: dict[str, Any]) -> str:
    path = _run_dir() / f"{_run_slug(str(run['run_id']))}.md"
    lines = [
        f"# Lab Build Report: {run['kit_name']}",
        "",
        f"- Run: `{run['run_id']}`",
        f"- Status: {run['status']}",
        f"- Started: {run['started_at']}",
        f"- Finished: {run['finished_at']}",
        "",
        "## Steps",
        "",
    ]
    for step in _steps(run):
        lines.extend(
            [
                f"### {step['order']}. {step['label']}",
                "",
                f"- Status: {step['status']}",
                f"- Result: {step['operator_message']}",
                f"- Next: {step['suggested_action']}",
                "",
            ]
        )
    write_text_value(path, "\n".join(lines))
    return display_path(path, REPO_ROOT)


def _plan_blockers(profile: dict[str, Any], definitions: list[BuildStepDefinition]) -> list[str]:
    blockers: list[str] = []
    address = profile.get("resolved_address_plan") or profile.get("address_plan") or {}
    if not str(profile.get("name") or "").strip():
        blockers.append("Select or create a kit before starting the build.")
    if not isinstance(address, dict) or not str(address.get("subnet") or "").strip():
        blockers.append("Add a site subnet to the selected kit before starting the build.")
    blockers.extend(item.preflight_blocker for item in definitions if item.preflight_blocker)
    return blockers


def _build_start_evidence_blockers(context: dict[str, Any]) -> list[str]:
    profile = _active_profile(context)
    profile_id = str(profile.get("id") or "runtime-profile")
    profile_fingerprint = lab_profile_context_fingerprint(context)
    now = datetime.now(UTC)
    blockers: list[str] = []
    evidence_times: dict[str, datetime] = {}

    for requirement in BUILD_START_EVIDENCE_REQUIREMENTS:
        trace = latest_workflow_action_run_trace(requirement.action_id)
        checked_at = _build_start_trace_time(trace)
        if not _build_start_trace_is_accepted(
            trace,
            requirement=requirement,
            profile_id=profile_id,
            profile_fingerprint=profile_fingerprint,
            checked_at=checked_at,
            now=now,
        ):
            blockers.append(requirement.blocker)
            continue
        assert checked_at is not None
        evidence_times[requirement.action_id] = checked_at

    try:
        ilo_access = read_ilo_access_settings()
    except IloAccessSettingsError:
        ilo_access = {}
    ilo_checked_at = _parse_datetime(ilo_access.get("last_probe_time"))
    ilo_access_ready = (
        bool(ilo_access.get("host"))
        and ilo_access.get("username_configured") is True
        and ilo_access.get("password_configured") is True
        and str(ilo_access.get("last_probe_status") or "").lower() == "ok"
        and ilo_access.get("last_probe_target_matches_access_host") is True
        and _build_start_time_is_current(ilo_checked_at, now=now)
    )
    ilo_requirement = BUILD_START_EVIDENCE_REQUIREMENTS[1]
    if not ilo_access_ready and ilo_requirement.blocker not in blockers:
        blockers.append(ilo_requirement.blocker)

    ilo_trace_time = evidence_times.get("ilo.reachability")
    raid_trace_time = evidence_times.get("raid.validate")
    raid_requirement = BUILD_START_EVIDENCE_REQUIREMENTS[2]
    if (
        ilo_trace_time is not None
        and raid_trace_time is not None
        and raid_trace_time < ilo_trace_time
        and raid_requirement.blocker not in blockers
    ):
        blockers.append(raid_requirement.blocker)

    return blockers


def _build_start_trace_is_accepted(
    trace: dict[str, Any] | None,
    *,
    requirement: BuildStartEvidenceRequirement,
    profile_id: str,
    profile_fingerprint: str,
    checked_at: datetime | None,
    now: datetime,
) -> bool:
    if not isinstance(trace, dict):
        return False
    return (
        str(trace.get("action_id") or "") == requirement.action_id
        and str(trace.get("status") or "").lower() == "completed"
        and str(trace.get("evidence_status") or "").lower()
        in requirement.accepted_evidence_statuses
        and str(trace.get("source_type") or "").lower() == "live_probe"
        and str(trace.get("freshness") or "").lower() == "current"
        and trace.get("not_mock") is True
        and trace.get("executed") is True
        and not trace.get("blockers")
        and str(trace.get("lab_profile_id") or "") == profile_id
        and str(trace.get("lab_profile_fingerprint") or "") == profile_fingerprint
        and _build_start_time_is_current(checked_at, now=now)
    )


def _build_start_trace_time(trace: dict[str, Any] | None) -> datetime | None:
    if not isinstance(trace, dict):
        return None
    return _parse_datetime(
        trace.get("evidence_checked_at")
        or trace.get("checked_at")
        or trace.get("finished_at")
    )


def _build_start_time_is_current(value: datetime | None, *, now: datetime) -> bool:
    if value is None or value > now:
        return False
    return now - value <= timedelta(seconds=DEFAULT_STALE_AFTER_SECONDS)


def _deployment_mode(context: dict[str, Any]) -> str:
    features = context.get("enabled_features") if isinstance(context.get("enabled_features"), dict) else {}
    if features.get("netapp_enabled") is False:
        return "Single server - local RAID"
    return "Server + shared storage" + (" + central management" if features.get("vcenter_enabled") else "")


def _active_profile(context: dict[str, Any]) -> dict[str, Any]:
    profile = context.get("active_profile")
    return profile if isinstance(profile, dict) else {}


def _current_step(run: dict[str, Any]) -> dict[str, Any] | None:
    current_id = run.get("current_step_id")
    return next((step for step in _steps(run) if step.get("step_id") == current_id), None)


def _steps(run: dict[str, Any]) -> list[dict[str, Any]]:
    value = run.get("steps")
    return value if isinstance(value, list) else []


def _reset_step(step: dict[str, Any]) -> None:
    step.update(
        {
            "status": "not_started",
            "summary": "not_started",
            "operator_message": "Waiting for its dependencies.",
            "technical_details": "",
            "started_at": None,
            "finished_at": None,
            "action_run_id": None,
            "waiting_nonce": None,
            "lease_expires_at": None,
        }
    )


def _save_run(run: dict[str, Any]) -> None:
    _run_dir().mkdir(parents=True, exist_ok=True)
    run["revision"] = int(run.get("revision") or 0) + 1
    write_json_object(_run_path(str(run["run_id"])), _refresh_run_summary(run))


def _load_run(run_id: str) -> dict[str, Any]:
    payload = read_json_object(_run_path(run_id))
    if not payload or payload.get("run_id") != run_id:
        raise LabBuildRunNotFoundError(run_id)
    if _normalize_legacy_run(payload):
        _save_run(payload)
    return payload


def _normalize_legacy_run(run: dict[str, Any]) -> bool:
    changed = False
    if "revision" not in run:
        run["revision"] = 0
        changed = True
    for step in _steps(run):
        for key, default in (
            ("optional", False),
            ("waiting_nonce", None),
            ("lease_expires_at", None),
        ):
            if key not in step:
                step[key] = default
                changed = True

    if run.get("profile_fingerprint") or run.get("status") not in {"planned", "running", "waiting"}:
        return changed

    step = _current_step(run)
    if step:
        step.update(
            {
                "status": "failed",
                "summary": "resume_contract_upgrade_required",
                "operator_message": "This saved build cannot be resumed safely after the reliability upgrade.",
                "technical_details": "The saved run predates revision, profile, and evidence binding.",
                "suggested_action": "Reopen the build plan and start a new run.",
                "can_retry": False,
                "finished_at": _now(),
                "waiting_nonce": None,
                "lease_expires_at": None,
            }
        )
    run.update(
        {
            "status": "failed",
            "headline": "Reopen this build plan.",
            "operator_message": "This older saved run was stopped because its resume evidence cannot be verified.",
            "suggested_action": "Close this report and start a new build run.",
            "updated_at": _now(),
            "finished_at": _now(),
        }
    )
    return True


def _assert_revision(run: dict[str, Any], expected: int) -> None:
    if int(run.get("revision") or 0) != expected:
        raise LabBuildRunStateError("This build changed after the page was opened. Refresh and try again.")


def _assert_profile_unchanged(run: dict[str, Any], context: dict[str, Any]) -> None:
    if str(run.get("profile_fingerprint") or "") != _profile_fingerprint(context):
        raise LabBuildRunStateError("The selected kit changed while this build was waiting. Reopen the build plan.")


def _profile_fingerprint(context: dict[str, Any]) -> str:
    return lab_profile_context_fingerprint(context)


def _claim_guarded_evidence(
    trace: dict[str, Any],
    run: dict[str, Any],
    step: dict[str, Any],
) -> None:
    trace_run_id = str(trace.get("run_id") or "")
    if not trace_run_id:
        raise LabBuildRunStateError("The guarded action evidence has no run identifier.")
    claim_key = f"{step['action_id']}::{trace_run_id}"
    path = _run_dir() / EVIDENCE_CLAIMS_FILENAME
    with _run_lock("guarded-evidence-claims"):
        claims = read_json_object(path)
        existing = claims.get(claim_key)
        if isinstance(existing, dict) and (
            existing.get("lab_build_run_id") != run.get("run_id")
            or existing.get("step_id") != step.get("step_id")
        ):
            raise LabBuildRunStateError("That guarded action evidence is already attached to another build.")
        claims[claim_key] = {
            "lab_build_run_id": run.get("run_id"),
            "kit_id": run.get("kit_id"),
            "profile_fingerprint": run.get("profile_fingerprint"),
            "step_id": step.get("step_id"),
            "claimed_at": _now(),
        }
        write_json_object(path, claims)


def _reconcile_stale_run(run: dict[str, Any]) -> bool:
    if run.get("status") != "running":
        return False
    step = _current_step(run)
    if not step or step.get("status") != "running":
        return False
    expires_at = _parse_datetime(step.get("lease_expires_at"))
    if expires_at is None:
        updated_at = _parse_datetime(run.get("updated_at"))
        expires_at = updated_at + timedelta(seconds=RUN_LEASE_SECONDS) if updated_at else None
    if expires_at is None or expires_at > datetime.now(UTC):
        return False

    step.update(
        {
            "status": "failed",
            "summary": "execution_interrupted",
            "operator_message": "This check stopped before reporting a result.",
            "technical_details": "The execution lease expired without a terminal action result.",
            "can_retry": bool(step.get("can_retry")),
            "finished_at": _now(),
            "lease_expires_at": None,
        }
    )
    _mark_downstream_blocked(run, step)
    run.update(
        {
            "status": "failed",
            "headline": f"Build stopped at step {step['order']} of {len(_steps(run))}.",
            "operator_message": step["operator_message"],
            "suggested_action": step["suggested_action"],
            "updated_at": _now(),
        }
    )
    return True


@contextmanager
def _run_lock(run_id: str) -> Iterator[None]:
    _run_dir().mkdir(parents=True, exist_ok=True)
    path = _run_dir() / f".{_run_slug(run_id)}.lock"
    handle = open(path, "a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + RUN_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise LabBuildRunStateError("This build is already being updated. Try again shortly.") from exc
                time.sleep(0.05)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def _run_path(run_id: str) -> Path:
    return _run_dir() / f"{_run_slug(run_id)}.json"


def _run_dir() -> Path:
    configured = os.environ.get("LAB_BUILD_RUN_DIR")
    return Path(configured) if configured else LAB_BUILD_RUN_DIR


def _run_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:140] or "lab-build"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lease_expiry() -> str:
    return (datetime.now(UTC) + timedelta(seconds=RUN_LEASE_SECONDS)).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item).strip()]
