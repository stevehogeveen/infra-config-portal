from __future__ import annotations

import json
import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import LAB_ESXI_MANAGEMENT_IP, settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.ilo_redfish import IloRedfishAdapter, IloRedfishConfig, _base_url
from app.providers.redaction import redact_sensitive
from app.services.hpe_raid import REPO_ROOT, SYSTEM_PATH, _get_redfish_resource, _post_system_reset

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
RECOVERY_REPORT = CODEX_RUN_DIR / "esxi-reachability-remediation-report.md"
RECOVERY_JSON = CODEX_RUN_DIR / "esxi-reachability-remediation-redacted.json"
VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-post-recovery-validation-report.md"
VALIDATION_JSON = CODEX_RUN_DIR / "esxi-post-recovery-validation-redacted.json"

RECOVERY_CONFIRM_PHRASE = "RECOVER ESXI MANAGEMENT"
ASSERT_POWER_OFF_CONFIRM_PHRASE = "SERVER IS OFF"
SYSTEM_RESET_TARGET = "/redfish/v1/systems/1/Actions/ComputerSystem.Reset/"


def recover_esxi_management(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    target = _target_state()
    pre_system = _safe_system_state()
    ilo_probe = _safe_ilo_probe()
    gates = _recovery_gates()
    blockers = _recovery_blockers(target, pre_system, ilo_probe, gates)
    apply_attempted = False
    apply_result: dict[str, Any] = {
        "power_on_attempted": False,
        "force_restart_attempted": False,
        "result": "not_attempted",
    }

    operator_asserted_power_off = _operator_asserted_power_off(pre_system, ilo_probe, gates)

    if not blockers and target["https_reachable"]:
        status = "ready"
        message = "ESXi management is already reachable; no recovery action was required."
    elif not blockers and (pre_system.get("power_state") == "Off" or operator_asserted_power_off):
        apply_attempted = True
        apply_result = _power_on_and_wait(target, operator_asserted=operator_asserted_power_off)
        status = "recovered" if apply_result.get("esxi_https_reachable_after") else "blocked"
        message = (
            "ESXi host power-on was requested and management is reachable."
            if status == "recovered"
            else "ESXi host power-on was requested, but management did not become reachable before timeout."
        )
        if status != "recovered":
            if apply_result.get("result") == "power_on_rejected":
                reset_status = (apply_result.get("reset") or {}).get("status_code")
                blockers = [f"iLO rejected the guarded power-on request with HTTP {reset_status}."]
                message = "iLO rejected the guarded power-on request before ESXi polling could start."
            else:
                blockers = ["ESXi management did not become reachable after guarded power-on."]
    elif not blockers:
        status = "blocked"
        message = "ESXi is powered on or power state is unknown, but management is not reachable."
        blockers = [
            "Automatic management reconfiguration is not available without ESXi API/SSH or a verified installer/rebuild lane.",
        ]
    else:
        status = "blocked"
        message = "ESXi management recovery is blocked before any power or host action."

    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-management-recovery",
        "checked_at": checked_at,
        "status": status,
        "message": message,
        "mode": settings.provider_mode,
        "apply_enabled": not blockers,
        "source_type": "live_probe",
        "freshness": "current",
        "current_state": {
            "esxi_https_reachable": target["https_reachable"],
            "esxi_ssh_reachable": target["ssh_reachable"],
            "ilo_https_reachable": target["ilo_https_reachable"],
            "ilo_redfish_status": ilo_probe.get("status"),
            "ilo_redfish_message": ilo_probe.get("message"),
            "ilo_system_status_code": pre_system.get("status_code"),
            "power_state": pre_system.get("power_state"),
        },
        "target_state": {
            "esxi_management_ip": target["esxi_host"],
            "https_port": 443,
            "ssh_port": 22,
            "management_network": "active lab 192.168.1.0/24",
        },
        "recovery_method": _recovery_method(target, pre_system, ilo_probe),
        "flag_state": gates["flag_state"],
        "required_flags": _required_flags(),
        "apply": {
            **apply_result,
            "attempted": apply_attempted,
        },
        "blockers": blockers,
        "warnings": _warnings(target, pre_system, ilo_probe),
        "not_attempted": _not_attempted(apply_attempted),
        "artifacts": {
            "report": _rel(RECOVERY_REPORT),
            "json": _rel(RECOVERY_JSON),
            "post_recovery_validation_report": _rel(VALIDATION_REPORT),
        },
        "next_safe_action": _next_action(blockers, target, pre_system, ilo_probe),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(RECOVERY_JSON, RECOVERY_REPORT, sanitized, _markdown)
    return sanitized


def validate_esxi_post_recovery(*, write_report: bool = True) -> dict[str, Any]:
    target = _target_state()
    blockers = []
    if not target["https_reachable"]:
        blockers.append(f"ESXi HTTPS is not reachable at {target['esxi_host']}:443.")
    warnings = []
    if not target["ssh_reachable"]:
        warnings.append("ESXi SSH is not reachable or not enabled.")
    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-post-recovery-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "ESXi post-recovery validation completed with TCP checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe",
        "freshness": "current",
        "target_state": {
            "esxi_management_ip": target["esxi_host"],
            "https_port": 443,
            "ssh_port": 22,
        },
        "checks": {
            "https": target["https_check"],
            "ssh": target["ssh_check"],
        },
        "blockers": blockers,
        "warnings": warnings,
        "not_attempted": [
            "ESXi reboot",
            "ESXi management network reconfiguration",
            "datastore add/remove",
            "VM operation",
            "iLO power action",
        ],
        "artifacts": {
            "report": _rel(VALIDATION_REPORT),
            "json": _rel(VALIDATION_JSON),
            "recovery_report": _rel(RECOVERY_REPORT),
        },
        "next_safe_action": (
            "Mount the NetApp NFS datastore after HTTPS/govc access is ready."
            if not blockers
            else "Resolve iLO authorization or ESXi boot/management configuration, then rerun recovery."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(VALIDATION_JSON, VALIDATION_REPORT, sanitized, _markdown)
    return sanitized


def _target_state() -> dict[str, Any]:
    esxi_host = settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP
    ilo_host = settings.ilo_test_host or _profile_ilo_host()
    https = _tcp_check(esxi_host, 443)
    ssh = _tcp_check(esxi_host, 22)
    ilo_https = _tcp_check(ilo_host, 443)
    return {
        "esxi_host": esxi_host,
        "ilo_host": ilo_host,
        "https_check": https,
        "ssh_check": ssh,
        "ilo_https_check": ilo_https,
        "https_reachable": https["reachable"],
        "ssh_reachable": ssh["reachable"],
        "ilo_https_reachable": ilo_https["reachable"],
    }


def _profile_ilo_host() -> str | None:
    try:
        from app.services.lab_profiles import active_lab_profile_context

        context = active_lab_profile_context()
    except Exception:
        return None
    plan = context.get("resolved_address_plan") if isinstance(context, dict) else {}
    if not isinstance(plan, dict):
        return None
    value = str(plan.get("ilo") or "").strip()
    return value or None


def _safe_system_state() -> dict[str, Any]:
    try:
        response = _get_redfish_resource(SYSTEM_PATH)
    except Exception as exc:
        return {
            "status_code": None,
            "error_class": exc.__class__.__name__,
            "power_state": None,
            "boot": {},
        }
    body = response.get("body") if response.get("status_code") and isinstance(response.get("body"), dict) else {}
    boot = body.get("Boot") if isinstance(body.get("Boot"), dict) else {}
    return {
        "status_code": response.get("status_code"),
        "error_class": response.get("error_class"),
        "power_state": body.get("PowerState"),
        "health": ((body.get("Status") or {}) if isinstance(body.get("Status"), dict) else {}).get("Health"),
        "boot": {
            "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled"),
            "boot_source_override_target": boot.get("BootSourceOverrideTarget"),
        },
    }


def _safe_ilo_probe() -> dict[str, Any]:
    try:
        return IloRedfishAdapter(provider_mode=settings.provider_mode).probe()
    except Exception as exc:
        return {
            "status": "failed",
            "message": "iLO Redfish probe failed before inventory completed.",
            "blockers": [exc.__class__.__name__],
        }


def _recovery_gates() -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "lab_allow_power_actions": os.getenv("LAB_ALLOW_POWER_ACTIONS") == "true" or policy.allow_power_actions,
        "esxi_recovery_apply": os.getenv("ESXI_RECOVERY_APPLY") == "true",
        "esxi_recovery_confirm": os.getenv("ESXI_RECOVERY_CONFIRM") == RECOVERY_CONFIRM_PHRASE,
        "esxi_recovery_assume_power_off": os.getenv("ESXI_RECOVERY_ASSUME_POWER_OFF") == "true",
        "esxi_recovery_assume_power_off_confirm": (
            os.getenv("ESXI_RECOVERY_ASSUME_POWER_OFF_CONFIRM") == ASSERT_POWER_OFF_CONFIRM_PHRASE
        ),
    }
    blockers = policy.action_blockers("ilo.power-action", ActionCategory.POWER_ACTION)
    if not flag_state["esxi_recovery_apply"]:
        blockers.append("ESXI_RECOVERY_APPLY=true is required.")
    if not flag_state["esxi_recovery_confirm"]:
        blockers.append(f'ESXI_RECOVERY_CONFIRM="{RECOVERY_CONFIRM_PHRASE}" is required.')
    return {"flag_state": flag_state, "blockers": list(dict.fromkeys(blockers))}


