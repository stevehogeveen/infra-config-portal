from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal

from sqlalchemy.orm import Session

from app.services.control_actions import REPO_ROOT
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.lab_profiles import active_lab_profile_context
from app.services.path_utils import display_path, glob_paths
from app.services.workflow_action_run_store import latest_workflow_action_run_trace
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
    preflight_blocker: str | None = None


ActionRunner = Callable[[str, Session | None, dict[str, Any] | None], dict[str, Any]]


def get_lab_build_plan(
    *,
    context: dict[str, Any] | None = None,
    definitions: tuple[BuildStepDefinition, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = context or active_lab_profile_context()
    ordered = _ordered_definitions(definitions or _kit_step_definitions(resolved_context))
    profile = _active_profile(resolved_context)
    blockers = _plan_blockers(profile, ordered)
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
    plan = get_lab_build_plan(context=context, definitions=definitions)
    if plan["blockers"]:
        raise LabBuildPlanError(plan["blockers"][0])

    now = _now()
    run = {
        "run_id": f"lab-build:{uuid.uuid4().hex[:12]}",
        "kit_id": plan["kit_id"],
        "kit_name": plan["kit_name"],
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
    action_runner: ActionRunner = run_workflow_action,
) -> dict[str, Any]:
    run = get_lab_build_run(run_id)
    if run.get("status") != "waiting":
        raise LabBuildRunStateError("Only a waiting build can be resumed.")
    waiting_step = _current_step(run)
    if waiting_step and waiting_step["status"] == "waiting":
        _resolve_waiting_step(waiting_step)
        run["updated_at"] = _now()
        _save_run(run)
        if waiting_step["status"] == "waiting":
            return _refresh_run_summary(run)
    return _advance_run(run, session=session, action_runner=action_runner)


def retry_lab_build_step(
    run_id: str,
    step_id: str,
    session: Session | None = None,
    *,
    action_runner: ActionRunner = run_workflow_action,
) -> dict[str, Any]:
    run = get_lab_build_run(run_id)
    steps = _steps(run)
    step_index = next((index for index, step in enumerate(steps) if step["step_id"] == step_id), None)
    if step_index is None:
        raise LabBuildStepNotFoundError(step_id)
    step = steps[step_index]
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
    payload = read_json_object(_run_path(run_id))
    if not payload or payload.get("run_id") != run_id:
        raise LabBuildRunNotFoundError(run_id)
    return _refresh_run_summary(payload)


def get_latest_lab_build_run() -> dict[str, Any] | None:
    runs = [read_json_object(path) for path in glob_paths(_run_dir(), "*.json")]
    valid = [run for run in runs if run.get("run_id")]
    if not valid:
        return None
    return _refresh_run_summary(max(valid, key=lambda run: str(run.get("updated_at") or "")))


def _kit_step_definitions(context: dict[str, Any]) -> tuple[BuildStepDefinition, ...]:
    features = context.get("enabled_features") if isinstance(context.get("enabled_features"), dict) else {}
    netapp_enabled = features.get("netapp_enabled") is not False
    vcenter_enabled = netapp_enabled and features.get("vcenter_enabled") is True
    storage_protocol = str(features.get("storage_protocol") or "nfs").lower()

    definitions = [
        BuildStepDefinition(
            "profile",
            "Check lab addresses",
            "Confirm the selected kit and its address plan are complete.",
            "lab-profile.validate-ip-profile",
            "read_only",
            (),
            ("lab-profile",),
            "/overview",
            "Correct the selected kit or address plan, then retry.",
        ),
        BuildStepDefinition(
            "firmware",
            "Check firmware readiness",
            "Compare installed firmware with the selected kit baseline.",
            "firmware.compliance-check",
            "read_only",
            ("lab-profile",),
            ("firmware-ready",),
            "/firmware-upgrades",
            "Review the firmware map and resolve the listed exception.",
        ),
        BuildStepDefinition(
            "network",
            "Configure the management network",
            "Prepare the switch so the remaining devices can use the management network.",
            "cisco.apply-bootstrap",
            "write",
            ("lab-profile", "firmware-ready"),
            ("mgmt-network",),
            "/network",
            "Open Network Setup, approve the guarded change, then resume this build.",
        ),
        BuildStepDefinition(
            "server-control",
            "Check server management",
            "Confirm the server management controller can be reached before storage work.",
            "ilo.reachability",
            "read_only",
            ("lab-profile", "firmware-ready"),
            ("server-control",),
            "/server",
            "Open Server Setup and correct the management connection, then retry.",
        ),
        BuildStepDefinition(
            "local-storage",
            "Create the server storage layout",
            "Apply the saved local disk and RAID plan for this server.",
            "raid.apply",
            "destructive",
            ("server-control",),
            ("local-storage",),
            "/server",
            "Open Server Setup, review and approve the RAID plan, then resume this build.",
            can_retry=False,
        ),
        BuildStepDefinition(
            "hypervisor",
            "Install the compute host",
            "Install and configure the compute host after local storage and networking are ready.",
            "esxi.rebuild-install",
            "destructive",
            ("mgmt-network", "local-storage"),
            ("hypervisor",),
            "/virtualization",
            "Open Virtualization Setup, approve the guarded install, then resume this build.",
            can_retry=False,
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
                    ("mgmt-network",),
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
                    "Connect shared storage to the compute host",
                    "Make the selected shared storage available to the compute host.",
                    "esxi.iscsi-datastore-validate" if storage_protocol == "iscsi" else "esxi.netapp-datastore-apply",
                    "read_only" if storage_protocol == "iscsi" else "write",
                    ("hypervisor", "shared-storage"),
                    ("datastore",),
                    "/virtualization",
                    "Open Virtualization Setup, finish the storage connection, then retry.",
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
        "depends_on": list(definition.depends_on),
        "provides": list(definition.provides),
        "action_id": definition.action_id,
        "action_mode": definition.mode,
        "operator_path": definition.operator_path,
        "rationale": definition.rationale,
        "started_at": None,
        "finished_at": None,
        "action_run_id": None,
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
                    "status": "blocked",
                    "summary": "dependency_not_ready",
                    "operator_message": f"Blocked by: {blocker}.",
                    "technical_details": "A declared build capability is not currently available.",
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
        run["updated_at"] = _now()
        _save_run(run)
        if step["status"] in {"failed", "blocked"}:
            return _stop_run(run, step, "failed")
        if step["status"] == "waiting":
            return _stop_run(run, step, "waiting")

    return _complete_run(run)


def _apply_action_result(step: dict[str, Any], result: dict[str, Any]) -> None:
    raw_status = str(result.get("status") or "failed").lower()
    blockers = _string_list(result.get("blockers"))
    warnings = _string_list(result.get("warnings"))
    if raw_status == "waiting":
        status: BuildStepStatus = "waiting"
        message = str(result.get("operator_message") or f"Waiting on: {step['label'].lower()}.")
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
        status = "skipped"
        message = f"{step['label']} is not required for this kit."
    else:
        status = "failed"
        message = f"{step['label']} failed."

    technical = {
        "status": raw_status,
        "summary": result.get("summary"),
        "blockers": blockers,
        "warnings": warnings,
        "next_action": result.get("next_action"),
        "error_type": result.get("error_type"),
        "trace_artifact": result.get("trace_artifact"),
        "report_artifacts": result.get("report_artifacts"),
    }
    step.update(
        {
            "status": status,
            "summary": str(result.get("summary") or raw_status),
            "operator_message": message,
            "technical_details": json.dumps(technical, indent=2, default=str),
            "suggested_action": step["suggested_action"],
            "can_retry": bool(step.get("can_retry")) and status != "waiting",
            "finished_at": None if status == "waiting" else _now(),
            "action_run_id": result.get("run_id"),
        }
    )


def _resolve_waiting_step(step: dict[str, Any]) -> None:
    latest = latest_workflow_action_run_trace(str(step["action_id"]))
    if not latest or not _trace_is_new_enough(latest, step.get("started_at")):
        return
    _apply_action_result(step, latest)


def _trace_is_new_enough(trace: dict[str, Any], started_at: Any) -> bool:
    trace_time = _parse_datetime(trace.get("finished_at") or trace.get("started_at"))
    waiting_time = _parse_datetime(started_at)
    return bool(trace_time and waiting_time and trace_time >= waiting_time)


def _dependency_blocker(step: dict[str, Any], steps: list[dict[str, Any]]) -> str | None:
    owners = {
        capability: candidate
        for candidate in steps
        for capability in _string_list(candidate.get("provides"))
    }
    for capability in _string_list(step.get("depends_on")):
        owner = owners.get(capability)
        if not owner or owner.get("status") not in SUCCESS_STATUSES:
            return str(owner.get("label") if owner else capability.replace("-", " "))
    return None


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
                "status": "blocked",
                "summary": "dependency_not_ready",
                "operator_message": f"Blocked by: {blocker}.",
                "technical_details": "A declared build capability is not currently available.",
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
    _save_run(run)
    run["report_artifact"] = _write_completion_report(run)
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
        }
    )


def _save_run(run: dict[str, Any]) -> None:
    _run_dir().mkdir(parents=True, exist_ok=True)
    write_json_object(_run_path(str(run["run_id"])), _refresh_run_summary(run))


def _run_path(run_id: str) -> Path:
    return _run_dir() / f"{_run_slug(run_id)}.json"


def _run_dir() -> Path:
    configured = os.environ.get("LAB_BUILD_RUN_DIR")
    return Path(configured) if configured else LAB_BUILD_RUN_DIR


def _run_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:140] or "lab-build"


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
