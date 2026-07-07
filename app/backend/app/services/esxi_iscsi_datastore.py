from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.redaction import redact_sensitive
from app.services.esxi_netapp_datastore import _run_esxi_ssh, _ssh_target_state
from app.services.json_file_store import write_json_object, write_text_value
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.netapp_iscsi_setup import build_netapp_iscsi_setup_preview, validate_netapp_iscsi_setup
from app.services.path_utils import repo_relative_path

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

ISCSI_DATASTORE_PREVIEW_REPORT = CODEX_RUN_DIR / "esxi-iscsi-datastore-preview-report.md"
ISCSI_DATASTORE_PREVIEW_JSON = CODEX_RUN_DIR / "esxi-iscsi-datastore-preview-redacted.json"
ISCSI_DATASTORE_VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-iscsi-datastore-validation-report.md"
ISCSI_DATASTORE_VALIDATION_JSON = CODEX_RUN_DIR / "esxi-iscsi-datastore-validation-redacted.json"


def build_esxi_iscsi_datastore_preview(*, write_report: bool = True) -> dict[str, Any]:
    return _build_payload(action="esxi-iscsi-datastore-preview", preview_only=True, write_report=write_report)


def validate_esxi_iscsi_datastore(*, write_report: bool = True) -> dict[str, Any]:
    return _build_payload(action="esxi-iscsi-datastore-validation", preview_only=False, write_report=write_report)


