from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.esxi_vm_deploy import _govc_binary, _govc_env, _run_govc

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
PREVIEW_REPORT = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-preview-report.md"
PREVIEW_JSON = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-preview-redacted.json"
APPLY_REPORT = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-apply-report.md"
APPLY_JSON = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-apply-redacted.json"
VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-validation-report.md"
VALIDATION_JSON = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-validation-redacted.json"

DATASTORE_CONFIRM_PHRASE = "MOUNT NETAPP NFS DATASTORE"


def build_esxi_netapp_datastore_preview(*, write_report: bool = True) -> dict[str, Any]:
    plan = _mount_plan()
    target = _target_state()
    current = _datastore_info(plan) if target["can_query"] else _skipped_datastore_info()
    blockers = _preview_blockers(plan, target, current)
    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-netapp-datastore-preview",
        "checked_at": _now(),
        "status": "blocked" if blockers else "preview_ready",
        "message": "NetApp NFS datastore mount preview generated. No ESXi, NetApp, or vCenter write action was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if current.get("checked") else "live_cached",
        "freshness": "current",
        "current_state": current,
        "target_state": plan,
        "required_flags": _required_flags(),
        "command_preview": _command_preview(plan),
        "blockers": blockers,
        "warnings": _warnings(),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(PREVIEW_REPORT),
            "json": _rel(PREVIEW_JSON),
            "apply_report": _rel(APPLY_REPORT),
            "validation_report": _rel(VALIDATION_REPORT),
        },
        "next_safe_action": (
            "Resolve ESXi/govc blockers, then run guarded datastore apply."
            if blockers
            else "Run guarded datastore apply if this mount target is correct."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(PREVIEW_JSON, PREVIEW_REPORT, sanitized, _markdown)
    return sanitized


def apply_esxi_netapp_datastore(*, write_report: bool = True) -> dict[str, Any]:
    plan = _mount_plan()
    target = _target_state()
    current = _datastore_info(plan) if target["can_query"] else _skipped_datastore_info()
    gates = _apply_gates(plan, target, current)
    apply_result = {
        "govc_datastore_create_attempted": False,
        "return_code": None,
        "result": "not_attempted",
    }
    blockers = list(gates["blockers"])
    status = "blocked" if blockers else "ready_to_apply"
    message = (
        "NetApp datastore apply was refused before any govc datastore.create command."
        if blockers
        else "NetApp datastore apply gates passed; running guarded govc datastore.create."
    )

    if not blockers:
        if current.get("exists") and current.get("accessible"):
            status = "ready"
            message = "NetApp NFS datastore is already mounted and accessible on ESXi."
            apply_result["result"] = "already_mounted"
        else:
            result = _run_govc(_govc_create_args(plan), env=_govc_env(), timeout=120)
            apply_result = {
                "govc_datastore_create_attempted": True,
                "return_code": result["return_code"],
                "result": "completed" if result["return_code"] == 0 else "failed",
                "stderr": result.get("stderr"),
            }
            if result["return_code"] == 0:
                after = _datastore_info(plan)
                current = after
                status = "mounted" if after.get("exists") else "warning"
                message = "NetApp NFS datastore mount command completed."
                if not after.get("exists"):
                    blockers.append("govc datastore.create returned success, but datastore.info did not confirm the datastore.")
            else:
                status = "failed"
                message = "govc datastore.create failed."
                blockers.append("govc datastore.create failed.")

    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-netapp-datastore-apply",
        "checked_at": _now(),
        "status": status,
        "message": message,
        "mode": settings.provider_mode,
        "apply_enabled": not gates["blockers"],
        "source_type": "live_probe" if current.get("checked") else "live_cached",
        "freshness": "current",
        "current_state": current,
        "target_state": plan,
        "flag_state": gates["flag_state"],
        "required_flags": _required_flags(),
        "command_preview": _command_preview(plan),
        "apply": apply_result,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": _warnings(),
        "not_attempted": _not_attempted(apply_result.get("govc_datastore_create_attempted") is True),
        "artifacts": {
            "report": _rel(APPLY_REPORT),
            "json": _rel(APPLY_JSON),
            "validation_report": _rel(VALIDATION_REPORT),
        },
        "next_safe_action": (
            "Run datastore validation and then VM deployment preview."
            if status in {"mounted", "ready"}
            else "Restore ESXi management/govc access, then rerun datastore apply."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(APPLY_JSON, APPLY_REPORT, sanitized, _markdown)
    return sanitized


def validate_esxi_netapp_datastore(*, write_report: bool = True) -> dict[str, Any]:
    plan = _mount_plan()
    target = _target_state()
    current = _datastore_info(plan) if target["can_query"] else _skipped_datastore_info()
    blockers = []
    if not target["can_query"]:
        blockers.append(_target_blocker(target))
    if target["can_query"] and not current.get("exists"):
        blockers.append(f"Datastore `{plan['datastore_name']}` is not visible to ESXi govc.")
    if current.get("exists") and current.get("accessible") is False:
        blockers.append(f"Datastore `{plan['datastore_name']}` is visible but not accessible.")
    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-netapp-datastore-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp NFS datastore validation completed with read-only govc checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if current.get("checked") else "live_cached",
        "freshness": "current",
        "current_state": current,
        "target_state": plan,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": _warnings(),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(VALIDATION_REPORT),
            "json": _rel(VALIDATION_JSON),
            "apply_report": _rel(APPLY_REPORT),
        },
        "next_safe_action": (
            "Deploy the selected OVF/OVA to the NetApp datastore."
            if not blockers
            else "Mount the NetApp NFS datastore after ESXi management is reachable."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(VALIDATION_JSON, VALIDATION_REPORT, sanitized, _markdown)
    return sanitized


def _mount_plan() -> dict[str, Any]:
    nfs_lifs = list(settings.netapp_nfs_lifs)
    remote_host = os.getenv("ESXI_NETAPP_DATASTORE_REMOTE_HOST") or (nfs_lifs[0] if nfs_lifs else None)
    return {
        "datastore_name": os.getenv("ESXI_NETAPP_DATASTORE_NAME") or settings.netapp_nfs_datastore_name,
        "remote_host": remote_host,
        "remote_path": os.getenv("ESXI_NETAPP_DATASTORE_REMOTE_PATH") or settings.netapp_nfs_mount_path,
        "nfs_version": os.getenv("ESXI_NETAPP_DATASTORE_NFS_VERSION", "nfs"),
        "netapp_nfs_lifs": nfs_lifs,
    }


def _target_state() -> dict[str, Any]:
    env = _govc_env()
    missing = []
    if not settings.esxi_configured:
        missing.append("ESXI_CONFIGURED=true")
    if not env.get("GOVC_URL"):
        missing.append("GOVC_URL or ESXI_TEST_HOST")
    if not env.get("GOVC_USERNAME"):
        missing.append("GOVC_USERNAME or ESXI_TEST_USERNAME")
    if not env.get("GOVC_PASSWORD"):
        missing.append("GOVC_PASSWORD or ESXI_TEST_PASSWORD")
    govc = _govc_binary()
    if not govc:
        missing.append("govc")
    about = {"return_code": None, "stderr": None}
    if govc and not missing:
        about = _run_govc(["about"], env=env, timeout=15)
        if about["return_code"] != 0:
            missing.append("reachable ESXi govc endpoint")
    return {
        "provider_mode": settings.provider_mode,
        "esxi_configured": settings.esxi_configured,
        "govc_available": bool(govc),
        "govc_url_configured": bool(env.get("GOVC_URL")),
        "username_configured": bool(env.get("GOVC_USERNAME")),
        "credential_configured": bool(env.get("GOVC_PASSWORD")),
        "govc_about": about,
        "missing_fields": missing,
        "can_query": bool(govc and not missing),
    }


def _datastore_info(plan: dict[str, Any]) -> dict[str, Any]:
    result = _run_govc(["datastore.info", "-json", plan["datastore_name"]], env=_govc_env(), timeout=30)
    summary = _datastore_summary(result.get("stdout"))
    return {
        "checked": True,
        "exists": result["return_code"] == 0,
        "accessible": summary.get("accessible") if summary else None,
        "return_code": result["return_code"],
        "stderr": result.get("stderr"),
        "summary": summary,
    }


def _datastore_summary(stdout: str | None) -> dict[str, Any] | None:
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    datastores = payload.get("Datastores") if isinstance(payload, dict) else None
    if not isinstance(datastores, list) or not datastores:
        return None
    summary = datastores[0].get("Summary") if isinstance(datastores[0], dict) else None
    if not isinstance(summary, dict):
        return None
    return {
        "name": summary.get("Name"),
        "type": summary.get("Type"),
        "accessible": summary.get("Accessible"),
        "capacity": summary.get("Capacity"),
        "free_space": summary.get("FreeSpace"),
    }


def _skipped_datastore_info() -> dict[str, Any]:
    return {
        "checked": False,
        "exists": False,
        "accessible": None,
        "return_code": None,
        "stderr": None,
        "summary": None,
    }


def _preview_blockers(plan: dict[str, Any], target: dict[str, Any], current: dict[str, Any]) -> list[str]:
    blockers = []
    if not plan["datastore_name"]:
        blockers.append("NETAPP_NFS_DATASTORE_NAME or ESXI_NETAPP_DATASTORE_NAME is required.")
    if not plan["remote_host"]:
        blockers.append("NETAPP_NFS_LIFS or ESXI_NETAPP_DATASTORE_REMOTE_HOST is required.")
    if not plan["remote_path"]:
        blockers.append("NETAPP_NFS_MOUNT_PATH or ESXI_NETAPP_DATASTORE_REMOTE_PATH is required.")
    if not target["can_query"]:
        blockers.append(_target_blocker(target))
    if current.get("exists") and current.get("accessible") is False:
        blockers.append(f"Datastore `{plan['datastore_name']}` exists but is not accessible.")
    return list(dict.fromkeys(blockers))


def _target_blocker(target: dict[str, Any]) -> str:
    missing = target.get("missing_fields") or []
    if missing:
        return f"ESXi govc target is not ready: {', '.join(missing)}."
    return "ESXi govc target is not ready."


def _apply_gates(plan: dict[str, Any], target: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "datastore_apply": os.getenv("ESXI_NETAPP_DATASTORE_APPLY") == "true",
        "datastore_confirm": os.getenv("ESXI_NETAPP_DATASTORE_CONFIRM") == DATASTORE_CONFIRM_PHRASE,
    }
    blockers = policy.action_blockers("esxi.datastore-vswitch-vmkernel", ActionCategory.STORAGE_CONFIG)
    blockers.extend(_preview_blockers(plan, target, current))
    if not flag_state["datastore_apply"]:
        blockers.append("ESXI_NETAPP_DATASTORE_APPLY=true is required.")
    if not flag_state["datastore_confirm"]:
        blockers.append(f'ESXI_NETAPP_DATASTORE_CONFIRM="{DATASTORE_CONFIRM_PHRASE}" is required.')
    return {"flag_state": flag_state, "blockers": list(dict.fromkeys(blockers))}


def _govc_create_args(plan: dict[str, Any]) -> list[str]:
    datastore_type = "-type"
    datastore_kind = "nfs41" if str(plan.get("nfs_version")).lower() == "nfs41" else "nfs"
    return [
        "datastore.create",
        datastore_type,
        datastore_kind,
        "-name",
        plan["datastore_name"],
        "-remote-host",
        plan["remote_host"],
        "-remote-path",
        plan["remote_path"],
    ]


def _command_preview(plan: dict[str, Any]) -> list[str]:
    return [
        f"govc datastore.info -json {plan['datastore_name']}",
        " ".join(["govc", *_govc_create_args(plan)]),
        f"govc datastore.info -json {plan['datastore_name']}",
    ]


def _required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "ESXI_NETAPP_DATASTORE_APPLY=true",
        f'ESXI_NETAPP_DATASTORE_CONFIRM="{DATASTORE_CONFIRM_PHRASE}"',
    ]


def _warnings() -> list[str]:
    return [
        "Datastore apply only runs govc datastore.create; it does not create ONTAP exports or change ESXi networking.",
        "NFS v3 is the default mount type for this lab workflow; set ESXI_NETAPP_DATASTORE_NFS_VERSION=nfs41 only after validation.",
    ]


def _not_attempted(apply_attempted: bool = False) -> list[str]:
    skipped = [
        "ONTAP volume/export changes",
        "vCenter operation",
        "VM deploy/power operation",
        "ESXi host reboot",
        "ESXi networking changes",
    ]
    if not apply_attempted:
        skipped.insert(0, "govc datastore.create")
    return skipped


def _markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target_state") or {}
    current = payload.get("current_state") or {}
    lines = [
        "# ESXi NetApp NFS Datastore Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Action: `{payload.get('action')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Current State",
        f"- Checked: `{current.get('checked')}`",
        f"- Exists: `{current.get('exists')}`",
        f"- Accessible: `{current.get('accessible')}`",
        "",
        "## Target State",
        f"- Datastore: `{target.get('datastore_name')}`",
        f"- Remote host: `{target.get('remote_host')}`",
        f"- Remote path: `{target.get('remote_path')}`",
        "",
        "## Command Preview",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("command_preview") or [])
    lines.extend(["", "## Required Flags"])
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- No datastore, ESXi, NetApp, vCenter, or VM write is run unless apply gates pass."])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown_builder(payload), encoding="utf-8")


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for key, value in os.environ.items()
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie"))
    ]


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat()
