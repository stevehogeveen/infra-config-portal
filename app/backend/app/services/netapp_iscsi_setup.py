from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.env_utils import env_flag as _env_flag
from app.services.json_file_store import write_json_object, write_text_value
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.netapp_state import get_netapp_runtime_state
from app.services.path_utils import repo_relative_path

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

ISCSI_PREVIEW_REPORT = CODEX_RUN_DIR / "netapp-iscsi-setup-preview-report.md"
ISCSI_PREVIEW_JSON = CODEX_RUN_DIR / "netapp-iscsi-setup-preview-redacted.json"
ISCSI_APPLY_REPORT = CODEX_RUN_DIR / "netapp-iscsi-setup-apply-report.md"
ISCSI_APPLY_JSON = CODEX_RUN_DIR / "netapp-iscsi-setup-apply-redacted.json"
ISCSI_VALIDATION_REPORT = CODEX_RUN_DIR / "netapp-iscsi-setup-validation-report.md"
ISCSI_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-iscsi-setup-validation-redacted.json"

ISCSI_SETUP_CONFIRM_PHRASE = "APPLY NETAPP ISCSI SETUP"


def build_netapp_iscsi_setup_preview(*, write_report: bool = True) -> dict[str, Any]:
    runtime_state = get_netapp_runtime_state()
    plan = _iscsi_plan(runtime_state)
    protocol = _iscsi_protocol_option(runtime_state)
    inventory = _iscsi_inventory(plan)
    blockers = _preview_blockers(runtime_state, plan)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "iscsi-setup-preview",
        "checked_at": _now(),
        "status": "blocked" if blockers else "preview_only",
        "message": "NetApp iSCSI setup preview generated. No LUN, igroup, ESXi, or datastore write action was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": runtime_state.get("source_type") or "live_cached",
        "freshness": runtime_state.get("freshness") or "current",
        "configured_state": runtime_state.get("configured_state"),
        "configured": bool(runtime_state.get("configured")),
        "api_access_present": _api_access_present(),
        "iscsi_plan": plan,
        "current_state": inventory,
        "protocol_readiness": protocol,
        "exact_changes": _exact_changes(plan),
        "rest_preview": _rest_preview(plan),
        "required_flags": _required_flags(),
        "blockers": blockers,
        "warnings": [
            "Preview only. No LUN, igroup, LUN map, ESXi login, or VMFS datastore action was run.",
            "The guarded apply lane only manages ONTAP LUN, igroup, and LUN map objects; ESXi login and VMFS mount remain separate guarded work.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(ISCSI_PREVIEW_REPORT),
            "json": _rel(ISCSI_PREVIEW_JSON),
        },
        "next_safe_action": (
            "Resolve iSCSI readiness blockers before designing the guarded LUN/igroup/datastore apply lane."
            if blockers
            else "iSCSI protocol readiness is proven; review the guarded LUN, igroup, and map apply lane before setting apply flags."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(ISCSI_PREVIEW_JSON, ISCSI_PREVIEW_REPORT, sanitized, _preview_markdown)
    return sanitized


def apply_netapp_iscsi_setup(*, write_report: bool = True) -> dict[str, Any]:
    runtime_state = get_netapp_runtime_state()
    plan = _iscsi_plan(runtime_state)
    protocol = _iscsi_protocol_option(runtime_state)
    inventory = _iscsi_inventory(plan)
    gates = _apply_gates(runtime_state, plan, protocol)
    apply_result = _rest_apply_not_attempted("Apply gates blocked before ONTAP REST write session started.")
    if not gates["blockers"]:
        apply_result = _ensure_iscsi_lun_igroup_map(plan, inventory)
        inventory = _iscsi_inventory(plan)
    blockers = _unique([*gates["blockers"], *_string_list(apply_result.get("blockers"))])
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "iscsi-setup-apply",
        "checked_at": _now(),
        "status": "blocked" if blockers else apply_result.get("status") or "ready",
        "message": (
            "NetApp iSCSI setup apply was refused before any ONTAP write command."
            if gates["blockers"]
            else apply_result.get("message") or "NetApp iSCSI setup apply completed."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": not bool(gates["blockers"]),
        "source_type": runtime_state.get("source_type") or "live_cached",
        "freshness": runtime_state.get("freshness") or "current",
        "configured_state": runtime_state.get("configured_state"),
        "configured": bool(runtime_state.get("configured")),
        "api_access_present": _api_access_present(),
        "flag_state": gates["flag_state"],
        "iscsi_plan": plan,
        "current_state": inventory,
        "protocol_readiness": protocol,
        "exact_changes": _exact_changes(plan),
        "rest_preview": _rest_preview(plan),
        "required_flags": _required_flags(),
        "apply": {
            "ontap_writes_attempted": bool(apply_result.get("ontap_writes_attempted")),
            "esxi_writes_attempted": False,
            "vcenter_writes_attempted": False,
            "transcript_summary": _string_list(apply_result.get("transcript_summary")),
            "rest_result": apply_result,
        },
        "blockers": blockers,
        "warnings": [
            "No secrets are printed or written to the apply report.",
            "This apply lane does not run ESXi iSCSI login, rescan, VMFS format, datastore mount, or vCenter registration.",
        ],
        "not_attempted": _not_attempted(bool(apply_result.get("ontap_writes_attempted"))),
        "artifacts": {
            "report": _rel(ISCSI_APPLY_REPORT),
            "json": _rel(ISCSI_APPLY_JSON),
        },
        "next_safe_action": (
            "Resolve blockers and rerun iSCSI preview before apply."
            if blockers
            else "Run iSCSI validation, then build the separate ESXi login/rescan/VMFS mount lane."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(ISCSI_APPLY_JSON, ISCSI_APPLY_REPORT, sanitized, _apply_markdown)
    return sanitized


def validate_netapp_iscsi_setup(*, write_report: bool = True) -> dict[str, Any]:
    runtime_state = get_netapp_runtime_state()
    plan = _iscsi_plan(runtime_state)
    protocol = _iscsi_protocol_option(runtime_state)
    inventory = _iscsi_inventory(plan)
    blockers = _validation_blockers(runtime_state, plan, protocol, inventory)
    source_type = "live_probe" if inventory.get("checked") else runtime_state.get("source_type") or "live_cached"
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "iscsi-setup-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp iSCSI setup validation completed with read-only protocol and inventory checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": source_type,
        "freshness": runtime_state.get("freshness") or "current",
        "configured_state": runtime_state.get("configured_state"),
        "configured": bool(runtime_state.get("configured")),
        "api_access_present": _api_access_present(),
        "iscsi_plan": plan,
        "current_state": inventory,
        "protocol_readiness": protocol,
        "blockers": blockers,
        "warnings": [
            "Read-only validation only. No LUN, igroup, LUN map, initiator login, VMFS datastore, or ESXi mount is created by validation.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(ISCSI_VALIDATION_REPORT),
            "json": _rel(ISCSI_VALIDATION_JSON),
        },
        "report_artifacts": [
            _rel(ISCSI_VALIDATION_REPORT),
            _rel(ISCSI_VALIDATION_JSON),
        ],
        "next_safe_action": _validation_next_safe_action(blockers, protocol),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(ISCSI_VALIDATION_JSON, ISCSI_VALIDATION_REPORT, sanitized, _validation_markdown)
    return sanitized


def _iscsi_plan(runtime_state: dict[str, Any]) -> dict[str, Any]:
    lifs = list(settings.netapp_iscsi_lifs)
    svm_name = settings.netapp_svm_name or "esxi_svm"
    initiator_iqns, initiator_discovery = _esxi_initiator_iqns()
    storage = runtime_state.get("storage") if isinstance(runtime_state.get("storage"), dict) else {}
    detected = storage.get("iscsi_lifs_detected") if isinstance(storage, dict) else []
    if isinstance(detected, list) and detected:
        lifs = [str(item) for item in detected if str(item).strip()]
    missing = []
    for field, value in (
        ("NETAPP_CLUSTER_MGMT_IP", settings.netapp_cluster_mgmt_ip),
        ("NETAPP_SVM_NAME", svm_name),
        ("NETAPP_ISCSI_LIFS", lifs),
    ):
        if not value:
            missing.append(field)
    return {
        "storage_protocol": settings.netapp_storage_protocol,
        "svm_name": svm_name,
        "svm_management_ip": settings.netapp_svm_mgmt_ip,
        "iscsi_lifs": lifs,
        "preferred_iscsi_lif": lifs[0] if lifs else None,
        "volume_name": os.getenv("NETAPP_ISCSI_VOLUME", settings.netapp_nfs_volume),
        "lun_name": os.getenv("NETAPP_ISCSI_LUN_NAME", "esxi_lun_01"),
        "lun_path": _lun_path(os.getenv("NETAPP_ISCSI_VOLUME", settings.netapp_nfs_volume), os.getenv("NETAPP_ISCSI_LUN_NAME", "esxi_lun_01")),
        "lun_size": os.getenv("NETAPP_ISCSI_LUN_SIZE", "1TB"),
        "igroup_name": os.getenv("NETAPP_ISCSI_IGROUP_NAME", "esxi_hosts"),
        "initiator_iqns": initiator_iqns,
        "initiator_discovery": initiator_discovery,
        "datastore_name": os.getenv("ESXI_ISCSI_DATASTORE_NAME", "netapp_iscsi_ds01"),
        "vmfs_version": os.getenv("ESXI_ISCSI_VMFS_VERSION", "VMFS6"),
        "missing_fields": missing,
    }


def _lun_path(volume_name: str | None, lun_name: str | None) -> str | None:
    if not volume_name or not lun_name:
        return None
    return f"/vol/{volume_name}/{lun_name}"


def _esxi_initiator_iqns() -> tuple[list[str], dict[str, Any]]:
    configured = _csv_env("ESXI_ISCSI_INITIATOR_IQNS")
    if configured:
        return configured, {"source": "ESXI_ISCSI_INITIATOR_IQNS", "status": "configured"}
    missing = []
    if not settings.esxi_test_host:
        missing.append("ESXI_TEST_HOST")
    if not settings.esxi_test_username:
        missing.append("ESXI_TEST_USERNAME")
    if not settings.esxi_test_password:
        missing.append("ESXI_TEST_PASSWORD")
    if missing:
        return [], {"source": "live_esxi_ssh", "status": "blocked", "missing_fields": missing}
    try:
        import paramiko  # type: ignore[import-untyped]
    except Exception as exc:
        return [], {"source": "live_esxi_ssh", "status": "blocked", "blockers": [f"paramiko unavailable: {exc}"]}
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=settings.esxi_test_host,
            username=settings.esxi_test_username,
            password=settings.esxi_test_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        )
        list_result = _run_ssh_command(client, "esxcli iscsi adapter list")
        adapters = _adapter_names(list_result.get("stdout"))
        iqns: list[str] = []
        adapter_results = []
        for adapter in adapters:
            result = _run_ssh_command(client, f"esxcli iscsi adapter get -A {adapter}")
            found = re.findall(r"iqn\.[^\s]+", result.get("stdout") or "")
            iqns.extend(found)
            adapter_results.append(
                {
                    "adapter": adapter,
                    "return_code": result.get("return_code"),
                    "iqns": found,
                }
            )
        return unique_strings(iqns), {
            "source": "live_esxi_ssh",
            "status": "ready" if iqns else "blocked",
            "host": settings.esxi_test_host,
            "adapters": adapters,
            "adapter_results": adapter_results,
            "blockers": [] if iqns else ["ESXi software iSCSI adapter is not enabled or no initiator IQN was returned."],
        }
    except (OSError, paramiko.SSHException) as exc:
        return [], {"source": "live_esxi_ssh", "status": "blocked", "blockers": [f"{exc.__class__.__name__}: {exc}"]}
    finally:
        client.close()


def _run_ssh_command(client: Any, command: str, *, timeout: int = 30) -> dict[str, Any]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return {"return_code": stdout.channel.recv_exit_status(), "stdout": out, "stderr": err}


def _adapter_names(stdout: str | None) -> list[str]:
    adapters: list[str] = []
    for line in (stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("vmhba"):
            adapters.append(stripped.split()[0])
    return adapters


def _iscsi_protocol_option(runtime_state: dict[str, Any]) -> dict[str, Any]:
    options = runtime_state.get("protocol_options") if isinstance(runtime_state.get("protocol_options"), dict) else {}
    option = options.get("iscsi") if isinstance(options.get("iscsi"), dict) else {}
    return {
        "ready": bool(option.get("ready")),
        "service_status": option.get("service_status") or "not_checked",
        "service_enabled": option.get("service_enabled"),
        "lifs": option.get("lifs") if isinstance(option.get("lifs"), list) else list(settings.netapp_iscsi_lifs),
        "reachable_lif_count": option.get("reachable_lif_count") or 0,
        "port": option.get("port") or 3260,
        "checks": option.get("checks") if isinstance(option.get("checks"), list) else [],
        "blockers": _string_list(option.get("blockers")),
        "warnings": _string_list(option.get("warnings")),
    }


def _iscsi_inventory(plan: dict[str, Any]) -> dict[str, Any]:
    if not _api_access_present():
        return {
            "checked": False,
            "source": "ontap_rest",
            "status": "blocked",
            "blockers": ["NetApp API access fields are missing: NETAPP_API_USERNAME, NETAPP_API_PASSWORD."],
        }
    checks: dict[str, Any] = {}
    blockers: list[str] = []
    for name, path, parser in (
        ("svm", f"/api/svm/svms?name={_q(plan.get('svm_name'))}&fields=name,uuid,state,subtype", _first_record),
        (
            "iscsi_service",
            f"/api/protocols/san/iscsi/services?svm.name={_q(plan.get('svm_name'))}&fields=svm.name,svm.uuid,enabled,target.name",
            _first_record,
        ),
        ("volume", f"/api/storage/volumes?name={_q(plan.get('volume_name'))}&fields=name,uuid,svm.name,size,state,nas.path", _first_record),
        ("lun", f"/api/storage/luns?svm.name={_q(plan.get('svm_name'))}&name={_q(plan.get('lun_path'))}&fields=name,uuid,svm.name,space.size,os_type,status.state,lun_maps", _first_record),
        (
            "igroup",
            f"/api/protocols/san/igroups?svm.name={_q(plan.get('svm_name'))}&name={_q(plan.get('igroup_name'))}&fields=name,uuid,svm.name,protocol,os_type,initiators.name",
            _first_record,
        ),
        (
            "lun_map",
            f"/api/protocols/san/lun-maps?svm.name={_q(plan.get('svm_name'))}&lun.name={_q(plan.get('lun_path'))}&igroup.name={_q(plan.get('igroup_name'))}&fields=svm.name,lun.name,igroup.name,logical_unit_number",
            _first_record,
        ),
    ):
        result = _ontap_get(path)
        checks[name] = parser(result)
        if result.get("http_status") not in {200, 201, 202}:
            blockers.append(f"ONTAP {name} inventory returned HTTP {result.get('http_status')}.")
    return {
        "checked": True,
        "source": "ontap_rest",
        "status": "blocked" if blockers else "ready",
        "svm": _svm_summary(checks.get("svm")),
        "iscsi_service": _iscsi_service_summary(checks.get("iscsi_service")),
        "volume": _volume_summary(checks.get("volume")),
        "lun": _lun_summary(checks.get("lun")),
        "igroup": _igroup_summary(checks.get("igroup")),
        "lun_map": _lun_map_summary(checks.get("lun_map")),
        "blockers": _unique(blockers),
    }


def _ontap_get(path: str) -> dict[str, Any]:
    try:
        response = _ontap_request("GET", path)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return {"http_status": None, "error": f"{exc.__class__.__name__}: {exc}"}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    records = payload.get("records") if isinstance(payload, dict) else []
    return {
        "http_status": response.status_code,
        "num_records": payload.get("num_records") if isinstance(payload, dict) else None,
        "records": records if isinstance(records, list) else [],
        "error": payload.get("error") if isinstance(payload, dict) else None,
    }


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


def _first_record(result: dict[str, Any]) -> dict[str, Any] | None:
    records = result.get("records")
    if isinstance(records, list) and records:
        first = records[0]
        return first if isinstance(first, dict) else None
    return None


def _svm_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "exists": bool(record),
        "name": record.get("name") if record else None,
        "uuid": record.get("uuid") if record else None,
        "state": record.get("state") if record else None,
    }


def _iscsi_service_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    target = record.get("target") if record else {}
    svm = record.get("svm") if record else {}
    return {
        "exists": bool(record),
        "enabled": record.get("enabled") if record else None,
        "svm": svm.get("name") if isinstance(svm, dict) else None,
        "target_iqn": target.get("name") if isinstance(target, dict) else None,
    }


def _volume_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    svm = record.get("svm") if record else {}
    return {
        "exists": bool(record),
        "name": record.get("name") if record else None,
        "uuid": record.get("uuid") if record else None,
        "svm": svm.get("name") if isinstance(svm, dict) else None,
        "size": record.get("size") if record else None,
        "state": record.get("state") if record else None,
    }


def _lun_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    status = record.get("status") if record else {}
    space = record.get("space") if record else {}
    return {
        "exists": bool(record),
        "name": record.get("name") if record else None,
        "uuid": record.get("uuid") if record else None,
        "size": space.get("size") if isinstance(space, dict) else None,
        "os_type": record.get("os_type") if record else None,
        "state": status.get("state") if isinstance(status, dict) else None,
    }


def _igroup_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "exists": bool(record),
        "name": record.get("name") if record else None,
        "uuid": record.get("uuid") if record else None,
        "protocol": record.get("protocol") if record else None,
        "os_type": record.get("os_type") if record else None,
        "initiators": [
            initiator.get("name")
            for initiator in (record.get("initiators") if record else []) or []
            if isinstance(initiator, dict) and initiator.get("name")
        ],
    }


def _lun_map_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    lun = record.get("lun") if record else {}
    igroup = record.get("igroup") if record else {}
    return {
        "exists": bool(record),
        "lun": lun.get("name") if isinstance(lun, dict) else None,
        "igroup": igroup.get("name") if isinstance(igroup, dict) else None,
        "logical_unit_number": record.get("logical_unit_number") if record else None,
    }


def _q(value: Any) -> str:
    from urllib.parse import quote

    return quote(str(value or ""), safe="")


def _preview_blockers(runtime_state: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    blockers = []
    if not runtime_state.get("configured"):
        blockers.append("NetApp ONTAP cluster is not live-configured yet; iSCSI setup is blocked by prior cluster setup.")
    if not _api_access_present():
        blockers.append("NetApp API access fields are missing: NETAPP_API_USERNAME, NETAPP_API_PASSWORD.")
    if plan["missing_fields"]:
        blockers.append("NetApp iSCSI setup plan has missing required fields.")
    if not plan["initiator_iqns"]:
        blockers.append("ESXI_ISCSI_INITIATOR_IQNS is required before any future guarded igroup apply.")
    return _unique(blockers)


def _validation_blockers(
    runtime_state: dict[str, Any],
    plan: dict[str, Any],
    protocol: dict[str, Any],
    inventory: dict[str, Any] | None = None,
) -> list[str]:
    blockers = _preview_blockers(runtime_state, plan)
    blockers.extend(_string_list(protocol.get("blockers")))
    if not protocol.get("ready"):
        blockers.append("NetApp iSCSI protocol option is not ready yet.")
    inventory = inventory or _iscsi_inventory(plan)
    for label, item in (
        ("LUN", inventory.get("lun")),
        ("igroup", inventory.get("igroup")),
        ("LUN map", inventory.get("lun_map")),
    ):
        if not isinstance(item, dict) or not item.get("exists"):
            blockers.append(f"NetApp iSCSI {label} is missing.")
    return _unique(blockers)


def _validation_next_safe_action(blockers: list[str], protocol: dict[str, Any]) -> str:
    if not blockers:
        return "ONTAP iSCSI LUN, igroup, and map are present; build/run ESXi login, rescan, and VMFS mount validation next."
    missing_object_blockers = [blocker for blocker in blockers if blocker.startswith("NetApp iSCSI ")]
    non_object_blockers = [blocker for blocker in blockers if blocker not in missing_object_blockers]
    if protocol.get("ready") and not non_object_blockers:
        return "iSCSI protocol is ready; run guarded iSCSI apply to create missing ONTAP LUN, igroup, and map objects."
    return "Fix iSCSI readiness blockers, then rerun validation."


def _exact_changes(plan: dict[str, Any]) -> list[dict[str, str | None]]:
    return [
        {"area": "svm", "change": "Confirm SVM for ESXi iSCSI", "value": plan.get("svm_name")},
        {"area": "iscsi", "change": "Enable or confirm iSCSI service", "value": plan.get("storage_protocol")},
        {"area": "network", "change": "Confirm iSCSI data LIFs", "value": ", ".join(plan.get("iscsi_lifs") or [])},
        {"area": "lun", "change": "Future create or confirm LUN", "value": plan.get("lun_name")},
        {"area": "igroup", "change": "Future create or confirm igroup", "value": plan.get("igroup_name")},
        {"area": "initiators", "change": "Future bind ESXi IQNs", "value": ", ".join(plan.get("initiator_iqns") or [])},
        {"area": "datastore", "change": "Future mount VMFS datastore", "value": plan.get("datastore_name")},
    ]


def _rest_preview(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"method": "GET", "path": "/api/protocols/san/iscsi/services", "purpose": "Confirm iSCSI service"},
        {"method": "GET", "path": "/api/network/ip/interfaces", "purpose": "Confirm iSCSI LIFs"},
        {"method": "POST", "path": "/api/storage/luns", "purpose": f"Future create LUN {plan.get('lun_name')}"},
        {"method": "POST", "path": "/api/protocols/san/igroups", "purpose": f"Future create igroup {plan.get('igroup_name')}"},
        {"method": "PATCH", "path": "/api/protocols/san/igroups/{igroup.uuid}", "purpose": "Future bind ESXi initiator IQNs"},
    ]


def _apply_gates(runtime_state: dict[str, Any], plan: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "netapp_iscsi_setup_apply": _env_flag("NETAPP_ISCSI_SETUP_APPLY"),
        "netapp_iscsi_setup_confirm": os.getenv("NETAPP_ISCSI_SETUP_CONFIRM") == ISCSI_SETUP_CONFIRM_PHRASE,
        "netapp_iscsi_setup_allow_storage_create": _env_flag("NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE"),
    }
    blockers: list[str] = []
    blockers.extend(_string_list(policy.action_blockers("netapp.iscsi-setup", ActionCategory.STORAGE_CONFIG)))
    blockers.extend(_preview_blockers(runtime_state, plan))
    blockers.extend(_string_list(protocol.get("blockers")))
    if not protocol.get("ready"):
        blockers.append("NetApp iSCSI protocol option is not ready yet.")
    if not flag_state["netapp_iscsi_setup_apply"]:
        blockers.append("NETAPP_ISCSI_SETUP_APPLY=true is required.")
    if not flag_state["netapp_iscsi_setup_confirm"]:
        blockers.append(f'NETAPP_ISCSI_SETUP_CONFIRM="{ISCSI_SETUP_CONFIRM_PHRASE}" is required.')
    if not flag_state["netapp_iscsi_setup_allow_storage_create"]:
        blockers.append("NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true is required.")
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _ensure_iscsi_lun_igroup_map(plan: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    transcript: list[str] = []
    writes_attempted = False
    try:
        if not _object_exists(inventory.get("lun")):
            writes_attempted = True
            _create_lun(plan)
            transcript.append(f"Created LUN {plan.get('lun_path')}.")
        else:
            transcript.append(f"Existing LUN found at {plan.get('lun_path')}; no LUN create needed.")

        inventory = _iscsi_inventory(plan)
        if not _object_exists(inventory.get("igroup")):
            writes_attempted = True
            _create_igroup(plan)
            transcript.append(f"Created igroup {plan.get('igroup_name')} with {len(plan.get('initiator_iqns') or [])} initiator(s).")
        else:
            transcript.append(f"Existing igroup found at {plan.get('igroup_name')}; no igroup create needed.")

        inventory = _iscsi_inventory(plan)
        if not _object_exists(inventory.get("lun_map")):
            writes_attempted = True
            _create_lun_map(plan)
            transcript.append(f"Mapped {plan.get('lun_path')} to {plan.get('igroup_name')}.")
        else:
            transcript.append(f"Existing LUN map found for {plan.get('lun_path')} and {plan.get('igroup_name')}.")
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return _rest_apply_failed(f"NetApp iSCSI apply failed: {exc.__class__.__name__}: {exc}")

    return {
        "status": "applied" if writes_attempted else "ready",
        "message": "NetApp iSCSI LUN, igroup, and LUN map are present.",
        "ontap_writes_attempted": writes_attempted,
        "blockers": [],
        "transcript_summary": transcript,
    }


def _object_exists(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("exists"))


def _create_lun(plan: dict[str, Any]) -> None:
    size = _parse_size_bytes(plan.get("lun_size"))
    body = {
        "svm": {"name": plan.get("svm_name")},
        "name": plan.get("lun_path"),
        "os_type": "vmware",
        "space": {"size": size},
    }
    response = _ontap_request("POST", "/api/storage/luns", json_body=body)
    if response.status_code not in {200, 201, 202}:
        raise ValueError(f"LUN create returned HTTP {response.status_code}")


def _create_igroup(plan: dict[str, Any]) -> None:
    body = {
        "svm": {"name": plan.get("svm_name")},
        "name": plan.get("igroup_name"),
        "protocol": "iscsi",
        "os_type": "vmware",
        "initiators": [{"name": iqn} for iqn in plan.get("initiator_iqns") or []],
    }
    response = _ontap_request("POST", "/api/protocols/san/igroups", json_body=body)
    if response.status_code not in {200, 201, 202}:
        raise ValueError(f"igroup create returned HTTP {response.status_code}")


def _create_lun_map(plan: dict[str, Any]) -> None:
    body = {
        "svm": {"name": plan.get("svm_name")},
        "lun": {"name": plan.get("lun_path")},
        "igroup": {"name": plan.get("igroup_name")},
    }
    response = _ontap_request("POST", "/api/protocols/san/lun-maps", json_body=body)
    if response.status_code not in {200, 201, 202}:
        raise ValueError(f"LUN map create returned HTTP {response.status_code}")


def _parse_size_bytes(value: Any) -> int:
    raw = str(value or "").strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmgtp]?i?b?)?", raw)
    if not match:
        raise ValueError(f"Unsupported LUN size `{value}`")
    amount = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    multipliers = {
        "": 1,
        "b": 1,
        "k": 1000,
        "kb": 1000,
        "ki": 1024,
        "kib": 1024,
        "m": 1000**2,
        "mb": 1000**2,
        "mi": 1024**2,
        "mib": 1024**2,
        "g": 1000**3,
        "gb": 1000**3,
        "gi": 1024**3,
        "gib": 1024**3,
        "t": 1000**4,
        "tb": 1000**4,
        "ti": 1024**4,
        "tib": 1024**4,
        "p": 1000**5,
        "pb": 1000**5,
        "pi": 1024**5,
        "pib": 1024**5,
    }
    if unit not in multipliers:
        raise ValueError(f"Unsupported LUN size unit `{unit}`")
    return int(amount * multipliers[unit])


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
        "NETAPP_ISCSI_SETUP_APPLY=true",
        f'NETAPP_ISCSI_SETUP_CONFIRM="{ISCSI_SETUP_CONFIRM_PHRASE}"',
        "NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true",
    ]