def _build_payload(*, action: str, preview_only: bool, write_report: bool) -> dict[str, Any]:
    target = _ssh_target_state()
    netapp_preview = build_netapp_iscsi_setup_preview(write_report=False)
    netapp_validation = validate_netapp_iscsi_setup(write_report=False)
    plan = _plan(netapp_preview)
    evidence = _esxi_iscsi_evidence(plan, target) if target.get("can_query") else _skipped_evidence()
    blockers = _blockers(plan, target, evidence, netapp_validation, preview_only=preview_only)
    remediation_plan = _remediation_plan(plan, target, evidence, netapp_validation, blockers, preview_only=preview_only)
    status = "blocked" if blockers else "preview_ready" if preview_only else "ready"
    payload = {
        "provider_id": "esxi-readonly",
        "action": action,
        "checked_at": _now(),
        "status": status,
        "message": (
            "ESXi iSCSI datastore preview completed with read-only ESXi checks."
            if preview_only
            else "ESXi iSCSI datastore validation completed with read-only ESXi checks."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if evidence.get("checked") else "not_checked",
        "freshness": "current" if evidence.get("checked") else "not_checked",
        "target_state": {
            "host": settings.esxi_test_host,
            "access_method": "ssh-esxcli" if target.get("can_query") else "none",
            "ssh_available": bool(target.get("can_query")),
            "missing_fields": target.get("missing_fields") or [],
        },
        "iscsi_plan": plan,
        "netapp_validation": {
            "status": netapp_validation.get("status"),
            "blockers": netapp_validation.get("blockers") or [],
            "protocol_readiness": netapp_validation.get("protocol_readiness"),
            "current_state": netapp_validation.get("current_state"),
        },
        "current_state": evidence,
        "remediation_plan": remediation_plan,
        "blockers": blockers,
        "warnings": [
            "Read-only only. No ESXi iSCSI login, target add, adapter rescan, VMFS creation, datastore mount, or vCenter registration was attempted.",
        ],
        "not_attempted": [
            "esxcli iscsi adapter discovery sendtarget add",
            "esxcli storage core adapter rescan",
            "VMFS format",
            "datastore create or mount",
            "vCenter registration",
        ],
        "artifacts": {
            "report": _rel(ISCSI_DATASTORE_PREVIEW_REPORT if preview_only else ISCSI_DATASTORE_VALIDATION_REPORT),
            "json": _rel(ISCSI_DATASTORE_PREVIEW_JSON if preview_only else ISCSI_DATASTORE_VALIDATION_JSON),
        },
        "next_safe_action": (
            "Resolve NetApp iSCSI object and ESXi login/session blockers before designing the guarded VMFS mount lane."
            if blockers
            else "ESXi can see the intended iSCSI datastore path; keep write/mount work behind a separate guarded apply lane."
        ),
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        _write_payload(
            ISCSI_DATASTORE_PREVIEW_JSON if preview_only else ISCSI_DATASTORE_VALIDATION_JSON,
            ISCSI_DATASTORE_PREVIEW_REPORT if preview_only else ISCSI_DATASTORE_VALIDATION_REPORT,
            sanitized,
        )
    return sanitized


def _plan(netapp_preview: dict[str, Any]) -> dict[str, Any]:
    iscsi_plan = netapp_preview.get("iscsi_plan") if isinstance(netapp_preview.get("iscsi_plan"), dict) else {}
    return {
        "datastore_name": str(iscsi_plan.get("datastore_name") or os.getenv("ESXI_ISCSI_DATASTORE_NAME") or "netapp_iscsi_ds01"),
        "vmfs_version": str(iscsi_plan.get("vmfs_version") or os.getenv("ESXI_ISCSI_VMFS_VERSION") or "VMFS6"),
        "target_iqn": _nested_string(netapp_preview, ["current_state", "iscsi_service", "target_iqn"]),
        "preferred_iscsi_lif": iscsi_plan.get("preferred_iscsi_lif"),
        "iscsi_lifs": unique_strings(iscsi_plan.get("iscsi_lifs")),
        "lun_path": iscsi_plan.get("lun_path"),
        "lun_name": iscsi_plan.get("lun_name"),
        "igroup_name": iscsi_plan.get("igroup_name"),
        "initiator_iqns": unique_strings(iscsi_plan.get("initiator_iqns")),
    }


def _esxi_iscsi_evidence(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    commands = {
        "adapter_list": "esxcli iscsi adapter list",
        "iscsi_path_list": "esxcli iscsi session list",
        "device_list": "esxcli storage core device list",
        "filesystem_list": "esxcli storage filesystem list",
    }
    results = {key: _run_esxi_ssh(command, timeout=60) for key, command in commands.items()}
    adapters = _adapter_names(str(results["adapter_list"].get("stdout") or ""))
    sessions = _session_summaries(str(results["iscsi_path_list"].get("stdout") or ""))
    datastore = _datastore_summary(plan["datastore_name"], str(results["filesystem_list"].get("stdout") or ""))
    return {
        "checked": True,
        "command_return_codes": {key: result.get("return_code") for key, result in results.items()},
        "adapter_count": len(adapters),
        "adapters": adapters,
        "iscsi_path_count": len(sessions),
        "iscsi_paths": sessions,
        "target_iqn_seen": _target_iqn_seen(plan.get("target_iqn"), sessions, str(results["iscsi_path_list"].get("stdout") or "")),
        "datastore": datastore,
        "datastore_visible": bool(datastore),
        "device_evidence": _device_evidence(plan, str(results["device_list"].get("stdout") or "")),
        "stderr": "\n".join(unique_strings([result.get("stderr") for result in results.values()])) or None,
        "access_method": "ssh-esxcli",
        "ssh_target": target.get("host"),
    }


def _skipped_evidence() -> dict[str, Any]:
    return {
        "checked": False,
        "adapter_count": 0,
        "adapters": [],
        "iscsi_path_count": 0,
        "iscsi_paths": [],
        "target_iqn_seen": False,
        "datastore": None,
        "datastore_visible": False,
        "device_evidence": {"matched": False, "reason": "ESXi SSH was not available."},
    }


def _blockers(
    plan: dict[str, Any],
    target: dict[str, Any],
    evidence: dict[str, Any],
    netapp_validation: dict[str, Any],
    *,
    preview_only: bool,
) -> list[str]:
    blockers: list[str] = []
    if target.get("missing_fields"):
        blockers.append(f"ESXi SSH target is not ready: {', '.join(unique_strings(target.get('missing_fields')))}.")
    if not plan.get("target_iqn"):
        blockers.append("NetApp target IQN is not available from iSCSI validation.")
    if not plan.get("initiator_iqns"):
        blockers.append("ESXi iSCSI initiator IQN is not available for igroup validation.")
    blockers.extend(unique_strings(netapp_validation.get("blockers")))
    if not evidence.get("checked"):
        return unique_preserving_order(blockers)
    if not evidence.get("adapters"):
        blockers.append("ESXi has no iSCSI adapter listed.")
    if plan.get("target_iqn") and not evidence.get("target_iqn_seen"):
        blockers.append("ESXi does not show an active iSCSI session to the NetApp target IQN.")
    if not preview_only and not evidence.get("datastore_visible"):
        blockers.append(f"ESXi VMFS datastore `{plan['datastore_name']}` is not visible.")
    return unique_preserving_order(blockers)


def _remediation_plan(
    plan: dict[str, Any],
    target: dict[str, Any],
    evidence: dict[str, Any],
    netapp_validation: dict[str, Any],
    blockers: list[str],
    *,
    preview_only: bool,
) -> dict[str, Any]:
    netapp_blockers = unique_strings(netapp_validation.get("blockers"))
    steps = [
        {
            "label": "Confirm ONTAP SAN objects",
            "status": "blocked" if netapp_blockers or not plan.get("target_iqn") else "ready",
            "detail": (
                netapp_blockers[0]
                if netapp_blockers
                else f"Target IQN {plan.get('target_iqn') or 'not discovered'} with LUN {plan.get('lun_name') or 'not planned'}."
            ),
            "next_action": "Validate NetApp iSCSI until target IQN, LUN, igroup, and LUN map are present.",
        },
        {
            "label": "Confirm ESXi iSCSI adapter",
            "status": _step_status(bool(target.get("can_query")) and bool(evidence.get("adapters"))),
            "detail": (
                f"{evidence.get('adapter_count') or 0} adapter(s): {', '.join(unique_strings(evidence.get('adapters'))) or 'none'}."
                if evidence.get("checked")
                else "ESXi SSH evidence was not available."
            ),
            "next_action": "Enable the ESXi software iSCSI adapter before target discovery if no adapter is listed.",
        },
        {
            "label": "Discover NetApp target portal",
            "status": _step_status(bool(plan.get("iscsi_lifs"))),
            "detail": f"Planned iSCSI LIFs: {', '.join(unique_strings(plan.get('iscsi_lifs'))) or 'none discovered'}.",
            "next_action": "Confirm ESXi vmkernel networking can reach the NetApp iSCSI LIFs on TCP/3260.",
        },
        {
            "label": "Establish active iSCSI session",
            "status": _step_status(bool(evidence.get("target_iqn_seen"))),
            "detail": (
                f"{evidence.get('iscsi_path_count') or 0} active path(s); target IQN seen: {bool(evidence.get('target_iqn_seen'))}."
                if evidence.get("checked")
                else "Run Preview ESXi iSCSI to read live session evidence."
            ),
            "next_action": "Add the NetApp target portal, rescan the iSCSI adapter, and confirm an active session to the target IQN.",
        },
        {
            "label": "Confirm VMFS datastore visibility",
            "status": "ready" if evidence.get("datastore_visible") else ("warning" if preview_only else "blocked"),
            "detail": (
                f"Datastore {plan.get('datastore_name')} is visible."
                if evidence.get("datastore_visible")
                else f"Datastore {plan.get('datastore_name')} is not visible to ESXi."
            ),
            "next_action": "After the LUN is visible, run the guarded datastore create or mount lane and revalidate VMFS visibility.",
        },
    ]
    open_steps = [step for step in steps if step["status"] != "ready"]
    return {
        "status": "blocked" if blockers and not preview_only else "warning" if open_steps else "ready",
        "summary": (
            "ESXi iSCSI path is ready; keep create/mount work behind the guarded apply lane."
            if not open_steps
            else f"{len(open_steps)} iSCSI remediation step(s) need attention before VMFS can be treated as ready."
        ),
        "read_only": True,
        "apply_not_attempted": [
            "target portal add",
            "iSCSI login",
            "adapter rescan",
            "VMFS create or mount",
        ],
        "steps": steps,
    }


def _step_status(ready: bool) -> str:
    return "ready" if ready else "blocked"


def _adapter_names(stdout: str) -> list[str]:
    names: list[str] = []
    for line in stdout.splitlines():
        match = re.match(r"^\s*(vmhba\S+)\s+", line)
        if match:
            names.append(match.group(1))
    return unique_strings(names)


def _session_summaries(stdout: str) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in stdout.splitlines():
        if not line.strip():
            if current:
                sessions.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        current[normalized] = value.strip()
    if current:
        sessions.append(current)
    return sessions


def _target_iqn_seen(target_iqn: Any, sessions: list[dict[str, Any]], stdout: str) -> bool:
    if not target_iqn:
        return False
    needle = str(target_iqn).lower()
    if needle in stdout.lower():
        return True
    return any(needle in " ".join(str(value).lower() for value in session.values()) for session in sessions)


def _datastore_summary(datastore_name: str, stdout: str) -> dict[str, Any] | None:
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) > 4 and parts[1] == datastore_name:
            return {
                "name": datastore_name,
                "mount_point": parts[0],
                "uuid": parts[2],
                "mounted": _parse_bool(parts[3]),
                "type": parts[4],
                "capacity": _parse_int(parts[5]) if len(parts) > 5 else None,
                "free_space": _parse_int(parts[6]) if len(parts) > 6 else None,
            }
    return None


def _device_evidence(plan: dict[str, Any], stdout: str) -> dict[str, Any]:
    target_iqn = str(plan.get("target_iqn") or "").lower()
    lun_name = str(plan.get("lun_name") or "").lower()
    text = stdout.lower()
    matched = bool((target_iqn and target_iqn in text) or (lun_name and lun_name in text))
    return {
        "matched": matched,
        "reason": "Matched target IQN or LUN name in ESXi storage device list." if matched else "No target IQN or LUN name was found in ESXi storage device list.",
    }


def _parse_bool(value: Any) -> bool | None:
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _parse_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _nested_string(payload: dict[str, Any], keys: list[str]) -> str | None:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    text = str(current).strip() if current is not None else ""
    return text or None


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any]) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(json_path, payload)
    write_text_value(report_path, _markdown(payload))


