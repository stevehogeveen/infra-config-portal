from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.netapp_real_lab import get_netapp_nfs_vcenter_readiness
from app.services.netapp_state import get_netapp_runtime_state

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

NFS_PREVIEW_REPORT = CODEX_RUN_DIR / "netapp-nfs-setup-preview-report.md"
NFS_PREVIEW_JSON = CODEX_RUN_DIR / "netapp-nfs-setup-preview-redacted.json"
NFS_APPLY_REPORT = CODEX_RUN_DIR / "netapp-nfs-setup-apply-report.md"
NFS_APPLY_JSON = CODEX_RUN_DIR / "netapp-nfs-setup-apply-redacted.json"
NFS_VALIDATION_REPORT = CODEX_RUN_DIR / "netapp-nfs-setup-validation-report.md"
NFS_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-nfs-setup-validation-redacted.json"

NFS_SETUP_CONFIRM_PHRASE = "APPLY NETAPP NFS SETUP"


def build_netapp_nfs_setup_preview(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    plan = _nfs_plan()
    blockers = _preview_blockers(runtime_state, plan)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "nfs-setup-preview",
        "checked_at": checked_at,
        "status": "blocked" if blockers else "preview_only",
        "message": "NetApp NFS setup preview generated. No ONTAP, ESXi, vCenter, or storage write action was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_cached",
        "freshness": "current",
        "configured_state": runtime_state.get("configured_state"),
        "configured": bool(runtime_state.get("configured")),
        "api_access_present": _api_access_present(),
        "nfs_plan": plan,
        "exact_changes": _exact_changes(plan),
        "rest_preview": _rest_preview(plan),
        "required_flags": _required_flags(),
        "blockers": blockers,
        "warnings": [
            "Preview only. No SVM, NFS service, LIF, volume, export policy, export rule, datastore, or iSCSI action was run.",
            "This operation is NFS-only; future iSCSI LIFs are intentionally ignored.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(NFS_PREVIEW_REPORT),
            "json": _rel(NFS_PREVIEW_JSON),
        },
        "next_safe_action": (
            "Resolve blockers, rerun live validation, then run guarded NFS setup apply only from an attended real-lab session."
            if blockers
            else "Review the NFS setup preview and set the explicit apply flags only when ready."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(NFS_PREVIEW_JSON, NFS_PREVIEW_REPORT, sanitized, _preview_markdown)
    return sanitized


def apply_netapp_nfs_setup(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    plan = _nfs_plan()
    gates = _apply_gates(runtime_state, plan)
    blocked = bool(gates["blockers"])
    rest_apply = _rest_apply_not_attempted("Apply gates blocked before ONTAP REST session started.")
    if not blocked:
        rest_apply = _ensure_nfs_export_rule(plan)
        blocked = rest_apply["status"] == "failed"
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "nfs-setup-apply",
        "checked_at": checked_at,
        "status": "blocked" if gates["blockers"] else rest_apply["status"],
        "message": (
            "NetApp NFS setup apply was refused before any ONTAP or datastore write command."
            if gates["blockers"]
            else rest_apply["message"]
        ),
        "mode": settings.provider_mode,
        "apply_enabled": not bool(gates["blockers"]),
        "source_type": "live_cached",
        "freshness": "current",
        "configured_state": runtime_state.get("configured_state"),
        "configured": bool(runtime_state.get("configured")),
        "api_access_present": _api_access_present(),
        "flag_state": gates["flag_state"],
        "nfs_plan": plan,
        "exact_changes": _exact_changes(plan),
        "rest_preview": _rest_preview(plan),
        "required_flags": _required_flags(),
        "apply": {
            "ontap_writes_attempted": bool(rest_apply.get("ontap_writes_attempted")),
            "esxi_writes_attempted": False,
            "vcenter_writes_attempted": False,
            "transcript_summary": list(rest_apply.get("transcript_summary") or []),
            "rest_result": rest_apply,
        },
        "blockers": gates["blockers"] + list(rest_apply.get("blockers") or []),
        "warnings": [
            "No secrets are printed or written to the apply report.",
            "Run NFS validation after a guarded NFS setup session completes.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(NFS_APPLY_REPORT),
            "json": _rel(NFS_APPLY_JSON),
        },
        "next_safe_action": (
            "Resolve blockers and rerun `make provider-lab-netapp-nfs-setup-preview` before apply."
            if gates["blockers"] or rest_apply.get("status") == "failed"
            else "Run NFS validation and then mount the NFS datastore on ESXi."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(NFS_APPLY_JSON, NFS_APPLY_REPORT, sanitized, _apply_markdown)
    return sanitized


def validate_netapp_nfs_setup(*, write_report: bool = True) -> dict[str, Any]:
    readiness = get_netapp_nfs_vcenter_readiness(check_ports=True, write_report=True)
    blockers = list(readiness.get("blockers") or [])
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "nfs-setup-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp NFS setup validation completed with read-only checks.",
        "mode": settings.provider_mode,
        "source_type": "live_probe",
        "freshness": "current",
        "apply_enabled": False,
        "readiness": readiness,
        "blockers": blockers,
        "warnings": list(readiness.get("warnings") or []),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(NFS_VALIDATION_REPORT),
            "json": _rel(NFS_VALIDATION_JSON),
            "readiness_report": "artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md",
        },
        "next_safe_action": (
            "Resolve blockers, then rerun `make provider-lab-netapp-nfs-setup-validate`."
            if blockers
            else "Mount the NFS datastore on ESXi with the guarded datastore lane."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(NFS_VALIDATION_JSON, NFS_VALIDATION_REPORT, sanitized, _validation_markdown)
    return sanitized


def _nfs_plan() -> dict[str, Any]:
    nfs_lifs = list(settings.netapp_nfs_lifs)
    missing = []
    if settings.netapp_storage_protocol.lower() != "nfs":
        missing.append("NETAPP_STORAGE_PROTOCOL=nfs")
    for field, value in (
        ("NETAPP_CLUSTER_MGMT_IP", settings.netapp_cluster_mgmt_ip),
        ("NETAPP_SVM_MGMT_IP", settings.netapp_svm_mgmt_ip),
        ("NETAPP_NFS_LIFS", nfs_lifs),
        ("NETAPP_NFS_VOLUME", settings.netapp_nfs_volume),
        ("NETAPP_NFS_EXPORT_POLICY", settings.netapp_nfs_export_policy),
        ("NETAPP_NFS_MOUNT_PATH", settings.netapp_nfs_mount_path),
        ("NETAPP_NFS_DATASTORE_NAME", settings.netapp_nfs_datastore_name),
        ("NETAPP_NFS_CLIENT_MATCH", settings.netapp_nfs_client_match),
    ):
        if not value:
            missing.append(field)
    return {
        "storage_protocol": settings.netapp_storage_protocol,
        "svm_name": settings.netapp_svm_name or "esxi_svm",
        "svm_management_ip": settings.netapp_svm_mgmt_ip,
        "nfs_lifs": nfs_lifs,
        "preferred_nfs_lif": nfs_lifs[0] if nfs_lifs else None,
        "fallback_nfs_lif": nfs_lifs[1] if len(nfs_lifs) > 1 else None,
        "volume": settings.netapp_nfs_volume,
        "mount_path": settings.netapp_nfs_mount_path,
        "export_policy": settings.netapp_nfs_export_policy,
        "export_client_match": settings.netapp_nfs_client_match,
        "datastore_name": settings.netapp_nfs_datastore_name,
        "future_iscsi_lifs_ignored": list(settings.netapp_iscsi_lifs),
        "missing_fields": missing,
    }


def _preview_blockers(runtime_state: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    blockers = []
    if not runtime_state.get("configured"):
        blockers.append("NetApp ONTAP cluster is not live-configured yet; NFS setup is blocked by prior cluster setup.")
    if not _api_access_present():
        blockers.append("NetApp API access fields are missing: NETAPP_API_USERNAME, NETAPP_API_PASSWORD.")
    if plan["missing_fields"]:
        blockers.append("NetApp NFS setup plan has missing required fields.")
    return _unique(blockers)


def _apply_gates(runtime_state: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "netapp_nfs_setup_apply": os.getenv("NETAPP_NFS_SETUP_APPLY") == "true",
        "netapp_nfs_setup_confirm": os.getenv("NETAPP_NFS_SETUP_CONFIRM") == NFS_SETUP_CONFIRM_PHRASE,
        "netapp_nfs_setup_allow_storage_create": os.getenv("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE") == "true",
    }
    blockers = []
    blockers.extend(policy.action_blockers("netapp.nfs-setup", ActionCategory.STORAGE_CONFIG))
    blockers.extend(_preview_blockers(runtime_state, plan))
    if not flag_state["netapp_nfs_setup_apply"]:
        blockers.append("NETAPP_NFS_SETUP_APPLY=true is required.")
    if not flag_state["netapp_nfs_setup_confirm"]:
        blockers.append(f'NETAPP_NFS_SETUP_CONFIRM="{NFS_SETUP_CONFIRM_PHRASE}" is required.')
    if not flag_state["netapp_nfs_setup_allow_storage_create"]:
        blockers.append("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true is required.")
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _api_access_present() -> bool:
    return bool(settings.netapp_api_username and settings.netapp_api_password)


def _exact_changes(plan: dict[str, Any]) -> list[dict[str, str | None]]:
    return [
        {"area": "svm", "change": "Create or confirm SVM for ESXi NFS", "value": plan.get("svm_name")},
        {"area": "nfs", "change": "Enable or confirm NFS service", "value": plan.get("storage_protocol")},
        {"area": "network", "change": "Create or confirm NFS data LIFs", "value": ", ".join(plan.get("nfs_lifs") or [])},
        {"area": "volume", "change": "Create or confirm datastore volume", "value": plan.get("volume")},
        {"area": "export", "change": "Create or confirm export policy", "value": plan.get("export_policy")},
        {"area": "export", "change": "Allow ESXi lab clients", "value": plan.get("export_client_match")},
        {"area": "datastore", "change": "Prepare ESXi datastore mount target", "value": plan.get("datastore_name")},
    ]


def _rest_preview(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"method": "GET", "path": "/api/cluster", "purpose": "Confirm cluster identity"},
        {"method": "GET", "path": "/api/svm/svms", "purpose": "Check SVM existence"},
        {"method": "POST", "path": "/api/svm/svms", "purpose": f"Create SVM {plan.get('svm_name')} if absent"},
        {"method": "PATCH", "path": "/api/protocols/nfs/services/{svm.uuid}", "purpose": "Enable NFS service if disabled"},
        {"method": "POST", "path": "/api/network/ip/interfaces", "purpose": "Create NFS data LIFs if absent"},
        {"method": "POST", "path": "/api/storage/volumes", "purpose": f"Create volume {plan.get('volume')} if absent"},
        {"method": "POST", "path": "/api/protocols/nfs/export-policies", "purpose": f"Create export policy {plan.get('export_policy')} if absent"},
        {"method": "POST", "path": "/api/protocols/nfs/export-policies/{policy.id}/rules", "purpose": f"Allow {plan.get('export_client_match')}"},
    ]


def _ensure_nfs_export_rule(plan: dict[str, Any]) -> dict[str, Any]:
    policy_name = str(plan.get("export_policy") or "")
    client_match = str(plan.get("export_client_match") or "")
    if not policy_name or not client_match:
        return _rest_apply_failed("NFS export policy or client match is missing.")
    try:
        policy = _get_export_policy(policy_name)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return _rest_apply_failed(f"Could not read NetApp export policy `{policy_name}`: {exc.__class__.__name__}.")
    if not policy:
        return _rest_apply_failed(f"NetApp export policy `{policy_name}` was not found.")
    rules = list(policy.get("rules") or [])
    for rule in rules:
        clients = rule.get("clients") if isinstance(rule, dict) else []
        if any(str(client.get("match") or "") == client_match for client in clients or [] if isinstance(client, dict)):
            return {
                "status": "ready",
                "message": f"NetApp NFS export rule for `{client_match}` already exists on `{policy_name}`.",
                "ontap_writes_attempted": False,
                "blockers": [],
                "transcript_summary": [f"Existing export rule found for {client_match}; no ONTAP write was needed."],
                "policy": {"name": policy_name, "id": policy.get("id")},
            }
    body = {
        "clients": [{"match": client_match}],
        "protocols": ["nfs"],
        "ro_rule": ["sys"],
        "rw_rule": ["sys"],
        "superuser": ["sys"],
    }
    try:
        response = _ontap_request("POST", f"/api/protocols/nfs/export-policies/{policy['id']}/rules", json_body=body)
    except (httpx.HTTPError, OSError) as exc:
        return _rest_apply_failed(f"Could not create NetApp export rule for `{client_match}`: {exc.__class__.__name__}.")
    if response.status_code not in {200, 201, 202}:
        return _rest_apply_failed(f"NetApp export rule create returned HTTP {response.status_code}.")
    return {
        "status": "applied",
        "message": f"NetApp NFS export rule for `{client_match}` was created on `{policy_name}`.",
        "ontap_writes_attempted": True,
        "blockers": [],
        "transcript_summary": [f"Created export policy rule for {client_match} on {policy_name}."],
        "policy": {"name": policy_name, "id": policy.get("id")},
    }


def _get_export_policy(policy_name: str) -> dict[str, Any] | None:
    response = _ontap_request(
        "GET",
        f"/api/protocols/nfs/export-policies?name={policy_name}&fields=id,name,svm.name,rules",
    )
    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code}")
    payload = response.json()
    for record in payload.get("records") or []:
        if record.get("name") == policy_name:
            return record
    return None


def _ontap_request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> httpx.Response:
    host = settings.netapp_cluster_mgmt_ip
    if not host or not settings.netapp_api_username or not settings.netapp_api_password:
        raise ValueError("NetApp API target or credentials missing")
    try:
        return _ontap_request_once(method, host, path, verify=settings.netapp_api_verify_tls, json_body=json_body)
    except (httpx.HTTPError, OSError):
        if not settings.netapp_api_verify_tls:
            raise
        return _ontap_request_once(method, host, path, verify=False, json_body=json_body)


def _ontap_request_once(
    method: str,
    host: str,
    path: str,
    *,
    verify: bool,
    json_body: dict[str, Any] | None,
) -> httpx.Response:
    with httpx.Client(verify=verify, timeout=10.0, trust_env=False) as client:
        return client.request(
            method,
            f"https://{host}{path}",
            auth=(settings.netapp_api_username, settings.netapp_api_password),
            headers={"Accept": "application/json"},
            json=json_body,
        )


def _rest_apply_not_attempted(reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "message": reason,
        "ontap_writes_attempted": False,
        "blockers": [],
        "transcript_summary": [reason],
    }


def _rest_apply_failed(reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "message": reason,
        "ontap_writes_attempted": False,
        "blockers": [reason],
        "transcript_summary": [reason],
    }


def _required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "NETAPP_NFS_SETUP_APPLY=true",
        f'NETAPP_NFS_SETUP_CONFIRM="{NFS_SETUP_CONFIRM_PHRASE}"',
        "NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true",
    ]


def _not_attempted() -> list[str]:
    return [
        "ONTAP REST write",
        "SVM, LIF, NFS service, volume, export policy, or export rule creation",
        "iSCSI configuration",
        "ESXi datastore mount",
        "vCenter datastore mount",
        "controller reboot, wipe, takeover/giveback, or ONTAP upgrade",
    ]


def _preview_markdown(payload: dict[str, Any]) -> str:
    return _common_markdown("NetApp NFS Setup Preview Report", payload)


def _apply_markdown(payload: dict[str, Any]) -> str:
    return _common_markdown("NetApp NFS Setup Apply Report", payload)


def _validation_markdown(payload: dict[str, Any]) -> str:
    return _common_markdown("NetApp NFS Setup Validation Report", payload)


def _common_markdown(title: str, payload: dict[str, Any]) -> str:
    plan = payload.get("nfs_plan") or (payload.get("readiness") or {}).get("planned_nfs") or {}
    lines = [
        f"# {title}",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Configured state: `{payload.get('configured_state')}`",
        f"- API access present: `{payload.get('api_access_present')}`",
        "- ONTAP writes attempted: `False`",
        "- ESXi/vCenter writes attempted: `False`",
        "",
        "## NFS Plan",
        f"- SVM: `{plan.get('svm_name')}`",
        f"- SVM management IP: `{plan.get('svm_management_ip')}`",
        f"- NFS LIFs: `{', '.join(plan.get('nfs_lifs') or [])}`",
        f"- Volume: `{plan.get('volume')}`",
        f"- Mount path: `{plan.get('mount_path')}`",
        f"- Export policy: `{plan.get('export_policy')}`",
        f"- Client match: `{plan.get('export_client_match') or plan.get('client_match')}`",
        f"- Datastore: `{plan.get('datastore_name')}`",
        "",
        "## Required Flags",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- NFS only. iSCSI is not used by this workflow.", "- Secrets are represented only as configured/missing/redacted state."])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown_builder(payload), encoding="utf-8")


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
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


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