def _not_attempted(ontap_writes_attempted: bool = False) -> list[str]:
    not_attempted = [
        "ONTAP REST write",
        "iSCSI service, LIF, LUN, igroup, or initiator creation",
        "ESXi software iSCSI adapter configuration",
        "ESXi initiator login or rescan",
        "VMFS datastore creation or mount",
        "NFS configuration",
        "controller reboot, wipe, takeover/giveback, or ONTAP upgrade",
    ]
    if ontap_writes_attempted:
        not_attempted.remove("ONTAP REST write")
        not_attempted.remove("iSCSI service, LIF, LUN, igroup, or initiator creation")
    return not_attempted


def _preview_markdown(payload: dict[str, Any]) -> str:
    return _common_markdown("NetApp iSCSI Setup Preview Report", payload)


def _apply_markdown(payload: dict[str, Any]) -> str:
    return _common_markdown("NetApp iSCSI Setup Apply Report", payload)


def _validation_markdown(payload: dict[str, Any]) -> str:
    return _common_markdown("NetApp iSCSI Setup Validation Report", payload)


def _common_markdown(title: str, payload: dict[str, Any]) -> str:
    plan = payload.get("iscsi_plan") or {}
    protocol = payload.get("protocol_readiness") or {}
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
        "## iSCSI Plan",
        f"- SVM: `{plan.get('svm_name')}`",
        f"- iSCSI LIFs: `{', '.join(plan.get('iscsi_lifs') or [])}`",
        f"- LUN: `{plan.get('lun_name')}`",
        f"- LUN size: `{plan.get('lun_size')}`",
        f"- Igroup: `{plan.get('igroup_name')}`",
        f"- Initiator IQNs: `{', '.join(plan.get('initiator_iqns') or [])}`",
        f"- Datastore: `{plan.get('datastore_name')}`",
        f"- Protocol service: `{protocol.get('service_status')}`",
        f"- Reachable LIFs: `{protocol.get('reachable_lif_count')}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Required Flags"])
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Safety", "- Preview and validation are read-only. Apply is gated and only manages ONTAP LUN, igroup, and LUN map objects."])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(json_path, payload)
    write_text_value(report_path, markdown_builder(payload))


def _api_access_present() -> bool:
    return bool(settings.netapp_api_username and settings.netapp_api_password)


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for value in (
            settings.netapp_api_username,
            settings.netapp_api_password,
            os.getenv("NETAPP_ISCSI_SETUP_CONFIRM"),
        )
        if value
    ]


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _unique(values: list[Any]) -> list[str]:
    return unique_preserving_order(_string_list(values))


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _now() -> str:
    return datetime.now(UTC).isoformat()