def _recovery_blockers(
    target: dict[str, Any],
    pre_system: dict[str, Any],
    ilo_probe: dict[str, Any],
    gates: dict[str, Any],
) -> list[str]:
    if target["https_reachable"]:
        return []
    blockers: list[str] = []
    operator_asserted_power_off = _operator_asserted_power_off(pre_system, ilo_probe, gates)
    if not target["ilo_https_reachable"]:
        blockers.append(f"iLO HTTPS is not reachable at {target['ilo_host']}:443.")
    if (pre_system.get("status_code") in {401, 403} or ilo_probe.get("status") != "ok") and not operator_asserted_power_off:
        blockers.append(
            "iLO Redfish authorization is blocked; the app cannot read power state or issue guarded power recovery."
        )
    if pre_system.get("power_state") not in {"Off"} and not operator_asserted_power_off:
        blockers.append(
            "The app can only auto-recover a verified powered-off host; current power state is not confirmed as Off."
        )
    blockers.extend(gates["blockers"])
    return list(dict.fromkeys(blockers))


def _recovery_method(target: dict[str, Any], pre_system: dict[str, Any], ilo_probe: dict[str, Any]) -> dict[str, Any]:
    if target["https_reachable"]:
        return {"method": "none", "reason": "ESXi HTTPS is already reachable."}
    if _operator_asserted_power_off(pre_system, ilo_probe, _recovery_gates()):
        return {
            "method": "operator_asserted_redfish_power_on",
            "reason": "Operator asserted the host is powered off; only ResetType=On may be attempted.",
        }
    if pre_system.get("status_code") in {401, 403} or ilo_probe.get("status") != "ok":
        return {
            "method": "blocked_before_apply",
            "reason": "iLO authentication/authorization does not permit system inventory or power action.",
        }
    if pre_system.get("power_state") == "Off":
        return {"method": "ilo_redfish_power_on", "reason": "Host is verified Off and can be powered on through iLO."}
    return {
        "method": "operator_or_rebuild_required",
        "reason": "Management is unreachable and power/boot state does not identify a safe automatic fix.",
    }


