from __future__ import annotations

import json
import os
import signal
import subprocess
import uuid
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import PureWindowsPath
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter, IloRedfishConfig
from app.providers.redaction import redact_sensitive
from app.services.build_verification import get_lab_build_verification
from app.services.firmware_compliance import get_firmware_compliance, get_firmware_inventory, write_waiver_report
from app.services.full_rebuild_run import get_full_rebuild_summary
from app.services.golden_state import get_provider_lab_golden_state
from app.services.guarded_action_context import GuardedActionContext
from app.schemas import HpeRaidApplyCreate, HpeRaidFactoryResetCreate
from app.services.hpe_raid import (
    apply_hpe_raid_factory_reset,
    apply_hpe_raid_plan,
    build_hpe_raid_apply_plan,
    build_hpe_raid_factory_reset_preview,
    get_hpe_raid_plan_preview,
    get_hpe_storage_discovery,
    reset_server_for_raid,
    validate_hpe_raid_after_reset,
    write_hpe_raid_pending_report,
)
from app.services.ilo_baseline import get_ilo_baseline_preview, get_ilo_baseline_readiness
from app.services.lab_profiles import (
    active_lab_profile_context,
    lab_profile_context_fingerprint,
    list_lab_profiles,
)
from app.services.lab_validation import get_lab_validation_summary
from app.services.cisco_setup_readiness import get_cisco_setup_readiness
from app.services.cisco_current_intent import get_cisco_current_intent_diff
from app.services.ilo_readiness import get_ilo_setup_plan_preview
from app.services.json_file_store import write_json_object, write_text_value
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.media_inventory import get_media_inventory
from app.services.netapp_iscsi_setup import apply_netapp_iscsi_setup, build_netapp_iscsi_setup_preview, validate_netapp_iscsi_setup
from app.services.netapp_factory_reset import (
    apply_netapp_factory_reset,
    build_netapp_factory_reset_preview,
    validate_netapp_factory_reset,
)
from app.services.netapp_nfs_setup import apply_netapp_nfs_setup, build_netapp_nfs_setup_preview, validate_netapp_nfs_setup
from app.services.netapp_address_plan import (
    build_netapp_address_remediation_plan,
    build_netapp_address_remediation_preview,
    diagnose_netapp_ha_node_warning,
    validate_netapp_address_remediation,
)
from app.services.netapp_real_lab import (
    get_netapp_nfs_vcenter_readiness,
    run_netapp_console_discovery,
    run_netapp_console_login_state,
    run_netapp_console_read_state,
    run_netapp_live_state,
    run_netapp_setup_validation,
)
from app.services.netapp_setup_intent import apply_netapp_setup, build_netapp_setup_preview, run_netapp_post_setup_validation
from app.services.netapp_upgrade_center import (
    build_netapp_upgrade_inventory,
    build_netapp_upgrade_plan,
    validate_netapp_upgrade,
)
from app.services.path_utils import path_exists as _path_exists
from app.services.report_center import get_report_center, get_report_summary
from app.services.esxi_netapp_datastore import (
    apply_esxi_netapp_datastore,
    build_esxi_netapp_datastore_preview,
    validate_esxi_netapp_datastore,
)
from app.services.esxi_install_readiness import get_esxi_install_readiness
from app.services.esxi_management_recovery import validate_esxi_post_recovery
from app.services.esxi_iscsi_datastore import build_esxi_iscsi_datastore_preview, validate_esxi_iscsi_datastore
from app.services.esxi_vm_deploy import apply_esxi_vm_deploy, build_esxi_vm_deploy_preview, validate_esxi_vm_deploy
from app.services.esxi_vm_teardown import (
    apply_esxi_vm_teardown,
    build_esxi_vm_teardown_preview,
    validate_esxi_vm_teardown,
)
from app.services.vcenter_netapp_readiness import (
    get_vcenter_attach_esxi_preview,
    get_vcenter_install_plan,
    get_vcenter_install_preview,
    get_vcenter_install_readiness,
    get_vcenter_netapp_datastore_plan,
    get_vcenter_netapp_readiness,
    validate_vcenter_post_attach,
)
from app.services.workflow_action_allowlist import (
    get_workflow_action_execution_spec,
    workflow_action_run_blockers,
)
from app.services.workflow_action_run_store import (
    latest_workflow_action_run_trace,
    list_workflow_action_run_traces,
    save_workflow_action_run_trace,
)
from app.services.workflow_registry import WorkflowRegistryNotFoundError, get_workflow_action, workflow_action_exists
from app.services.control_actions import REPO_ROOT

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
ESXI_MANAGEMENT_VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-management-readiness-report.md"
ESXI_MANAGEMENT_VALIDATION_JSON = CODEX_RUN_DIR / "esxi-management-readiness-redacted.json"
ILO_REACHABILITY_REPORT = CODEX_RUN_DIR / "ilo-real-run-report.md"
ILO_REACHABILITY_JSON = CODEX_RUN_DIR / "ilo-real-run-redacted.json"
HPE_RAID_DISCOVERY_REPORT = CODEX_RUN_DIR / "hpe-raid-discovery-report.md"
HPE_RAID_PLAN_REPORT = CODEX_RUN_DIR / "hpe-raid-plan-report.md"
ILO_WRITE_ACTION_IDS = frozenset(
    {
        "esxi.one-time-boot",
        "esxi.rebuild-install",
        "esxi.recover-management",
        "esxi.virtual-media-insert",
        "ilo.one-time-boot",
        "ilo.reset-server",
        "ilo.virtual-media-insert",
        "raid.apply",
        "raid.reset-commit",
    }
)
ILO_EXACT_READ_ACTION_IDS = frozenset({"raid.discovery"})


class WorkflowActionRunNotFoundError(LookupError):
    pass


