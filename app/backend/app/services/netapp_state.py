from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, init_database
from app.models import ProviderRuntimeState
from app.providers.redaction import redact_sensitive
from app.services.status_source import attach_status_source

PROVIDER_ID = "netapp-ontap"
DEVICE_ROLE = "storage-controller"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
LIVE_STATE_REPORT = CODEX_RUN_DIR / "netapp-live-state-report.md"
AUTOMANAGEMENT_REPORT = CODEX_RUN_DIR / "netapp-state-automanagement-report.md"
CONSOLE_LAST_KNOWN_GOOD_JSON = CODEX_RUN_DIR / "netapp-console-last-known-good-redacted.json"
CONSOLE_AUTODISCOVERY_JSON = CODEX_RUN_DIR / "netapp-console-autodiscovery-redacted.json"
CONSOLE_STATE_JSON = CODEX_RUN_DIR / "netapp-console-state-redacted.json"

VALID_CONFIGURED_STATES = {
    "not_detected",
    "console_detected",
    "login_required",
    "setup_wizard",
    "ontap_detected",
    "management_reachable",
    "api_authenticated",
    "storage_ready",
    "configured",
    "blocked",
}


def get_netapp_runtime_state(*, session: Session | None = None) -> dict[str, Any]:
    if session is not None:
        return _record_to_payload(_get_record(session))

    init_database()
    with SessionLocal() as local_session:
        return _record_to_payload(_get_record(local_session))