def _operator_asserted_power_off(
    pre_system: dict[str, Any],
    ilo_probe: dict[str, Any],
    gates: dict[str, Any],
) -> bool:
    flags = gates.get("flag_state") if isinstance(gates.get("flag_state"), dict) else {}
    if not flags.get("esxi_recovery_assume_power_off") or not flags.get("esxi_recovery_assume_power_off_confirm"):
        return False
    if pre_system.get("power_state") == "On":
        return False
    return _ilo_identity_available(ilo_probe)


def _ilo_identity_available(ilo_probe: dict[str, Any]) -> bool:
    if not isinstance(ilo_probe, dict):
        return False
    if isinstance(ilo_probe.get("legacy_identity"), dict) and ilo_probe["legacy_identity"]:
        return True
    detection = ilo_probe.get("endpoint_detection") if isinstance(ilo_probe.get("endpoint_detection"), dict) else {}
    if detection.get("redfish_status") == "available":
        return True
    root = detection.get("redfish_root_payload") if isinstance(detection.get("redfish_root_payload"), dict) else {}
    product = str(root.get("Product") or "")
    vendor = str(root.get("Vendor") or "")
    return "ProLiant" in product or vendor == "HPE"


def _power_on_and_wait(target: dict[str, Any], *, operator_asserted: bool = False) -> dict[str, Any]:
    reset = _post_standard_system_power_on() if operator_asserted else _post_system_reset("On")
    status_code = int(reset.get("status_code") or 0)
    if status_code < 200 or status_code >= 300:
        return {
            "power_on_attempted": True,
            "force_restart_attempted": False,
            "operator_asserted_power_off": operator_asserted,
            "result": "power_on_rejected",
            "reset": reset,
            "poll_checks": [],
            "esxi_https_reachable_after": False,
        }
    deadline = time.monotonic() + float(os.getenv("ESXI_RECOVERY_WAIT_SECONDS", "300"))
    poll_seconds = float(os.getenv("ESXI_RECOVERY_POLL_SECONDS", "15"))
    checks: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        check = _tcp_check(target["esxi_host"], 443)
        checks.append(check)
        if check["reachable"]:
            break
        time.sleep(poll_seconds)
    return {
        "power_on_attempted": True,
        "force_restart_attempted": False,
        "operator_asserted_power_off": operator_asserted,
        "result": "power_on_requested",
        "reset": reset,
        "poll_checks": checks[-10:],
        "esxi_https_reachable_after": bool(checks and checks[-1].get("reachable")),
    }