def run_workflow_action(
    action_id: str,
    session: Session | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = get_workflow_action(action_id)
    payload = payload or {}
    blockers = workflow_action_run_blockers(
        action,
        confirmation_phrase=_string_or_none(payload.get("confirmation_phrase")),
        confirmed_gates=_string_list(payload.get("confirmed_gates")),
    )
    blockers = _unique(
        [
            *blockers,
            *_ilo_exact_read_request_blockers(action_id, payload),
            *_ilo_write_request_blockers(action_id, payload),
        ]
    )
    started_at = _now()
    run_id = f"workflow-action:{action_id}:{uuid.uuid4().hex[:12]}"
    if blockers:
        result = _blocked_result(action, run_id, started_at, blockers)
        return _save_profile_bound_trace(result)

    spec = get_workflow_action_execution_spec(action_id)
    if spec is None:
        result = _blocked_result(
            action,
            run_id,
            started_at,
            ["No read-only UI runner allowlist entry exists for this action yet."],
        )
        return _save_profile_bound_trace(result)

    if spec.kind == "api":
        result = _run_api_action(action, run_id, started_at, session, payload)
    else:
        result = _run_command_action(
            action,
            run_id,
            started_at,
            spec.command,
            spec.timeout_seconds,
            request_env_overrides=_guarded_command_env_overrides(action_id, payload),
        )

    reports = _existing_report_artifacts([*_string_list(action.get("reports")), *_string_list(spec.reports)])
    result["report_artifacts"] = _unique(
        [
            *reports,
            *_string_list(result.get("report_artifacts")),
        ]
    )
    return _save_profile_bound_trace(result)


def _save_profile_bound_trace(result: dict[str, Any]) -> dict[str, Any]:
    context = active_lab_profile_context()
    profile = context.get("active_profile") if isinstance(context.get("active_profile"), dict) else {}
    return save_workflow_action_run_trace(
        {
            **result,
            "lab_profile_id": str(profile.get("id") or "runtime-profile"),
            "lab_profile_fingerprint": lab_profile_context_fingerprint(context),
        }
    )


def list_workflow_action_runs(action_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    if not workflow_action_exists(action_id):
        raise WorkflowRegistryNotFoundError(action_id)
    return [_compact_run_history_trace(trace) for trace in list_workflow_action_run_traces(action_id, limit=limit)]


def latest_workflow_action_run(action_id: str) -> dict[str, Any] | None:
    return latest_workflow_action_run_trace(action_id)


def _run_command_action(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    command: tuple[str, ...],
    timeout_seconds: int,
    *,
    request_env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed: subprocess.CompletedProcess[str] | None = None
    stderr = ""
    stdout = ""
    normalized_command, inline_env_overrides = _normalize_inline_env_command(command)
    env_overrides = {**inline_env_overrides, **(request_env_overrides or {})}
    try:
        if env_overrides:
            completed = _run_subprocess(normalized_command, timeout_seconds, env_overrides=env_overrides)
        else:
            completed = _run_subprocess(normalized_command, timeout_seconds)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return_code = completed.returncode
        status = "completed" if return_code == 0 else "failed"
        blockers = [] if return_code == 0 else [f"Command exited with code {return_code}; review evidence before rerun."]
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_output(exc.stdout)
        stderr = _decode_output(exc.stderr)
        return_code = None
        status = "failed"
        blockers = [f"Command exceeded the {timeout_seconds}s safe action runner timeout."]
    except OSError as exc:
        return_code = None
        status = "failed"
        blockers = [_command_start_blocker(normalized_command, exc)]

    stdout_summary = _redacted_summary(stdout)
    stderr_summary = _redacted_summary(stderr)
    status, blockers, warnings = _command_report_gate(action, status, blockers, _output_warnings(stdout_summary, stderr_summary))
    return _base_result(
        action,
        run_id,
        started_at,
        status=status,
        command=" ".join(command),
        executed=True,
        return_code=return_code,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        blockers=blockers,
        warnings=warnings,
    )


def _run_api_action(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    session: Session | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        action_id = str(action["action_id"])
        guarded_context = _guarded_action_context(action_id, payload)
        action_payload = _api_action_payload(action_id, session, payload, guarded_context=guarded_context)
        summary_limit = 16000 if action_id == "cisco.ssh-readonly-probe" else 4000
        stdout_summary = _redacted_summary(json.dumps(_api_stdout_payload(action_id, action_payload), sort_keys=True), max_chars=summary_limit)
        payload_status = str(action_payload.get("status") or "").lower() if isinstance(action_payload, dict) else ""
        status = payload_status if payload_status in {"blocked", "failed"} else "completed"
        blockers = _string_list(action_payload.get("blockers")) if isinstance(action_payload, dict) and status == "blocked" else []
        warnings = _string_list(action_payload.get("warnings")) if isinstance(action_payload, dict) else []
        result = _base_result(
            action,
            run_id,
            started_at,
            status=status,
            command=f"{action.get('api_method') or 'GET'} {action.get('api_endpoint')}",
            executed=True,
            return_code=0 if status != "failed" else None,
            stdout_summary=stdout_summary,
            stderr_summary="",
            blockers=blockers,
            warnings=warnings,
        )
        if isinstance(action_payload, dict):
            result["evidence_status"] = payload_status or None
            result["evidence_checked_at"] = _string_or_none(
                action_payload.get("checked_at")
                or action_payload.get("finished_at")
            )
            result["report_artifacts"] = _unique(
                [
                    *_string_list(result.get("report_artifacts")),
                    *_string_list(action_payload.get("report_artifacts")),
                ]
            )
        return result
    except Exception as exc:
        return _base_result(
            action,
            run_id,
            started_at,
            status="failed",
            command=f"{action.get('api_method') or 'GET'} {action.get('api_endpoint')}",
            executed=True,
            return_code=None,
            stdout_summary="",
            stderr_summary=_redacted_summary(f"{exc.__class__.__name__}: {exc}"),
            blockers=[f"API action failed before completing safely: {exc.__class__.__name__}."],
            warnings=[],
        )


def _api_action_payload(
    action_id: str,
    session: Session | None,
    payload: dict[str, Any] | None = None,
    *,
    guarded_context: GuardedActionContext | None = None,
) -> Any:
    payload = payload or {}
    if action_id == "cisco.discover-console":
        return CiscoConsoleAdapter().prompt_readiness()
    if action_id == "cisco.setup-readiness":
        return get_cisco_setup_readiness()
    if action_id == "cisco.ssh-readonly-probe":
        from app.providers.cisco_ansible import CiscoAnsibleAdapter, _validated_extra_show_commands

        extra_commands = _validated_extra_show_commands(payload.get("cisco_commands"))
        adapter = CiscoAnsibleAdapter()
        return adapter.probe(extra_show_commands=extra_commands) if extra_commands else adapter.probe()
    if action_id == "cisco.current-intent-diff":
        return get_cisco_current_intent_diff()
    if action_id in {"cisco.firmware-inventory", "ilo.firmware-inventory"}:
        return get_firmware_inventory(refresh_live=False)
    if action_id == "ilo.reachability":
        payload = IloRedfishAdapter(config=_ilo_config_for_payload(payload)).probe()
        return _write_ilo_reachability_artifacts(payload)
    if action_id == "ilo.auth":
        return get_ilo_baseline_readiness()
    if action_id == "ilo.inventory":
        return get_ilo_baseline_preview()
    if action_id == "ilo.baseline-preview":
        return get_ilo_baseline_preview()
    if action_id == "ilo.setup-plan-preview":
        return get_ilo_setup_plan_preview(session)
    if action_id == "raid.discovery":
        return _write_hpe_raid_discovery_artifact(
            _ilo_config_for_payload(payload, require_explicit_target=True)
        )
    if action_id == "raid.plan":
        if session is None:
            raise WorkflowActionRunNotFoundError("RAID plan preview requires a database session.")
        return _write_hpe_raid_plan_artifact(session)
    if action_id == "raid.pending-check":
        if session is None:
            raise WorkflowActionRunNotFoundError("RAID pending check requires a database session.")
        return write_hpe_raid_pending_report(session)
    if action_id == "raid.validate":
        if session is None:
            raise WorkflowActionRunNotFoundError("RAID validation requires a database session.")
        return validate_hpe_raid_after_reset(session)
    if action_id == "raid.apply":
        if session is None:
            raise WorkflowActionRunNotFoundError("RAID apply requires a database session.")
        return apply_hpe_raid_plan(
            session,
            HpeRaidApplyCreate(
                confirmation_phrase=_string_or_none(payload.get("confirmation_phrase")) or "",
                ilo_host=_string_or_none(payload.get("ilo_host")),
            ),
            guarded_context=guarded_context,
        )
    if action_id == "raid.factory-reset-preview":
        if session is None:
            raise WorkflowActionRunNotFoundError("RAID factory reset preview requires a database session.")
        return build_hpe_raid_factory_reset_preview(session)
    if action_id == "raid.factory-reset-apply":
        if session is None:
            raise WorkflowActionRunNotFoundError("RAID factory reset apply requires a database session.")
        return apply_hpe_raid_factory_reset(
            session,
            HpeRaidFactoryResetCreate(confirmation_phrase=_string_or_none(payload.get("confirmation_phrase")) or ""),
            guarded_context=guarded_context,
        )
    if action_id == "raid.reset-commit":
        return reset_server_for_raid(
            ilo_host=_string_or_none(payload.get("ilo_host")),
            guarded_context=guarded_context,
        )
    if action_id == "esxi.readiness":
        if session is None:
            raise WorkflowActionRunNotFoundError("ESXi readiness requires a database session.")
        return get_esxi_install_readiness(session)
    if action_id in {"esxi.installer-boot-detection", "esxi.management-readiness"}:
        if session is None:
            raise WorkflowActionRunNotFoundError("ESXi readiness requires a database session.")
        return get_esxi_install_readiness(session)
    if action_id == "esxi.iso-media-check":
        return get_media_inventory()
    if action_id == "esxi.management-validation":
        payload = EsxiReadonlyAdapter().probe()
        return _write_esxi_management_validation_artifacts(payload)
    if action_id == "esxi.post-recovery-validation":
        return validate_esxi_post_recovery(write_report=False)
    if action_id == "esxi.ssh-api-check":
        payload = EsxiReadonlyAdapter().probe()
        return _write_esxi_management_validation_artifacts(payload)
    if action_id == "esxi.netapp-datastore-preview":
        return build_esxi_netapp_datastore_preview()
    if action_id == "esxi.netapp-datastore-apply":
        return apply_esxi_netapp_datastore(guarded_context=guarded_context)
    if action_id == "esxi.netapp-datastore-validate":
        return validate_esxi_netapp_datastore()
    if action_id == "esxi.iscsi-datastore-preview":
        return build_esxi_iscsi_datastore_preview()
    if action_id == "esxi.iscsi-datastore-validate":
        return validate_esxi_iscsi_datastore()
    if action_id == "esxi.vm-deploy-preview":
        return build_esxi_vm_deploy_preview()
    if action_id == "esxi.vm-deploy-apply":
        return apply_esxi_vm_deploy(guarded_context=guarded_context)
    if action_id == "esxi.vm-teardown-preview":
        return build_esxi_vm_teardown_preview(_configured_vm_teardown_name())
    if action_id == "esxi.vm-teardown-apply":
        return apply_esxi_vm_teardown(
            _configured_vm_teardown_name(),
            guarded_context=guarded_context,
        )
    if action_id == "esxi.vm-teardown-validate":
        return validate_esxi_vm_teardown(_configured_vm_teardown_name())
    if action_id == "netapp.live-state":
        return run_netapp_live_state()
    if action_id == "netapp.console-autodiscovery":
        return run_netapp_console_discovery(session=session)
    if action_id == "netapp.console-read-state":
        return run_netapp_console_read_state(session=session)
    if action_id == "netapp.console-login-state":
        return run_netapp_console_login_state()
    if action_id == "netapp.nfs-vcenter-readiness":
        return get_netapp_nfs_vcenter_readiness(write_report=False)
    if action_id == "netapp.validate-setup":
        return run_netapp_setup_validation()
    if action_id == "netapp.setup-preview":
        return build_netapp_setup_preview(run_address_scan=False, write_report=False)
    if action_id == "netapp.setup-apply":
        return apply_netapp_setup(guarded_context=guarded_context)
    if action_id == "netapp.post-setup-validation":
        return run_netapp_post_setup_validation()
    if action_id == "netapp.address-plan":
        return build_netapp_address_remediation_plan(write_report=False)
    if action_id == "netapp.address-preview":
        return build_netapp_address_remediation_preview(write_report=False)
    if action_id == "netapp.address-validate":
        return validate_netapp_address_remediation(write_report=False)
    if action_id == "netapp.ha-node-diagnose":
        return diagnose_netapp_ha_node_warning()
    if action_id == "netapp.factory-reset-preview":
        return build_netapp_factory_reset_preview()
    if action_id == "netapp.factory-reset-apply":
        return apply_netapp_factory_reset(guarded_context=guarded_context)
    if action_id == "netapp.factory-reset-validate":
        return validate_netapp_factory_reset()
    if action_id == "netapp.nfs-setup-preview":
        return build_netapp_nfs_setup_preview(write_report=False)
    if action_id == "netapp.nfs-setup-apply":
        return apply_netapp_nfs_setup(guarded_context=guarded_context)
    if action_id == "netapp.nfs-setup-validate":
        return validate_netapp_nfs_setup()
    if action_id == "netapp.iscsi-setup-preview":
        return build_netapp_iscsi_setup_preview(write_report=False)
    if action_id == "netapp.iscsi-setup-apply":
        return apply_netapp_iscsi_setup(guarded_context=guarded_context)
    if action_id == "netapp.iscsi-setup-validate":
        return validate_netapp_iscsi_setup()
    if action_id == "esxi.vm-deploy-validate":
        return validate_esxi_vm_deploy()
    if action_id == "vcenter-netapp.readiness":
        return get_vcenter_netapp_readiness(check_ports=False, write_report=False)
    if action_id == "vcenter-netapp.datastore-plan":
        return get_vcenter_netapp_datastore_plan(write_report=False)
    if action_id == "vcenter.install-readiness":
        return get_vcenter_install_readiness(check_ports=False, write_report=False)
    if action_id == "vcenter.install-plan":
        return get_vcenter_install_plan(write_report=False)
    if action_id == "vcenter.install-preview":
        return get_vcenter_install_preview(write_report=False)
    if action_id == "vcenter.attach-esxi-preview":
        return get_vcenter_attach_esxi_preview(write_report=False)
    if action_id == "vcenter.post-attach-validation":
        return validate_vcenter_post_attach(write_report=False)
    if action_id == "firmware.inventory":
        return get_firmware_inventory(refresh_live=True)
    if action_id in {"firmware.compliance-check", "firmware.upgrade-plan"}:
        return get_firmware_compliance(refresh_live=False)
    if action_id == "firmware.package-inventory":
        return get_media_inventory()
    if action_id == "firmware.waiver-check":
        return write_waiver_report()
    if action_id in {"netapp.ontap-upgrade-inventory", "netapp.component-firmware-inventory"}:
        return build_netapp_upgrade_inventory(write_report=False)
    if action_id == "netapp.ontap-upgrade-plan":
        return build_netapp_upgrade_plan(write_report=False)
    if action_id == "netapp.ontap-upgrade-validate":
        return validate_netapp_upgrade(write_report=False)
    if action_id == "build-verification.run-full":
        return get_lab_build_verification()
    if action_id in {"lab-validation.summary", "full-lab.validation"}:
        return get_lab_validation_summary(write_report=True)
    if action_id == "full-lab.build-plan":
        return get_full_rebuild_summary()
    if action_id in {"full-lab.repair", "full-lab.handoff-report"}:
        return get_provider_lab_golden_state(write_report=False)
    if action_id == "reports.issue-center":
        if session is None:
            raise WorkflowActionRunNotFoundError("Report Center requires a database session.")
        return get_report_center(session)
    if action_id == "reports.summary":
        if session is None:
            raise WorkflowActionRunNotFoundError("Report summary requires a database session.")
        return get_report_summary(session)
    if action_id == "lab-profile.view-active":
        return list_lab_profiles()
    if action_id == "lab-profile.validate-ip-profile":
        return get_lab_build_verification()
    raise WorkflowActionRunNotFoundError(action_id)


def _write_esxi_management_validation_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    jsonable = _jsonable(payload)
    sanitized = redact_sensitive(jsonable if isinstance(jsonable, dict) else {"result": jsonable})
    sanitized.setdefault("source_type", "live_probe")
    sanitized.setdefault("freshness", "current")
    sanitized.setdefault("next_safe_action", "Use this live ESXi management proof for datastore and VM deployment validation.")
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(ESXI_MANAGEMENT_VALIDATION_JSON, sanitized)
    write_text_value(ESXI_MANAGEMENT_VALIDATION_REPORT, _esxi_management_markdown(sanitized))
    artifacts = _unique(
        [
            *_string_list(sanitized.get("report_artifacts")),
            _rel_artifact(ESXI_MANAGEMENT_VALIDATION_REPORT),
            _rel_artifact(ESXI_MANAGEMENT_VALIDATION_JSON),
        ]
    )
    sanitized["report_artifacts"] = artifacts
    return sanitized


def _write_ilo_reachability_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    jsonable = _jsonable(payload)
    sanitized = redact_sensitive(jsonable if isinstance(jsonable, dict) else {"result": jsonable})
    sanitized.setdefault("source_type", "live_probe")
    sanitized.setdefault("freshness", "current")
    sanitized.setdefault("next_safe_action", "Use this live iLO proof before RAID, virtual media, boot, or firmware workflows.")
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(ILO_REACHABILITY_JSON, sanitized)
    write_text_value(ILO_REACHABILITY_REPORT, _ilo_reachability_markdown(sanitized))
    sanitized["report_artifacts"] = _unique(
        [
            *_string_list(sanitized.get("report_artifacts")),
            _rel_artifact(ILO_REACHABILITY_REPORT),
            _rel_artifact(ILO_REACHABILITY_JSON),
        ]
    )
    return sanitized


def _ilo_config_for_payload(
    payload: dict[str, Any],
    *,
    require_explicit_target: bool = False,
) -> IloRedfishConfig:
    config = IloRedfishConfig.from_settings()
    requested_host = _string_or_none(payload.get("ilo_host"))
    if not requested_host:
        if require_explicit_target:
            raise ValueError(
                "An explicit current-access ilo_host IP is required for exact-target iLO reads."
            )
        return config

    # An operator-entered first-contact target must be exact-target-only. Falling
    # back to a saved profile could return a successful probe for a different
    # iLO and incorrectly mark the requested address as reachable.
    return replace(
        config,
        host=requested_host,
        host_source="operator_first_contact",
        fallback_hosts=(),
        fallback_host_sources=(),
    )


def _write_hpe_raid_discovery_artifact(
    config: IloRedfishConfig,
) -> dict[str, Any]:
    probe = IloRedfishAdapter(config=config).probe()
    discovery = get_hpe_storage_discovery(
        probe=probe,
        probe_time=_string_or_none(probe.get("checked_at")),
    )
    payload = {
        "checked_at": _now(),
        "provider_id": "ilo-redfish",
        "status": "ok" if probe.get("status") == "ok" and discovery.storage_inventory_available else "blocked",
        "source_type": "live_probe",
        "freshness": "current",
        "probe_status": probe.get("status"),
        "probe_message": probe.get("message"),
        "discovery": discovery.model_dump(),
        "blockers": _string_list(probe.get("blockers")) + _string_list(discovery.blockers),
        "warnings": _string_list(probe.get("warnings")) + _string_list(discovery.warnings),
        "not_attempted": _string_list(probe.get("not_attempted")),
        "next_safe_action": discovery.next_safe_action,
    }
    sanitized = redact_sensitive(_jsonable(payload))
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(HPE_RAID_DISCOVERY_REPORT, _hpe_raid_discovery_markdown(sanitized))
    sanitized["report_artifacts"] = [_rel_artifact(HPE_RAID_DISCOVERY_REPORT)]
    return sanitized


def _write_hpe_raid_plan_artifact(session: Session) -> dict[str, Any]:
    IloRedfishAdapter().probe()
    preview = get_hpe_raid_plan_preview(session)
    apply_plan = build_hpe_raid_apply_plan(session)
    payload = {
        "checked_at": _now(),
        "provider_id": "ilo-redfish",
        "status": preview.status,
        "source_type": "live_probe",
        "freshness": "current",
        "preview": preview.model_dump(),
        "apply_plan": apply_plan,
        "blockers": _string_list(preview.blockers) + _string_list(apply_plan.get("blockers")),
        "warnings": _string_list(preview.warnings) + _string_list(apply_plan.get("warnings")),
        "next_safe_action": preview.next_safe_action,
    }
    sanitized = redact_sensitive(_jsonable(payload))
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(HPE_RAID_PLAN_REPORT, _hpe_raid_plan_markdown(sanitized))
    sanitized["report_artifacts"] = [_rel_artifact(HPE_RAID_PLAN_REPORT)]
    return sanitized


def _hpe_raid_discovery_markdown(payload: dict[str, Any]) -> str:
    discovery = payload.get("discovery") if isinstance(payload.get("discovery"), dict) else {}
    lines = [
        "# HPE RAID Discovery Report",
        "",
        f"- Checked at: `{payload.get('checked_at') or 'unknown'}`",
        f"- Status: `{payload.get('status') or 'unknown'}`",
        f"- Source: `{payload.get('source_type') or 'live_probe'}`",
        f"- Storage inventory available: `{discovery.get('storage_inventory_available')}`",
        f"- Controllers: `{len(discovery.get('controllers') or [])}`",
        f"- Physical drives: `{len(discovery.get('physical_drives') or [])}`",
        f"- Logical drives: `{len(discovery.get('logical_drives') or [])}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = _string_list(payload.get("blockers"))
    lines.extend([f"- {item}" for item in blockers] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    warnings = _string_list(payload.get("warnings"))
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    lines.extend(["", "## Not Attempted", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("not_attempted"))] or ["- Storage writes"])
    return "\n".join(lines) + "\n"


def _hpe_raid_plan_markdown(payload: dict[str, Any]) -> str:
    preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
    planned = preview.get("planned_layout") if isinstance(preview.get("planned_layout"), dict) else {}
    current = preview.get("current_layout") if isinstance(preview.get("current_layout"), dict) else {}
    apply_plan = payload.get("apply_plan") if isinstance(payload.get("apply_plan"), dict) else {}
    lines = [
        "# HPE RAID Plan Report",
        "",
        f"- Checked at: `{payload.get('checked_at') or 'unknown'}`",
        f"- Status: `{payload.get('status') or 'unknown'}`",
        f"- Source: `{payload.get('source_type') or 'live_probe'}`",
        f"- Current logical drives: `{len(current.get('logical_drives') or [])}`",
        f"- Planned volumes: `{planned.get('volume_count', 0)}`",
        f"- Planned summary: {planned.get('summary') or 'none'}",
        f"- Apply enabled: `{apply_plan.get('apply_enabled')}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = _string_list(payload.get("blockers"))
    lines.extend([f"- {item}" for item in blockers] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    warnings = _string_list(payload.get("warnings"))
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    return "\n".join(lines) + "\n"


def _ilo_reachability_markdown(payload: dict[str, Any]) -> str:
    endpoint = payload.get("endpoint_detection") if isinstance(payload.get("endpoint_detection"), dict) else {}
    legacy = payload.get("legacy_identity") if isinstance(payload.get("legacy_identity"), dict) else {}
    lines = [
        "# iLO Reachability",
        "",
        f"- Checked at: `{payload.get('checked_at') or 'unknown'}`",
        f"- Status: `{payload.get('status') or 'unknown'}`",
        f"- Source: `{payload.get('source_type') or 'live_probe'}`",
        f"- Endpoint classification: `{endpoint.get('classification') or 'not_checked'}`",
        f"- Redfish status: `{endpoint.get('redfish_status') or 'not_checked'}`",
        f"- Legacy status: `{endpoint.get('legacy_status') or 'not_checked'}`",
        f"- Model: `{legacy.get('model') or 'unknown'}`",
        f"- iLO generation: `{legacy.get('ilo_generation') or 'unknown'}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = _string_list(payload.get("blockers"))
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    warnings = _string_list(payload.get("warnings"))
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- None")
    lines.extend(["", "## Not Attempted", ""])
    for item in _string_list(payload.get("not_attempted")):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _esxi_management_markdown(payload: dict[str, Any]) -> str:
    https = payload.get("https_reachability") if isinstance(payload.get("https_reachability"), dict) else {}
    ssh = payload.get("ssh_reachability") if isinstance(payload.get("ssh_reachability"), dict) else {}
    vim = payload.get("vim_service_versions") if isinstance(payload.get("vim_service_versions"), dict) else {}
    lines = [
        "# ESXi Management Validation",
        "",
        f"- Checked at: `{payload.get('checked_at') or 'unknown'}`",
        f"- Status: `{payload.get('status') or 'unknown'}`",
        f"- Source: `{payload.get('source_type') or 'live_probe'}`",
        f"- HTTPS reachable: `{https.get('reachable')}`",
        f"- SSH reachable: `{ssh.get('reachable')}`",
        f"- VIM service versions available: `{vim.get('available')}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = _string_list(payload.get("blockers"))
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    warnings = _string_list(payload.get("warnings"))
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- None")
    lines.extend(["", "## Not Attempted", ""])
    for item in _string_list(payload.get("not_attempted")):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _rel_artifact(path: Any) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _api_stdout_payload(action_id: str, action_payload: Any) -> Any:
    payload = _jsonable(action_payload)
    if not isinstance(payload, dict):
        return payload
    if action_id in {
        "netapp.live-state",
        "netapp.nfs-setup-validate",
        "netapp.iscsi-setup-preview",
        "netapp.iscsi-setup-apply",
        "netapp.iscsi-setup-validate",
    }:
        return _compact_netapp_payload(payload)
    if action_id in {
        "esxi.netapp-datastore-preview",
        "esxi.netapp-datastore-apply",
        "esxi.netapp-datastore-validate",
    }:
        return _compact_datastore_payload(payload)
    if action_id in {
        "esxi.vm-teardown-preview",
        "esxi.vm-teardown-apply",
        "esxi.vm-teardown-validate",
    }:
        return _compact_esxi_vm_teardown_payload(payload)
    if action_id in {
        "esxi.management-validation",
        "esxi.vm-deploy-preview",
        "esxi.vm-deploy-apply",
        "esxi.vm-deploy-validate",
    }:
        return _compact_esxi_payload(payload)
    if action_id == "cisco.current-intent-diff":
        return _compact_cisco_intent_payload(payload)
    if action_id != "cisco.ssh-readonly-probe":
        return payload
    command_results = payload.get("command_results") if isinstance(payload.get("command_results"), dict) else {}
    evidence: dict[str, Any] = {}
    for command in command_results.keys() if isinstance(command_results, dict) else ():
        result = command_results.get(command) if isinstance(command_results, dict) else None
        if not isinstance(result, dict):
            evidence[command] = {"captured": False}
            continue
        evidence[command] = {
            "captured": bool(result.get("captured")),
            "command": result.get("command") or command,
            "line_count": result.get("line_count"),
            "stdout_summary": result.get("stdout_summary") or [],
            "version_hint": result.get("version_hint"),
            "has_vlan_table_header": result.get("has_vlan_table_header"),
            "has_vlan_1": result.get("has_vlan_1"),
        }
    return {
        "provider_id": payload.get("provider_id"),
        "status": payload.get("status"),
        "message": payload.get("message"),
        "fallback": payload.get("fallback"),
        "command_evidence": evidence,
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "not_attempted": payload.get("not_attempted") or [],
    }


def _compact_cisco_intent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else {}
    vlan = diff.get("vlan") if isinstance(diff.get("vlan"), dict) else {}
    guardrails = diff.get("guardrails") if isinstance(diff.get("guardrails"), dict) else {}
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    current_vlans = current.get("vlans") if isinstance(current.get("vlans"), list) else []
    current_ports = current.get("ports") if isinstance(current.get("ports"), list) else []
    return {
        "provider_id": payload.get("provider_id"),
        "action": payload.get("action"),
        "status": payload.get("status"),
        "source_type": payload.get("source_type"),
        "freshness": payload.get("freshness"),
        "checked_at": payload.get("checked_at"),
        "version_hint": payload.get("version_hint"),
        "current_counts": {
            "vlans": len(current_vlans),
            "ports": len(current_ports),
        },
        "diff": {
            "drift_count": diff.get("drift_count"),
            "missing_vlans": vlan.get("missing") or [],
            "unexpected_vlans": vlan.get("unexpected") or [],
            "port_drift_count": len(diff.get("ports") or []),
            "guardrails": {
                area: {
                    "status": evidence.get("status"),
                    "missing": evidence.get("missing") or [],
                }
                for area, evidence in guardrails.items()
                if isinstance(evidence, dict)
            },
            "not_checked": diff.get("not_checked") or [],
        },
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "next_safe_action": payload.get("next_safe_action"),
    }


def _compact_netapp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    management = payload.get("management") if isinstance(payload.get("management"), dict) else {}
    api = payload.get("api") if isinstance(payload.get("api"), dict) else {}
    storage = payload.get("storage") if isinstance(payload.get("storage"), dict) else {}
    protocol_options = payload.get("protocol_options") if isinstance(payload.get("protocol_options"), dict) else {}
    protocol_readiness = (
        payload.get("protocol_readiness") if isinstance(payload.get("protocol_readiness"), dict) else {}
    )
    return {
        "provider_id": payload.get("provider_id"),
        "action": payload.get("action"),
        "status": payload.get("status"),
        "apply_enabled": payload.get("apply_enabled"),
        "protocol_ready": payload.get("protocol_ready") if "protocol_ready" in payload else protocol_readiness.get("ready"),
        "configured": payload.get("configured"),
        "configured_state": payload.get("configured_state"),
        "source_type": payload.get("source_type"),
        "freshness": payload.get("freshness"),
        "is_current": payload.get("is_current"),
        "checked_at": payload.get("checked_at"),
        "management": {
            "cluster_mgmt_ip": management.get("cluster_mgmt_ip"),
            "rest_443_reachable": management.get("rest_443_reachable"),
            "ssh_22_reachable": management.get("ssh_22_reachable"),
        },
        "api": {
            "access_values_present": api.get("access_values_present"),
            "authenticated": api.get("authenticated"),
            "status": api.get("status"),
            "reason": api.get("reason"),
        },
        "storage": {
            "protocol": storage.get("protocol"),
            "ready": storage.get("ready"),
            "service_enabled": storage.get("service_enabled"),
            "nfs_lifs_detected": storage.get("nfs_lifs_detected") or [],
            "iscsi_lifs_detected": storage.get("iscsi_lifs_detected") or [],
        },
        "protocol_options": _compact_protocol_options(protocol_options),
        "planned_iscsi": _compact_iscsi_plan(payload.get("planned_iscsi") or payload.get("iscsi_plan")),
        "validation": _compact_iscsi_validation(payload.get("validation") or payload.get("current_state")),
        "required_gates": payload.get("required_gates") or payload.get("required_flags") or [],
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "next_safe_action": payload.get("next_safe_action"),
        "evidence_artifacts": payload.get("evidence_artifacts") or [],
    }


def _compact_protocol_options(protocol_options: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for protocol in ("nfs", "iscsi"):
        option = protocol_options.get(protocol) if isinstance(protocol_options.get(protocol), dict) else {}
        compact[protocol] = {
            "active": option.get("active"),
            "ready": option.get("ready"),
            "service_enabled": option.get("service_enabled"),
            "service_status": option.get("service_status"),
            "reachable_lif_count": option.get("reachable_lif_count"),
            "lifs": option.get("lifs") or [],
            "blockers": option.get("blockers") or [],
            "warnings": option.get("warnings") or [],
        }
    return compact


def _compact_iscsi_plan(value: Any) -> dict[str, Any]:
    plan = value if isinstance(value, dict) else {}
    return {
        "svm_name": plan.get("svm_name"),
        "lun_path": plan.get("lun_path"),
        "lun_size_gb": plan.get("lun_size_gb"),
        "lun_size": plan.get("lun_size"),
        "igroup_name": plan.get("igroup_name"),
        "datastore_name": plan.get("datastore_name"),
        "target_lifs": plan.get("target_lifs") or plan.get("iscsi_lifs") or [],
        "initiators": plan.get("initiators") or plan.get("initiator_iqns") or [],
    }


def _compact_iscsi_validation(value: Any) -> dict[str, Any]:
    validation = value if isinstance(value, dict) else {}
    return {
        "lun_exists": validation.get("lun_exists") if "lun_exists" in validation else _inventory_object_exists(validation.get("lun")),
        "igroup_exists": (
            validation.get("igroup_exists") if "igroup_exists" in validation else _inventory_object_exists(validation.get("igroup"))
        ),
        "lun_mapped": validation.get("lun_mapped") if "lun_mapped" in validation else _inventory_object_exists(validation.get("lun_map")),
        "initiators_present": validation.get("initiators_present"),
        "target_lifs_reachable": validation.get("target_lifs_reachable"),
    }


def _inventory_object_exists(value: Any) -> bool | None:
    if not isinstance(value, dict):
        return None
    if "exists" in value:
        return bool(value.get("exists"))
    if "found" in value:
        return bool(value.get("found"))
    return None


def _compact_esxi_payload(payload: dict[str, Any]) -> dict[str, Any]:
    https = payload.get("https_reachability") if isinstance(payload.get("https_reachability"), dict) else {}
    ssh = payload.get("ssh_reachability") if isinstance(payload.get("ssh_reachability"), dict) else {}
    vim = payload.get("vim_service_versions") if isinstance(payload.get("vim_service_versions"), dict) else {}
    datastore = payload.get("datastore_check") if isinstance(payload.get("datastore_check"), dict) else {}
    vm = payload.get("vm_check") if isinstance(payload.get("vm_check"), dict) else {}
    plan = payload.get("deployment_plan") if isinstance(payload.get("deployment_plan"), dict) else {}
    return {
        "provider_id": payload.get("provider_id") or payload.get("id"),
        "status": payload.get("status"),
        "source_type": payload.get("source_type"),
        "freshness": payload.get("freshness"),
        "is_current": payload.get("is_current"),
        "checked_at": payload.get("checked_at"),
        "https_reachable": https.get("reachable"),
        "ssh_reachable": ssh.get("reachable"),
        "vim_versions": (vim.get("versions") or [])[:5],
        "target_datastore": plan.get("datastore"),
        "target_vm": plan.get("vm_name"),
        "datastore_visible": datastore.get("exists"),
        "datastore_checked": datastore.get("checked"),
        "vm_visible": vm.get("exists"),
        "vm_checked": vm.get("checked"),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "not_attempted": payload.get("not_attempted") or [],
    }


def _compact_esxi_vm_teardown_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    binding = (
        payload.get("target_binding")
        if isinstance(payload.get("target_binding"), dict)
        else {}
    )
    vm = payload.get("vm_evidence") if isinstance(payload.get("vm_evidence"), dict) else {}
    apply_state = payload.get("apply") if isinstance(payload.get("apply"), dict) else {}
    return {
        "provider_id": payload.get("provider_id"),
        "action": payload.get("action"),
        "status": payload.get("status"),
        "source_type": payload.get("source_type"),
        "freshness": payload.get("freshness"),
        "checked_at": payload.get("checked_at"),
        "apply_enabled": payload.get("apply_enabled"),
        "request": {
            "vm_name": request.get("vm_name"),
            "valid": request.get("valid"),
            "scope": request.get("scope"),
        },
        "target": {
            "configured_target": target.get("configured_target"),
            "govc_target": target.get("govc_target"),
            "targets_match": target.get("targets_match"),
        },
        "target_binding": {
            "checked": binding.get("checked"),
            "freshness": binding.get("freshness"),
            "bound": binding.get("bound"),
            "direct_esxi": binding.get("direct_esxi"),
            "instance_fingerprint": binding.get("instance_fingerprint"),
        },
        "vm_evidence": {
            "checked": vm.get("checked"),
            "freshness": vm.get("freshness"),
            "requested_name": vm.get("requested_name"),
            "exists": vm.get("exists"),
            "absence_confirmed": vm.get("absence_confirmed"),
            "exact_match": vm.get("exact_match"),
            "power_state": vm.get("power_state"),
        },
        "apply": {
            "power_off_attempted": apply_state.get("power_off_attempted"),
            "powered_off_proven": apply_state.get("powered_off_proven"),
            "destroy_attempted": apply_state.get("destroy_attempted"),
            "absence_validation_attempted": apply_state.get(
                "absence_validation_attempted"
            ),
            "absence_confirmed": apply_state.get("absence_confirmed"),
        },
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "next_safe_action": payload.get("next_safe_action"),
    }


def _compact_datastore_payload(payload: dict[str, Any]) -> dict[str, Any]:
    current = payload.get("current_state") if isinstance(payload.get("current_state"), dict) else {}
    target = payload.get("target_state") if isinstance(payload.get("target_state"), dict) else {}
    apply_result = payload.get("apply") if isinstance(payload.get("apply"), dict) else {}
    return {
        "provider_id": payload.get("provider_id"),
        "action": payload.get("action"),
        "status": payload.get("status"),
        "source_type": payload.get("source_type"),
        "freshness": payload.get("freshness"),
        "checked_at": payload.get("checked_at"),
        "apply_enabled": payload.get("apply_enabled"),
        "current_state": {
            "checked": current.get("checked"),
            "exists": current.get("exists"),
            "accessible": current.get("accessible"),
            "name": current.get("name"),
            "url": current.get("url"),
            "access_mode": current.get("access_mode"),
            "type": current.get("type"),
        },
        "target_state": {
            "datastore_name": target.get("datastore_name"),
            "nfs_server": target.get("nfs_server"),
            "nfs_path": target.get("nfs_path"),
            "access_method": target.get("access_method"),
            "can_query": target.get("can_query"),
        },
        "apply": {
            "result": apply_result.get("result"),
            "return_code": apply_result.get("return_code"),
            "apply_mechanism": apply_result.get("apply_mechanism"),
            "govc_datastore_create_attempted": apply_result.get("govc_datastore_create_attempted"),
            "govc_datastore_remove_attempted": apply_result.get("govc_datastore_remove_attempted"),
        },
        "required_gates": payload.get("required_gates") or [],
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "next_safe_action": payload.get("next_safe_action"),
    }


def _guarded_action_context(action_id: str, payload: dict[str, Any]) -> GuardedActionContext:
    confirmed_gates: list[tuple[str, str]] = []
    action = get_workflow_action(action_id)
    allowed_env_gates = {
        gate.strip()
        for gate in _string_list(action.get("required_gates"))
        if "=" in gate and not gate.strip().startswith("=")
    }
    for gate in _string_list(payload.get("confirmed_gates")):
        if "=" not in gate or gate.startswith("="):
            continue
        gate = gate.strip()
        if gate not in allowed_env_gates:
            continue
        key, value = gate.split("=", 1)
        key = key.strip()
        if key:
            confirmed_gates.append((key, _strip_optional_quotes(value.strip())))
    return GuardedActionContext(
        action_id=action_id,
        confirmed_gates=tuple(confirmed_gates),
        confirmation_phrase=_string_or_none(payload.get("confirmation_phrase")),
    )


def _configured_vm_teardown_name() -> str:
    return (
        _string_or_none(os.getenv("VM_TEARDOWN_VM_NAME"))
        or _string_or_none(os.getenv("VM_DEPLOY_VM_NAME"))
        or ""
    )


def _guarded_command_env_overrides(
    action_id: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if action_id == "cisco.apply-bootstrap":
        context = _guarded_action_context(action_id, payload)
        allowed_names = {
            "CISCO_CONSOLE_APPLY_ENABLED",
            "LAB_APPLY_ACK",
            "LAB_TARGET_ACK",
        }
        overrides.update(
            {
                key: value
                for key, value in context.confirmed_gates
                if key in allowed_names
            }
        )
        if context.confirmation_phrase:
            overrides["CISCO_BOOTSTRAP_CONFIRM"] = context.confirmation_phrase
    if action_id in ILO_WRITE_ACTION_IDS:
        ilo_host = _string_or_none(payload.get("ilo_host"))
        if ilo_host:
            overrides["ILO_WRITE_TARGET_HOST"] = ilo_host
    return overrides


def _ilo_write_request_blockers(
    action_id: str,
    payload: dict[str, Any],
) -> list[str]:
    if action_id not in ILO_WRITE_ACTION_IDS:
        return []
    if _string_or_none(payload.get("ilo_host")):
        return []
    return [
        "An explicit current-access ilo_host IP is required before this iLO-backed action can run."
    ]


def _ilo_exact_read_request_blockers(
    action_id: str,
    payload: dict[str, Any],
) -> list[str]:
    if action_id not in ILO_EXACT_READ_ACTION_IDS:
        return []
    if _string_or_none(payload.get("ilo_host")):
        return []
    return [
        "An explicit current-access ilo_host IP is required before this exact-target iLO read can run."
    ]


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _blocked_result(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    blockers: list[str],
) -> dict[str, Any]:
    return _base_result(
        action,
        run_id,
        started_at,
        status="blocked",
        command=_action_command(action),
        executed=False,
        return_code=None,
        stdout_summary="",
        stderr_summary="",
        blockers=blockers,
        warnings=[],
    )


def _base_result(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    *,
    status: str,
    command: str | None,
    executed: bool,
    return_code: int | None,
    stdout_summary: str,
    stderr_summary: str,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    finished_at = _now()
    report_artifacts = _existing_report_artifacts(action.get("reports"))
    guarded = str(action.get("mode") or "") in {"write", "destructive", "upgrade"}
    if status == "completed":
        summary = (
            "Guarded workflow action completed. Review evidence before continuing."
            if guarded
            else "Safe read-only/report-only action completed. Review evidence before using results as current state."
        )
        next_action = "Review evidence artifacts, then continue with the next stage."
    elif status == "blocked":
        if executed:
            summary = (
                "Guarded workflow endpoint ran and reported blockers before provider changes."
                if guarded
                else "Safe read-only/report-only endpoint ran and reported blockers."
            )
        else:
            summary = (
                "Guarded action was not run because required gates were not satisfied."
                if guarded
                else "Action was not run by the safe read-only action runner."
            )
        next_action = blockers[0] if blockers else str(action.get("next_action") or "Review the blocked action.")
    else:
        summary = (
            "Guarded workflow action failed before completing cleanly."
            if guarded
            else "Safe read-only/report-only action failed before completing cleanly."
        )
        next_action = "Review the run trace and evidence, fix the blocker, then run the check again."
    return {
        "run_id": run_id,
        "action_id": action["action_id"],
        "action_label": action["label"],
        "stage_id": action["stage"],
        "stage_label": action["stage_label"],
        "mode": action["mode"],
        "started_at": started_at,
        "finished_at": finished_at,
        "checked_at": finished_at,
        "status": status,
        "source_type": "live_probe",
        "freshness": "current",
        "not_mock": True,
        "command": command,
        "executed": executed,
        "return_code": return_code,
        "stdout_summary": stdout_summary,
        "stderr_summary": stderr_summary,
        "report_artifacts": report_artifacts,
        "trace_artifact": None,
        "summary": summary,
        "blockers": blockers,
        "warnings": warnings,
        "next_action": next_action,
    }


def _run_subprocess(
    command: tuple[str, ...],
    timeout_seconds: int,
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        **(env_overrides or {}),
    }
    command = _resolve_subprocess_executable(command)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        start_new_session=os.name != "nt",
        creationflags=creationflags,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            command,
            timeout_seconds,
            output=stdout,
            stderr=stderr,
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout, stderr=stderr)


def _resolve_subprocess_executable(command: tuple[str, ...]) -> tuple[str, ...]:
    if not command:
        return command
    executable = command[0]
    if (
        os.path.isabs(executable)
        or PureWindowsPath(executable).is_absolute()
        or not any(separator in executable for separator in ("/", "\\"))
    ):
        return command
    candidate = REPO_ROOT.joinpath(*executable.replace("\\", "/").split("/"))
    if _path_exists(candidate):
        return (str(candidate), *command[1:])
    return command


def _normalize_inline_env_command(command: tuple[str, ...]) -> tuple[tuple[str, ...], dict[str, str]]:
    if not command:
        return command, {}
    env_overrides: dict[str, str] = {}
    index = 1 if command[0] == "env" else 0
    while index < len(command):
        item = command[index]
        if "=" not in item or item.startswith("="):
            break
        key, value = item.split("=", 1)
        if not key:
            break
        env_overrides[key] = value
        index += 1
    normalized = command[index:]
    if not normalized:
        return command, {}
    return normalized, env_overrides


def _command_start_blocker(command: tuple[str, ...], exc: OSError) -> str:
    executable = command[0] if command else "command"
    return f"Command `{executable}` could not start: {exc.__class__.__name__}."


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        _terminate_windows_process_tree(process)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=5)


def _terminate_windows_process_tree(process: subprocess.Popen[str]) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            return
        process.wait(timeout=5)


def _action_command(action: dict[str, Any]) -> str | None:
    command = action.get("command")
    if command:
        return str(command)
    endpoint = action.get("api_endpoint")
    if endpoint:
        return f"{action.get('api_method') or 'GET'} {endpoint}"
    return None


def _existing_report_artifacts(paths: Any) -> list[str]:
    return _unique(path for path in _string_list(paths) if _path_exists(REPO_ROOT / path))


def _redacted_summary(text: str, *, max_chars: int = 4000) -> str:
    if not text:
        return ""
    redacted = redact_sensitive(text, _redaction_values())
    lines = str(redacted).splitlines()
    if len(lines) > 80:
        lines = [*lines[:40], "... output truncated ...", *lines[-40:]]
    summary = "\n".join(lines)
    if len(summary) > max_chars:
        return f"{summary[:max_chars]}\n... output truncated ..."
    return summary


def _redaction_values() -> list[str]:
    values: list[str] = []
    if hasattr(settings, "model_dump"):
        settings_data = settings.model_dump()
    elif hasattr(settings, "dict"):
        settings_data = settings.dict()
    elif is_dataclass(settings):
        settings_data = asdict(settings)
    else:
        settings_data = vars(settings)
    for key, value in settings_data.items():
        if _looks_sensitive_key(str(key)) and value:
            if isinstance(value, list | tuple):
                values.extend(str(item) for item in value if item)
            else:
                values.append(str(value))
    for key, value in os.environ.items():
        if _looks_sensitive_key(key) and value and len(value) >= 3:
            values.append(value)
    return _unique(values)


def _looks_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(fragment in lower for fragment in ("password", "token", "secret", "credential", "authorization", "cookie"))


def _output_warnings(stdout_summary: str, stderr_summary: str) -> list[str]:
    warnings = ["Output was redacted and truncated for operator display."]
    if stderr_summary:
        warnings.append("stderr summary is available in the run trace.")
    if "REDACTED" in stdout_summary or "REDACTED" in stderr_summary:
        warnings.append("Sensitive-looking values were redacted.")
    return warnings


def _command_report_gate(
    action: dict[str, Any],
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> tuple[str, list[str], list[str]]:
    if action.get("action_id") != "operator-readonly-sweep.real-lab" or status != "completed":
        return status, blockers, warnings
    report_path = REPO_ROOT / "artifacts" / "real-lab" / "operator-readonly-sweep-latest.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return status, blockers, warnings
    gate = report.get("quality_gate") if isinstance(report, dict) else None
    if not isinstance(gate, dict):
        return status, blockers, warnings
    gate_status = str(gate.get("status") or "").lower()
    if gate_status == "blocked":
        blocked_actions = _string_list(gate.get("blocked_actions"))
        return (
            "blocked",
            [f"Read-only sweep reported lab blockers: {', '.join(blocked_actions) or 'see sweep report'}."],
            _unique([*warnings, *_string_list(gate.get("warning_actions"))]),
        )
    if gate_status == "failed":
        failed_actions = _string_list(gate.get("failed_actions"))
        return (
            "failed",
            [f"Read-only sweep failed before usable evidence for: {', '.join(failed_actions) or 'see sweep report'}."],
            _unique([*warnings, *_string_list(gate.get("warning_actions"))]),
        )
    optional_blocked_actions = _string_list(gate.get("optional_blocked_actions"))
    if optional_blocked_actions:
        optional_warning = (
            "Read-only sweep passed the required path, but optional parity checks reported blockers: "
            f"{', '.join(optional_blocked_actions)}."
        )
        return status, blockers, _unique([*warnings, optional_warning, *_string_list(gate.get("warning_actions"))])
    return status, blockers, warnings


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _decode_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _compact_run_history_trace(trace: dict[str, Any]) -> dict[str, Any]:
    compact = dict(trace)
    compact["stdout_summary"] = _redacted_summary(str(trace.get("stdout_summary") or ""), max_chars=600)
    compact["stderr_summary"] = _redacted_summary(str(trace.get("stderr_summary") or ""), max_chars=600)
    compact["report_artifacts"] = _unique(_string_list(trace.get("report_artifacts"))[:10])
    return compact


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _unique(values: Any) -> list[Any]:
    return unique_preserving_order(values, skip_falsey=True)