def update_netapp_runtime_state_from_console_probe(
    payload: dict[str, Any],
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    selected_port = _optional_str(payload.get("selected_port"))
    selected_baud = _optional_int(payload.get("selected_baud"))
    checked_at = _parse_datetime(payload.get("checked_at")) or _utcnow()
    prompt_state = _optional_str(payload.get("selected_prompt_state"))
    state = _state_from_console_prompt(prompt_state, payload.get("blockers") or [])
    origin = _console_origin(selected_port, payload.get("selection_source"))
    confidence = _optional_str(payload.get("selection_confidence"))
    report_path = _optional_report(payload)
    console_payload = {
        "discovered_port": selected_port,
        "baud": selected_baud,
        "confidence": confidence,
        "last_seen": checked_at.isoformat(),
        "source": origin,
        "selection_source": _optional_str(payload.get("selection_source")),
        "prompt_state": prompt_state,
        "prompt_label": _optional_str(payload.get("selected_prompt_label")),
        "configured_port_hint": _optional_str(payload.get("configured_port_hint")),
        "detected_automatically": origin == "autodiscovery",
        "manual_env_update_required": False,
    }
    blockers = [str(item) for item in payload.get("blockers") or [] if str(item)]

    def apply(session_to_use: Session) -> dict[str, Any]:
        record = _get_or_create_record(session_to_use)
        if selected_port:
            record.discovered_console_port = selected_port
            record.discovered_baud = selected_baud
            record.confidence = confidence
            record.last_successful_probe_at = checked_at
            record.last_report_path = report_path
        if not record.configured:
            record.configured_state = state
            record.source = "console_read_state" if payload.get("action") == "console-read-state" else "console_discovery"
        record.blockers = blockers
        record.data_json = {
            **(record.data_json or {}),
            "console": console_payload,
            "legacy_env": _legacy_env_context(),
            "evidence_report_path": report_path,
            "verified_at": (record.data_json or {}).get("verified_at") if record.configured else None,
        }
        record.updated_at = _utcnow()
        session_to_use.add(record)
        return _record_to_payload(record)

    snapshot = _write_with_session(apply, session=session)
    _write_console_last_known_good(snapshot)
    _write_automanagement_report(snapshot)
    return snapshot


def read_netapp_live_state(
    *,
    check_ports: bool = True,
    write_report: bool = True,
    session: Session | None = None,
    reachable: Callable[[str | None, int, bool], bool | None] | None = None,
    api_getter: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = get_netapp_runtime_state(session=session)
    reachable = reachable or _reachable
    checked_at = _utcnow()
    cluster_host = settings.netapp_cluster_mgmt_ip
    management_rest = reachable(cluster_host, 443, check_ports)
    management_ssh = reachable(cluster_host, 22, check_ports)
    api_access_present = bool(settings.netapp_api_username and settings.netapp_api_password)
    api_probe = _api_probe_not_attempted("Port checks disabled for this run.")
    if check_ports and management_rest is True and api_access_present:
        api_probe = api_getter() if api_getter else _safe_ontap_api_probe()
    elif check_ports and not api_access_present:
        api_probe = _api_probe_not_attempted("NetApp API access values are missing.")
    elif check_ports and management_rest is not True:
        api_probe = _api_probe_not_attempted("Cluster management REST is not reachable.")

    storage = _storage_protocol_readiness()
    state = _classify_live_state(
        cached_state=current,
        management_rest=management_rest,
        api_authenticated=api_probe.get("authenticated") is True,
        storage_ready=storage["ready"],
    )
    configured = state == "configured"
    blockers = _live_state_blockers(
        management_rest=management_rest,
        api_access_present=api_access_present,
        api_probe=api_probe,
        storage=storage,
        check_ports=check_ports,
    )
    report_path = _rel(LIVE_STATE_REPORT)
    payload = {
        "provider_id": PROVIDER_ID,
        "device_role": DEVICE_ROLE,
        "action": "read-live-state",
        "checked_at": checked_at.isoformat(),
        "status": "ready" if configured else "blocked" if blockers else "warning",
        "configured": configured,
        "configured_state": state,
        "source": "live_verification",
        "mode": settings.provider_mode,
        "message": (
            "NetApp configured state was verified by live check."
            if configured
            else "NetApp live state was read without applying changes."
        ),
        "manual_env_flag_required": False,
        "legacy_env": _legacy_env_context(),
        "console": current.get("console") or _empty_console_state(),
        "management": {
            "cluster_mgmt_ip": cluster_host,
            "rest_443_reachable": management_rest,
            "ssh_22_reachable": management_ssh,
        },
        "api": {
            "access_values_present": api_access_present,
            "authenticated": api_probe.get("authenticated"),
            "status": api_probe.get("status"),
            "reason": api_probe.get("reason"),
        },
        "storage": storage,
        "detected_management_ips": _detected_management_ips(management_rest),
        "detected_storage_protocol_readiness": storage,
        "last_successful_probe_at": checked_at.isoformat() if configured else current.get("last_successful_probe_at"),
        "last_report_path": report_path,
        "confidence": "high" if configured else _live_state_confidence(current, management_rest),
        "blockers": blockers,
        "warnings": [
            "Manual env flag not required.",
            "Live checks are read-only and do not run NetApp setup, storage, upgrade, reboot, wipe, or apply commands.",
        ],
        "artifacts": {
            "report": report_path,
            "state_report": report_path,
            "automanagement_report": _rel(AUTOMANAGEMENT_REPORT),
            "console_last_known_good": _rel(CONSOLE_LAST_KNOWN_GOOD_JSON),
        },
        "next_safe_action": _live_state_next_action(state, blockers),
    }
    payload = attach_status_source(
        payload,
        source_type="live_probe",
        checked_at=checked_at.isoformat(),
        recheck_command="make provider-lab-refresh-live-state",
        evidence_artifacts=[
            report_path,
            _rel(AUTOMANAGEMENT_REPORT),
            _rel(CONSOLE_LAST_KNOWN_GOOD_JSON),
        ],
    )
    sanitized = _sanitize(payload)
    snapshot = _persist_live_state(sanitized, checked_at=checked_at, session=session)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        LIVE_STATE_REPORT.write_text(_live_state_markdown(sanitized), encoding="utf-8")
        _write_automanagement_report(snapshot)
        _write_console_last_known_good(snapshot)
    return sanitized


def validate_netapp_setup(
    *,
    check_ports: bool = True,
    write_report: bool = True,
    session: Session | None = None,
) -> dict[str, Any]:
    result = read_netapp_live_state(check_ports=check_ports, write_report=write_report, session=session)
    return {
        **result,
        "action": "validate-setup",
        "message": (
            "NetApp setup validation marked the provider configured from live verification."
            if result.get("configured")
            else "NetApp setup validation is blocked by live-state evidence."
        ),
    }


def reset_netapp_runtime_state(*, session: Session | None = None) -> None:
    def apply(session_to_use: Session) -> None:
        record = _get_record(session_to_use)
        if record is not None:
            session_to_use.delete(record)

    _write_with_session(apply, session=session)


def _persist_live_state(payload: dict[str, Any], *, checked_at: datetime, session: Session | None) -> dict[str, Any]:
    def apply(session_to_use: Session) -> dict[str, Any]:
        record = _get_or_create_record(session_to_use)
        configured = bool(payload.get("configured"))
        record.configured = configured
        record.configured_state = _valid_state(payload.get("configured_state"))
        record.source = "live_verification"
        record.last_report_path = _optional_report(payload) or _rel(LIVE_STATE_REPORT)
        record.confidence = _optional_str(payload.get("confidence"))
        if configured:
            record.last_successful_probe_at = checked_at
        record.blockers = [str(item) for item in payload.get("blockers") or [] if str(item)]
        record.data_json = {
            **(record.data_json or {}),
            "legacy_env": _legacy_env_context(),
            "console": payload.get("console") or (record.data_json or {}).get("console") or _empty_console_state(),
            "management": payload.get("management") or {},
            "api": payload.get("api") or {},
            "storage": payload.get("storage") or {},
            "verified_at": checked_at.isoformat() if configured else None,
            "evidence_report_path": record.last_report_path,
            "detected_management_ips": payload.get("detected_management_ips") or {},
            "detected_storage_protocol_readiness": payload.get("detected_storage_protocol_readiness") or {},
        }
        record.updated_at = _utcnow()
        session_to_use.add(record)
        return _record_to_payload(record)

    return _write_with_session(apply, session=session)


def _record_to_payload(record: ProviderRuntimeState | None) -> dict[str, Any]:
    if record is None:
        payload = {
            "provider_id": PROVIDER_ID,
            "device_role": DEVICE_ROLE,
            "checked_at": None,
            "configured": False,
            "configured_state": "not_detected",
            "source": "none",
            "manual_env_flag_required": False,
            "legacy_env": _legacy_env_context(),
            "console": _empty_console_state(),
            "last_successful_probe_at": None,
            "last_report_path": None,
            "confidence": "low",
            "blockers": ["No NetApp live runtime state has been recorded yet."],
            "artifacts": _state_artifacts(),
            "next_safe_action": "Discover the NetApp console or read live NetApp state.",
        }
        return attach_status_source(
            payload,
            source_type="not_checked",
            checked_at=None,
            recheck_command="make provider-lab-refresh-live-state",
            evidence_artifacts=list(_state_artifacts().values()),
        )
    data = record.data_json or {}
    console = data.get("console") if isinstance(data.get("console"), dict) else _empty_console_state()
    if record.discovered_console_port:
        console = {
            **console,
            "discovered_port": record.discovered_console_port,
            "baud": record.discovered_baud,
            "confidence": record.confidence or console.get("confidence"),
            "last_seen": _datetime_iso(record.last_successful_probe_at) or console.get("last_seen"),
            "manual_env_update_required": False,
        }
    console = _prefer_stable_netapp_console(console)
    payload = {
        "provider_id": record.provider_id,
        "device_role": record.device_role,
        "checked_at": _datetime_iso(record.updated_at),
        "configured": bool(record.configured),
        "configured_state": _valid_state(record.configured_state),
        "source": record.source or "runtime_state",
        "manual_env_flag_required": False,
        "legacy_env": _legacy_env_context(),
        "console": console,
        "management": data.get("management") or {},
        "api": data.get("api") or {},
        "storage": data.get("storage") or {},
        "verified_at": data.get("verified_at"),
        "evidence_report_path": data.get("evidence_report_path") or record.last_report_path,
        "detected_management_ips": data.get("detected_management_ips") or {},
        "detected_storage_protocol_readiness": data.get("detected_storage_protocol_readiness") or {},
        "last_successful_probe_at": _datetime_iso(record.last_successful_probe_at),
        "last_report_path": record.last_report_path,
        "confidence": record.confidence or "low",
        "blockers": record.blockers or [],
        "artifacts": _state_artifacts(),
        "next_safe_action": _live_state_next_action(record.configured_state, record.blockers or []),
    }
    return attach_status_source(
        payload,
        source_type="live_cached",
        checked_at=payload["checked_at"],
        recheck_command="make provider-lab-refresh-live-state",
        evidence_artifacts=list(_state_artifacts().values()),
    )


def _get_record(session: Session) -> ProviderRuntimeState | None:
    return session.execute(
        select(ProviderRuntimeState).where(
            ProviderRuntimeState.provider_id == PROVIDER_ID,
            ProviderRuntimeState.device_role == DEVICE_ROLE,
        )
    ).scalar_one_or_none()


def _get_or_create_record(session: Session) -> ProviderRuntimeState:
    record = _get_record(session)
    if record is not None:
        return record
    record = ProviderRuntimeState(
        provider_id=PROVIDER_ID,
        device_role=DEVICE_ROLE,
        configured_state="not_detected",
        configured=False,
        blockers=[],
        data_json={"legacy_env": _legacy_env_context(), "console": _empty_console_state()},
    )
    session.add(record)
    return record


def _write_with_session(callback: Callable[[Session], Any], *, session: Session | None) -> Any:
    if session is not None:
        result = callback(session)
        session.commit()
        return result

    init_database()
    with SessionLocal() as local_session:
        result = callback(local_session)
        local_session.commit()
        return result


def _state_from_console_prompt(prompt_state: str | None, blockers: list[Any]) -> str:
    if prompt_state == "cluster_setup_prompt":
        return "setup_wizard"
    if prompt_state in {"login_required", "password_required"}:
        return "login_required"
    if prompt_state == "existing_cluster_shell":
        return "ontap_detected"
    if prompt_state in {"loader_prompt", "boot_menu", "booting", "sp_bmc_login"}:
        return "console_detected"
    if blockers:
        return "blocked"
    return "not_detected"


def _classify_live_state(
    *,
    cached_state: dict[str, Any],
    management_rest: bool | None,
    api_authenticated: bool,
    storage_ready: bool,
) -> str:
    if api_authenticated and storage_ready:
        return "configured"
    if api_authenticated:
        return "api_authenticated"
    if management_rest is True:
        return "management_reachable"
    cached = _valid_state(cached_state.get("configured_state"))
    if cached in {"console_detected", "login_required", "setup_wizard", "ontap_detected"}:
        return cached
    if management_rest is False:
        return "blocked"
    return "not_detected"


def _live_state_blockers(
    *,
    management_rest: bool | None,
    api_access_present: bool,
    api_probe: dict[str, Any],
    storage: dict[str, Any],
    check_ports: bool,
) -> list[str]:
    blockers: list[str] = []
    if not check_ports:
        blockers.append("Live NetApp port/API validation was not run.")
    elif management_rest is False:
        blockers.append("NetApp cluster management REST is not reachable.")
    elif management_rest is None:
        blockers.append("NetApp cluster management host is missing.")
    if not api_access_present:
        blockers.append("NetApp API access values are missing; keep any values local and redacted.")
    elif api_probe.get("authenticated") is not True:
        blockers.append(str(api_probe.get("reason") or "NetApp API authentication was not verified."))
    if not storage["ready"]:
        blockers.extend(storage["blockers"])
    return blockers


def _storage_protocol_readiness() -> dict[str, Any]:
    protocol = settings.netapp_storage_protocol.lower()
    blockers = []
    if protocol == "nfs":
        if not settings.netapp_nfs_lifs:
            blockers.append("No NetApp NFS LIFs are planned or detected.")
        if not settings.netapp_nfs_mount_path:
            blockers.append("NetApp NFS mount path is missing.")
        if not settings.netapp_nfs_datastore_name:
            blockers.append("NetApp NFS datastore name is missing.")
    elif protocol == "iscsi":
        if not settings.netapp_iscsi_lifs:
            blockers.append("No NetApp iSCSI LIFs are planned or detected.")
    else:
        blockers.append(f"Unsupported NetApp storage protocol `{settings.netapp_storage_protocol}`.")
    return {
        "protocol": protocol,
        "ready": not blockers,
        "source": "bootstrap_profile_and_live_api_validation",
        "nfs_lifs_detected": list(settings.netapp_nfs_lifs) if protocol == "nfs" else [],
        "iscsi_lifs_detected": list(settings.netapp_iscsi_lifs) if protocol == "iscsi" else [],
        "blockers": blockers,
    }


def _safe_ontap_api_probe() -> dict[str, Any]:
    host = settings.netapp_cluster_mgmt_ip
    if not host or not settings.netapp_api_username or not settings.netapp_api_password:
        return _api_probe_not_attempted("NetApp API host or access values are missing.")
    fallback_reason = ""
    try:
        response = _ontap_api_cluster_get(host, verify=settings.netapp_api_verify_tls)
    except (httpx.HTTPError, OSError) as exc:
        fallback_reason = f"{exc.__class__.__name__}"
        if not settings.netapp_api_verify_tls:
            return {
                "status": "blocked",
                "authenticated": False,
                "reason": f"NetApp API GET failed with {fallback_reason}.",
            }
        try:
            response = _ontap_api_cluster_get(host, verify=False)
        except (httpx.HTTPError, OSError) as fallback_exc:
            return {
                "status": "blocked",
                "authenticated": False,
                "reason": f"NetApp API GET failed with {fallback_reason}; TLS-disabled fallback failed with {fallback_exc.__class__.__name__}.",
            }
    if 200 <= response.status_code < 300:
        reason = "Safe ONTAP API GET authenticated."
        if fallback_reason:
            reason = f"{reason} TLS-disabled local-lab fallback was used after {fallback_reason}."
        return {"status": "ready", "authenticated": True, "reason": reason}
    if response.status_code in {401, 403}:
        return {"status": "blocked", "authenticated": False, "reason": "NetApp API authentication failed."}
    return {
        "status": "blocked",
        "authenticated": False,
        "reason": f"Safe ONTAP API GET returned HTTP {response.status_code}.",
    }


def _ontap_api_cluster_get(host: str, *, verify: bool) -> httpx.Response:
    with httpx.Client(verify=verify, timeout=3.0, trust_env=False) as client:
        return client.get(
            f"https://{host}/api/cluster?fields=version",
            auth=(settings.netapp_api_username, settings.netapp_api_password),
            headers={"Accept": "application/json"},
        )


def _api_probe_not_attempted(reason: str) -> dict[str, Any]:
    return {"status": "not_attempted", "authenticated": None, "reason": reason}


def _reachable(host: str | None, port: int, check_ports: bool) -> bool | None:
    if not host or not check_ports:
        return None
    try:
        with socket.create_connection((host, port), timeout=2.5):
            return True
    except OSError:
        return False


def _detected_management_ips(management_rest: bool | None) -> dict[str, Any]:
    if management_rest is not True:
        return {}
    return {
        "cluster": settings.netapp_cluster_mgmt_ip,
        "source": "live_cluster_management_reachability",
    }


def _live_state_confidence(current: dict[str, Any], management_rest: bool | None) -> str:
    if management_rest is True:
        return "medium"
    console = current.get("console") if isinstance(current.get("console"), dict) else {}
    return str(console.get("confidence") or current.get("confidence") or "low")


def _live_state_next_action(state: Any, blockers: list[Any]) -> str:
    state_value = _valid_state(state)
    if state_value == "configured":
        return "Manual env flag not required; continue with read-only Build Verification and keep apply gates separate."
    if state_value == "setup_wizard":
        return "Complete or validate NetApp setup, then run Validate NetApp Setup."
    if state_value == "login_required":
        return "Use approved credentials only through the live validation path; do not paste secrets into the UI."
    if state_value == "management_reachable":
        return "Run safe ONTAP API authentication validation, then validate storage readiness."
    if state_value == "api_authenticated":
        return "Validate storage protocol readiness before marking NetApp configured."
    if blockers:
        return str(blockers[0])
    return "Discover the NetApp console, then read live NetApp state."


def _write_console_last_known_good(snapshot: dict[str, Any]) -> None:
    console = snapshot.get("console") if isinstance(snapshot.get("console"), dict) else {}
    console = _prefer_stable_netapp_console(console)
    payload = _sanitize(
        {
            "provider_id": PROVIDER_ID,
            "device_role": DEVICE_ROLE,
            "checked_at": snapshot.get("checked_at"),
            "discovered_console_port": console.get("discovered_port"),
            "discovered_baud": console.get("baud"),
            "confidence": console.get("confidence") or snapshot.get("confidence"),
            "last_seen": console.get("last_seen") or snapshot.get("last_successful_probe_at"),
            "source": console.get("source"),
            "selection_source": console.get("selection_source"),
            "manual_env_update_required": False,
            "configured_port_hint_used_as_hint_only": bool(console.get("configured_port_hint")),
            "redaction_applied": True,
        }
    )
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    CONSOLE_LAST_KNOWN_GOOD_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_automanagement_report(snapshot: dict[str, Any]) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    AUTOMANAGEMENT_REPORT.write_text(_automanagement_markdown(snapshot), encoding="utf-8")


def _live_state_markdown(payload: dict[str, Any]) -> str:
    console = payload.get("console") if isinstance(payload.get("console"), dict) else {}
    management = payload.get("management") if isinstance(payload.get("management"), dict) else {}
    api = payload.get("api") if isinstance(payload.get("api"), dict) else {}
    storage = payload.get("storage") if isinstance(payload.get("storage"), dict) else {}
    lines = [
        "# NetApp Live State Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Configured state: `{payload.get('configured_state')}`",
        f"- Configured: `{payload.get('configured')}`",
        f"- Source: `{payload.get('source')}`",
        "- Manual env flag required: `False`",
        "",
        "## Console",
        "",
        f"- Discovered port: `{console.get('discovered_port') or 'none'}`",
        f"- Baud: `{console.get('baud') or 'none'}`",
        f"- Confidence: `{console.get('confidence') or 'none'}`",
        f"- Last seen: `{console.get('last_seen') or 'none'}`",
        f"- Source: `{console.get('source') or 'none'}`",
        "",
        "## Live Checks",
        "",
        f"- Cluster REST 443 reachable: `{management.get('rest_443_reachable')}`",
        f"- Cluster SSH 22 reachable: `{management.get('ssh_22_reachable')}`",
        f"- API authenticated: `{api.get('authenticated')}`",
        f"- Storage protocol: `{storage.get('protocol') or 'unknown'}` ready=`{storage.get('ready')}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "", "- No secrets are written to this report.", "- No NetApp write, setup, storage, upgrade, reboot, wipe, or apply command is run."])
    return "\n".join(lines) + "\n"


def _automanagement_markdown(snapshot: dict[str, Any]) -> str:
    console = snapshot.get("console") if isinstance(snapshot.get("console"), dict) else {}
    return "\n".join(
        [
            "# NetApp State Automanagement Report",
            "",
            f"- Provider: `{snapshot.get('provider_id')}`",
            f"- Configured state: `{snapshot.get('configured_state')}`",
            f"- Configured: `{snapshot.get('configured')}`",
            f"- Source: `{snapshot.get('source')}`",
            f"- Last evidence at: `{snapshot.get('verified_at') or snapshot.get('last_successful_probe_at') or 'not verified'}`",
            f"- Evidence report: `{snapshot.get('evidence_report_path') or snapshot.get('last_report_path') or 'none'}`",
            "- Manual env flag required: `False`",
            "",
            "## Console Last Known Good",
            "",
            f"- Port: `{console.get('discovered_port') or 'none'}`",
            f"- Baud: `{console.get('baud') or 'none'}`",
            f"- Confidence: `{console.get('confidence') or 'none'}`",
            f"- Last seen: `{console.get('last_seen') or 'none'}`",
            f"- Source: `{console.get('source') or 'none'}`",
            "",
            "## Operator Note",
            "",
            "- `.env.local.real-lab` is bootstrap/profile input only; discovered console and configured state are tracked here.",
            "- Secrets are redacted and are never written to runtime state.",
            "",
        ]
    )


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value:
            continue
        if any(fragment in key.lower() for fragment in ("password", "token", "secret", "credential", "authorization", "cookie")):
            values.append(value)
    return values


def _legacy_env_context() -> dict[str, Any]:
    return {
        "netapp_configured_env": settings.netapp_configured,
        "netapp_configured_env_role": "legacy_override_or_desired_flag",
        "netapp_console_port_env_role": "optional_hint_only",
        "manual_state_tracking_required": False,
    }


def _empty_console_state() -> dict[str, Any]:
    return {
        "discovered_port": None,
        "baud": None,
        "confidence": "low",
        "last_seen": None,
        "source": "none",
        "selection_source": None,
        "prompt_state": None,
        "prompt_label": None,
        "configured_port_hint": settings.netapp_console_port,
        "detected_automatically": False,
        "manual_env_update_required": False,
    }


def _prefer_stable_netapp_console(console: dict[str, Any]) -> dict[str, Any]:
    stable = _stable_netapp_console_from_artifacts()
    if not stable:
        return console
    current_port = _optional_str(console.get("discovered_port"))
    current_prompt = _optional_str(console.get("prompt_state"))
    current_confidence = _optional_str(console.get("confidence"))
    current_seen = _parse_datetime(console.get("last_seen"))
    stable_seen = _parse_datetime(stable.get("last_seen"))
    if current_seen and stable_seen and current_seen >= stable_seen:
        return console
    if _is_stable_microchip_console(current_port, current_prompt):
        return console
    if current_port and current_confidence == "high" and current_prompt == "login_required":
        return console
    return {**console, **stable}


def _stable_netapp_console_from_artifacts() -> dict[str, Any] | None:
    for path in (CONSOLE_STATE_JSON, CONSOLE_AUTODISCOVERY_JSON):
        payload = _read_json(path)
        if not payload:
            continue
        port = _optional_str(payload.get("selected_port"))
        prompt_state = _optional_str(payload.get("selected_prompt_state"))
        baud = _optional_int(payload.get("selected_baud"))
        if not _is_stable_microchip_console(port, prompt_state):
            continue
        return {
            "discovered_port": port,
            "baud": baud,
            "confidence": _optional_str(payload.get("selection_confidence")) or "high",
            "last_seen": _optional_str(payload.get("checked_at")),
            "source": "autodiscovery",
            "selection_source": _optional_str(payload.get("selection_source")),
            "prompt_state": prompt_state,
            "prompt_label": _optional_str(payload.get("selected_prompt_label")),
            "configured_port_hint": _optional_str(payload.get("configured_port_hint")),
            "detected_automatically": True,
            "manual_env_update_required": False,
        }
    return None


def _is_stable_microchip_console(port: str | None, prompt_state: str | None) -> bool:
    return bool(
        port
        and "Microchip_Technology_Inc._MCP2221" in port
        and prompt_state == "login_required"
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _state_artifacts() -> dict[str, str]:
    return {
        "state_report": _rel(LIVE_STATE_REPORT),
        "automanagement_report": _rel(AUTOMANAGEMENT_REPORT),
        "console_last_known_good": _rel(CONSOLE_LAST_KNOWN_GOOD_JSON),
    }


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _optional_report(payload: dict[str, Any]) -> str | None:
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    report = artifacts.get("report") or artifacts.get("state_report")
    return str(report) if report else None


def _console_origin(selected_port: str | None, selection_source: Any) -> str:
    if selected_port and settings.netapp_console_port and selected_port == settings.netapp_console_port:
        return "hint"
    source = str(selection_source or "")
    if source == "configured-port-hint":
        return "hint"
    if selected_port:
        return "autodiscovery"
    return "none"


def _valid_state(value: Any) -> str:
    text = str(value or "not_detected")
    return text if text in VALID_CONFIGURED_STATES else "blocked"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _datetime_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _utcnow() -> datetime:
    return datetime.now(UTC)