def _post_standard_system_power_on() -> dict[str, Any]:
    config = IloRedfishConfig.from_settings()
    if not config.target_candidates or not config.username or not config.password:
        raise RuntimeError("Complete iLO configuration is required for server power-on.")
    timeout = httpx.Timeout(config.timeout_seconds)
    response: httpx.Response | None = None
    candidate = config.target_candidates[0]
    try:
        with httpx.Client(
            auth=(config.username, config.password),
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
            verify=config.verify_tls,
        ) as client:
            response = client.post(_base_url(candidate["host"]) + SYSTEM_RESET_TARGET, json={"ResetType": "On"})
    except httpx.HTTPError as exc:
        return _sanitize(
            {
                "method": "POST",
                "path": SYSTEM_RESET_TARGET,
                "target_source": candidate.get("source"),
                "status": "failed",
                "error_class": exc.__class__.__name__,
                "request": {"ResetType": "On"},
            }
        )
    try:
        body: Any = response.json()
    except ValueError:
        body = {"text": response.text[:1000]}
    return _sanitize(
        {
            "method": "POST",
            "path": SYSTEM_RESET_TARGET,
            "target_source": candidate.get("source"),
            "status_code": response.status_code,
            "request": {"ResetType": "On"},
            "response": body if isinstance(body, dict) else {"value": body},
        }
    )


def _tcp_check(host: str | None, port: int) -> dict[str, Any]:
    if not host:
        return {
            "host": None,
            "port": port,
            "reachable": False,
            "status": "not_configured",
            "detail": "Host is not configured.",
        }
    try:
        with socket.create_connection((host, port), timeout=3):
            return {
                "host": host,
                "port": port,
                "reachable": True,
                "status": "ready",
                "detail": f"TCP {port} reachable.",
            }
    except OSError as exc:
        return {
            "host": host,
            "port": port,
            "reachable": False,
            "status": "blocked",
            "detail": f"TCP {port} failed with {exc.__class__.__name__}.",
        }