def _markdown(payload: dict[str, Any]) -> str:
    current = payload.get("current_state") if isinstance(payload.get("current_state"), dict) else {}
    plan = payload.get("iscsi_plan") if isinstance(payload.get("iscsi_plan"), dict) else {}
    lines = [
        "# ESXi iSCSI Datastore Evidence",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Source: `{payload.get('source_type')}` / `{payload.get('freshness')}`",
        f"- Datastore: `{plan.get('datastore_name')}`",
        f"- Target IQN seen: `{current.get('target_iqn_seen')}`",
        f"- Datastore visible: `{current.get('datastore_visible')}`",
        f"- iSCSI adapters: `{current.get('adapter_count')}`",
        f"- iSCSI paths: `{current.get('iscsi_path_count')}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = unique_strings(payload.get("blockers"))
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- None")
    remediation = payload.get("remediation_plan") if isinstance(payload.get("remediation_plan"), dict) else {}
    lines.extend(["", "## Remediation Plan", ""])
    lines.append(f"- Status: `{remediation.get('status') or 'not_checked'}`")
    lines.append(f"- Summary: {remediation.get('summary') or 'No remediation plan generated.'}")
    for step in remediation.get("steps") if isinstance(remediation.get("steps"), list) else []:
        if isinstance(step, dict):
            lines.append(f"- `{step.get('status')}` {step.get('label')}: {step.get('next_action')}")
    lines.extend(["", "## Not Attempted", ""])
    lines.extend(f"- {item}" for item in unique_strings(payload.get("not_attempted")))
    lines.append("")
    return "\n".join(lines)


def _rel(path: Path) -> str:
    try:
        return repo_relative_path(path, REPO_ROOT)
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()