def _required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "LAB_ALLOW_POWER_ACTIONS=true",
        "ESXI_RECOVERY_APPLY=true",
        f'ESXI_RECOVERY_CONFIRM="{RECOVERY_CONFIRM_PHRASE}"',
        'Optional auth-bypass power-on only: ESXI_RECOVERY_ASSUME_POWER_OFF=true',
        f'Optional auth-bypass power-on only: ESXI_RECOVERY_ASSUME_POWER_OFF_CONFIRM="{ASSERT_POWER_OFF_CONFIRM_PHRASE}"',
    ]


def _warnings(target: dict[str, Any], pre_system: dict[str, Any], ilo_probe: dict[str, Any]) -> list[str]:
    warnings = [
        "Recovery does not reconfigure ESXi networking unless ESXi API/SSH is reachable.",
        "Power-on is the only automatic recovery action; rebuild/install remains a separate guarded workflow.",
    ]
    if not target["ssh_reachable"]:
        warnings.append("ESXi SSH is not reachable or not enabled.")
    if pre_system.get("status_code") == 401 or ilo_probe.get("status") != "ok":
        warnings.append("iLO root is reachable, but Redfish inventory/auth is blocked for the configured account.")
    if _operator_asserted_power_off(pre_system, ilo_probe, _recovery_gates()):
        warnings.append("Operator asserted the server is off; recovery may attempt only ResetType=On without a prior power-state read.")
    return list(dict.fromkeys(warnings))


def _not_attempted(apply_attempted: bool) -> list[str]:
    skipped = [
        "ESXi management network reconfiguration",
        "ESXi reinstall/rebuild",
        "virtual media insert/eject",
        "boot-order change",
        "datastore add/remove",
        "VM deploy/power operation",
    ]
    if not apply_attempted:
        skipped.insert(0, "iLO power action")
    return skipped


def _next_action(
    blockers: list[str],
    target: dict[str, Any],
    pre_system: dict[str, Any],
    ilo_probe: dict[str, Any],
) -> str:
    if not blockers and target["https_reachable"]:
        return "Run ESXi post-recovery validation, then mount the NetApp NFS datastore."
    if _operator_asserted_power_off(pre_system, ilo_probe, _recovery_gates()):
        return "Wait for ESXi HTTPS to return, then rerun post-recovery validation."
    if pre_system.get("status_code") in {401, 403} or ilo_probe.get("status") != "ok":
        return "Fix iLO account permissions/authentication, or rerun with the explicit server-off assertion if the host is visibly powered off."
    if pre_system.get("power_state") == "Off":
        return "Run the guarded recovery command with the exact power-action flags from this report."
    return "Use iLO console/KVM or the guarded ESXi rebuild workflow to restore management on 192.168.1.203."


def _markdown(payload: dict[str, Any]) -> str:
    current = payload.get("current_state") or {}
    target = payload.get("target_state") or {}
    method = payload.get("recovery_method") or {}
    lines = [
        "# ESXi Reachability Remediation Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Provider mode: `{payload.get('mode')}`",
        "",
        "## Current State",
        f"- ESXi HTTPS reachable: `{current.get('esxi_https_reachable')}`",
        f"- ESXi SSH reachable: `{current.get('esxi_ssh_reachable')}`",
        f"- iLO HTTPS reachable: `{current.get('ilo_https_reachable')}`",
        f"- iLO Redfish status: `{current.get('ilo_redfish_status')}`",
        f"- iLO system status code: `{current.get('ilo_system_status_code')}`",
        f"- Power state: `{current.get('power_state')}`",
        "",
        "## Target State",
        f"- ESXi management IP: `{target.get('esxi_management_ip')}`",
        f"- HTTPS: `{target.get('https_port')}`",
        f"- SSH: `{target.get('ssh_port')}`",
        "",
        "## Recovery Method",
        f"- Method: `{method.get('method')}`",
        f"- Reason: {method.get('reason')}",
        "",
        "## Required Flags",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Safety", "- No ESXi, iLO, datastore, virtual media, boot-order, or VM write is run unless the recovery gates pass."])
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
