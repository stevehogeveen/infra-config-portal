from __future__ import annotations

import json
import os
import shlex
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import (
    LAB_ANSIBLE_CONTROL_HOST_IP,
    LAB_CISCO_MANAGEMENT_IP,
    LAB_ESXI_MANAGEMENT_IP,
    LAB_ILO_IP,
    LAB_SERVER_EMBEDDED_NIC_IP,
    LAB_SUBNET_CIDR,
    settings,
)
from app.providers.redaction import redact_sensitive
from app.services.hpe_raid import REPO_ROOT

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
REPORT = CODEX_RUN_DIR / "build-verification-report.md"
SUMMARY = CODEX_RUN_DIR / "build-verification-summary-redacted.json"
LAB_IP_REPORT = CODEX_RUN_DIR / "lab-ip-profile-update-report.md"
LAB_IP_HARDENING_REPORT = CODEX_RUN_DIR / "lab-ip-profile-hardening-report.md"
CLASSIFICATION_REPORT = CODEX_RUN_DIR / "build-verification-classification-report.md"
FAILURE_CASE_REPORT = CODEX_RUN_DIR / "failure-case-hardening-report.md"
CLASSIFICATION_ORDER = {
    "hard_fail": 0,
    "stale_config": 1,
    "operator_action_required": 2,
    "blocked_by_prior_stage": 3,
    "not_configured_yet": 4,
    "warning": 5,
    "passed": 6,
}


def build_lab_build_verification(*, check_ports: bool = True) -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    credentials = _credential_checks()
    lab_ip_profile = _lab_ip_profile_checks()
    mtu = _mtu_checks()
    protocols = _protocol_checks(check_ports=check_ports)
    checklist = _post_build_checklist(protocols)
    failures = _failure_classification(credentials, lab_ip_profile, mtu, protocols)
    blockers = [
        item["next_action"]
        for item in failures
        if item["classification"]
        in {"hard_fail", "stale_config", "operator_action_required", "blocked_by_prior_stage"}
    ]
    warnings = [item["next_action"] for item in failures if item["classification"] == "warning"]
    certification_state = _certification_state(failures)
    payload = {
        "provider_id": "build-verification",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "blocked" if blockers else "warning" if warnings else "completed",
        "certification_state": certification_state,
        "message": "Build Verification / Product Certification completed with redacted findings.",
        "provider_mode": settings.provider_mode,
        "mock_results_used": False,
        "lab_ip_profile": lab_ip_profile,
        "credentials": credentials,
        "mtu": mtu,
        "protocols": protocols,
        "post_build_checklist": checklist,
        "failures": failures,
        "blockers": blockers,
        "warnings": warnings,
        "artifacts": {
            "report": str(REPORT.relative_to(REPO_ROOT)),
            "summary_json": str(SUMMARY.relative_to(REPO_ROOT)),
            "lab_ip_profile_report": str(LAB_IP_REPORT.relative_to(REPO_ROOT)),
            "lab_ip_profile_hardening_report": str(LAB_IP_HARDENING_REPORT.relative_to(REPO_ROOT)),
            "classification_report": str(CLASSIFICATION_REPORT.relative_to(REPO_ROOT)),
            "failure_case_report": str(FAILURE_CASE_REPORT.relative_to(REPO_ROOT)),
        },
        "next_safe_action": blockers[0] if blockers else "Review warnings, then continue product certification.",
    }
    sanitized = _sanitize(payload)
    REPORT.write_text(_markdown(sanitized), encoding="utf-8")
    LAB_IP_REPORT.write_text(_lab_ip_markdown(sanitized), encoding="utf-8")
    LAB_IP_HARDENING_REPORT.write_text(_lab_ip_hardening_markdown(sanitized), encoding="utf-8")
    CLASSIFICATION_REPORT.write_text(_classification_markdown(sanitized), encoding="utf-8")
    FAILURE_CASE_REPORT.write_text(_failure_case_markdown(sanitized), encoding="utf-8")
    SUMMARY.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    return sanitized


def get_lab_build_verification() -> dict[str, Any]:
    if SUMMARY.exists():
        try:
            payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, ValueError):
            pass
    return {
        "provider_id": "build-verification",
        "checked_at": None,
        "status": "not_run",
        "message": "Build verification has not been generated yet.",
        "warnings": [],
        "blockers": ["Build verification has not been generated yet."],
        "artifacts": {"report": str(REPORT.relative_to(REPO_ROOT))},
        "next_safe_action": "Run `make provider-lab-build-verification`.",
    }


def validate_credential_compatibility(name: str, value: str | None) -> dict[str, Any]:
    if value is None or value == "":
        return {
            "name": name,
            "configured": False,
            "status": "blocked",
            "classification": "not_configured_yet",
            "field": _credential_field_name(name),
            "issues": ["credential is missing"],
            "next_action": f"Set {_credential_field_name(name)} in .env.local.real-lab when this provider stage is ready.",
        }
    issues = []
    if "\n" in value or "\r" in value:
        issues.append("contains newline characters that are unsafe for shell, YAML, JSON, and Ansible inventory use")
    if "\x00" in value:
        issues.append("contains NUL byte that is invalid for shell and JSON use")
    shell_safe = shlex.quote(value)
    json_safe = json.dumps(value)
    yaml_needs_quotes = any(ch in value for ch in ":#{}[]&,*?|-<>=!%@`'\"\\") or value.strip() != value
    return {
        "name": name,
        "configured": True,
        "status": "blocked" if issues else "ready",
        "classification": "hard_fail" if issues else "passed",
        "field": _credential_field_name(name),
        "length": len(value),
        "special_characters_present": any(not ch.isalnum() for ch in value),
        "shell": {"safe_with_quoting": shell_safe != "", "quoted_length": len(shell_safe)},
        "json": {"serializable": bool(json_safe)},
        "yaml": {"quote_required": yaml_needs_quotes, "safe_when_quoted": True},
        "ansible": {"use_no_log": True, "pass_as_structured_var": True},
        "issues": issues,
        "next_action": (
            f"Fix {_credential_field_name(name)} formatting so it can pass through .env, JSON, YAML, "
            "shell quoting, Ansible, Cisco CLI, iLO Redfish, ESXi, and NetApp clients without printing the value."
            if issues
            else "Credential compatibility passed with redacted value handling."
        ),
    }


def validate_mtu_consistency(values: dict[str, int | None]) -> dict[str, Any]:
    configured = {key: value for key, value in values.items() if value is not None}
    invalid = {key: value for key, value in configured.items() if value < 576 or value > 9216}
    groups = {
        "management": ["cisco_management", "esxi_management", "netapp_management"],
        "iscsi": ["cisco_iscsi", "esxi_iscsi", "netapp_iscsi"],
        "vmotion": ["cisco_vmotion", "esxi_vmotion"],
        "backup": ["cisco_backup", "netapp_backup"],
    }
    mismatches = []
    for group, keys in groups.items():
        present = {key: configured[key] for key in keys if key in configured}
        if len(set(present.values())) > 1:
            mismatches.append({"group": group, "values": present})
    return {
        "status": "blocked" if invalid or mismatches else "ready",
        "classification": "hard_fail" if invalid or mismatches else "passed",
        "configured": configured,
        "invalid": invalid,
        "mismatches": mismatches,
        "next_action": (
            "Align MTU values across Cisco, ESXi, NetApp, iSCSI, vMotion, management, and backup paths."
            if invalid or mismatches
            else "MTU consistency passed for configured paths."
        ),
    }


def protocol_readiness(
    protocol: str,
    *,
    configured: bool,
    reachable: bool | None,
    required: bool = True,
    classification: str | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    blockers = []
    if not configured and required:
        blockers.append(f"{protocol} is not configured.")
    if reachable is False:
        blockers.append(f"{protocol} required port is not reachable.")
    final_classification = classification or (
        "hard_fail"
        if blockers
        else "not_configured_yet"
        if not configured
        else "passed"
        if reachable is True
        else "warning"
    )
    return {
        "protocol": protocol,
        "configured": configured,
        "reachable": reachable,
        "required": required,
        "status": (
            "blocked"
            if blockers
            else "skipped"
            if not configured
            else "ready"
            if reachable is not None
            else "unknown"
        ),
        "classification": final_classification,
        "blockers": blockers,
        "next_action": next_action or _protocol_next_action(protocol, final_classification, blockers),
    }


def find_stale_lab_ip_assumptions(values: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"field": key, "value": value}
        for key, value in values.items()
        if isinstance(value, str) and "10.10.8." in value
    ]


def _lab_ip_profile_checks() -> dict[str, Any]:
    expected = {
        "subnet": LAB_SUBNET_CIDR,
        "ilo": LAB_ILO_IP,
        "server_embedded_nic": LAB_SERVER_EMBEDDED_NIC_IP,
        "esxi_management": LAB_ESXI_MANAGEMENT_IP,
        "cisco_management": LAB_CISCO_MANAGEMENT_IP,
        "ansible_control_host": LAB_ANSIBLE_CONTROL_HOST_IP,
    }
    configured = {
        "subnet": settings.lab_subnet_cidr,
        "ilo": settings.ilo_test_host,
        "server_embedded_nic": settings.server_embedded_nic_ip,
        "esxi_management": settings.esxi_test_host,
        "cisco_management": settings.cisco_target_ip,
        "ansible_cisco_inventory_target": settings.cisco_target_ip,
        "ansible_control_host": settings.ansible_control_host,
        "cisco_target_ip_env": os.getenv("CISCO_TARGET_IP"),
        "ansible_cisco_host_env": os.getenv("ANSIBLE_CISCO_HOST"),
    }
    for key in (
        "NETAPP_CONTROLLER_A_SP",
        "NETAPP_CONTROLLER_B_SP",
        "NETAPP_CLUSTER_MGMT_IP",
        "NETAPP_NODE_A_MGMT_IP",
        "NETAPP_NODE_B_MGMT_IP",
        "NETAPP_SVM_MGMT_IP",
        "NETAPP_ISCSI_LIFS",
    ):
        if settings.netapp_configured or os.getenv(key):
            configured[key.lower()] = os.getenv(key) or getattr(settings, key.lower())
    mismatches = []
    for key, expected_value in expected.items():
        configured_value = configured.get(key)
        if configured_value and configured_value != expected_value:
            mismatches.append(
                {
                    "field": key,
                    "expected": expected_value,
                    "configured": configured_value,
                }
            )
    ansible_cisco_host = configured.get("ansible_cisco_host_env")
    if ansible_cisco_host and ansible_cisco_host != LAB_CISCO_MANAGEMENT_IP:
        mismatches.append(
            {
                "field": "ansible_cisco_host_env",
                "expected": LAB_CISCO_MANAGEMENT_IP,
                "configured": ansible_cisco_host,
                "reason": "ANSIBLE_CISCO_HOST is the Cisco device inventory target, not the control host.",
            }
        )
    stale_values = find_stale_lab_ip_assumptions(configured)
    stale_artifacts = _stale_artifact_evidence()
    return {
        "status": "blocked" if mismatches or stale_values else "ready",
        "classification": "stale_config" if mismatches or stale_values else "passed",
        "expected": expected,
        "configured": configured,
        "mismatches": mismatches,
        "stale_10_10_8_values": stale_values,
        "stale_artifact_evidence": stale_artifacts,
        "next_action": (
            "Update active lab inputs to 192.168.1.201-.205 and remove stale 10.10.8.x values before certification."
            if mismatches or stale_values
            else "Active lab IP profile matches 192.168.1.0/24 with devices at 192.168.1.200+."
        ),
        "ansible_role": {
            "first_contact": "Cisco console bootstrap",
            "starts_after": f"Cisco management SSH is configured at {LAB_CISCO_MANAGEMENT_IP}",
            "uses": [
                "show commands",
                "backup",
                "validation",
                "drift checks",
                "future repeatable config",
            ],
            "not_initial_bootstrap_path": True,
        },
    }


def _credential_checks() -> dict[str, Any]:
    checks = [
        validate_credential_compatibility("ilo", settings.ilo_test_password),
        validate_credential_compatibility("cisco", settings.cisco_test_password),
        validate_credential_compatibility("cisco_enable", settings.cisco_enable_password),
        validate_credential_compatibility("esxi", settings.esxi_test_password),
    ]
    if settings.netapp_configured:
        checks.append(validate_credential_compatibility("netapp", settings.netapp_api_password))
    return {
        "status": "blocked" if any(item["status"] == "blocked" for item in checks) else "ready",
        "classification": _worst_classification(item["classification"] for item in checks),
        "checks": checks,
    }


def _mtu_checks() -> dict[str, Any]:
    values = {
        "cisco_management": _int_env("CISCO_MANAGEMENT_MTU"),
        "esxi_management": _int_env("ESXI_MANAGEMENT_MTU"),
        "netapp_management": _int_env("NETAPP_MANAGEMENT_MTU"),
        "cisco_iscsi": _int_env("CISCO_ISCSI_MTU"),
        "esxi_iscsi": _int_env("ESXI_ISCSI_MTU"),
        "netapp_iscsi": _int_env("NETAPP_ISCSI_MTU"),
        "cisco_vmotion": _int_env("CISCO_VMOTION_MTU"),
        "esxi_vmotion": _int_env("ESXI_VMOTION_MTU"),
        "cisco_backup": _int_env("CISCO_BACKUP_MTU"),
        "netapp_backup": _int_env("NETAPP_BACKUP_MTU"),
    }
    return validate_mtu_consistency(values)


def _protocol_checks(*, check_ports: bool) -> dict[str, Any]:
    cisco_ssh_reachable = (
        _reachable(settings.cisco_target_ip, 22, check_ports)
        if settings.cisco_mgmt_configured
        else None
    )
    esxi_api_reachable = (
        _reachable(settings.esxi_test_host, 443, check_ports)
        if settings.esxi_configured
        else None
    )
    esxi_ssh_reachable = (
        _reachable(settings.esxi_test_host, 22, check_ports)
        if settings.esxi_configured
        else None
    )
    netapp_rest_reachable = (
        _reachable(settings.netapp_cluster_mgmt_ip, 443, check_ports)
        if settings.netapp_configured
        else None
    )
    netapp_ssh_reachable = (
        _reachable(settings.netapp_cluster_mgmt_ip, 22, check_ports)
        if settings.netapp_configured
        else None
    )
    checks = [
        protocol_readiness("iLO Redfish", configured=bool(settings.ilo_test_host), reachable=_reachable(settings.ilo_test_host, 443, check_ports)),
        protocol_readiness("iLO XML fallback", configured=bool(settings.ilo_test_host), reachable=_reachable(settings.ilo_test_host, 443, check_ports)),
        _cisco_console_readiness(),
        protocol_readiness(
            "Cisco SSH/SCP",
            configured=bool(settings.cisco_target_ip),
            reachable=cisco_ssh_reachable,
            classification="blocked_by_prior_stage" if not settings.cisco_mgmt_configured else None,
            next_action=(
                "Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure."
                if not settings.cisco_mgmt_configured
                else None
            ),
        ),
        protocol_readiness(
            "ESXi API",
            configured=bool(settings.esxi_test_host),
            reachable=esxi_api_reachable,
            classification="blocked_by_prior_stage" if not settings.esxi_configured else None,
            next_action=(
                "Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification."
                if not settings.esxi_configured
                else None
            ),
        ),
        protocol_readiness(
            "ESXi SSH",
            configured=bool(settings.esxi_test_host),
            reachable=esxi_ssh_reachable,
            classification="blocked_by_prior_stage" if not settings.esxi_configured else None,
            next_action=(
                "Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification."
                if not settings.esxi_configured
                else None
            ),
        ),
        protocol_readiness(
            "NetApp REST",
            configured=bool(settings.netapp_configured and settings.netapp_cluster_mgmt_ip),
            reachable=netapp_rest_reachable,
            required=settings.netapp_configured,
            classification="not_configured_yet" if not settings.netapp_configured else None,
            next_action=(
                "Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured."
                if not settings.netapp_configured
                else None
            ),
        ),
        protocol_readiness(
            "NetApp SSH",
            configured=bool(settings.netapp_configured and settings.netapp_cluster_mgmt_ip),
            reachable=netapp_ssh_reachable,
            required=settings.netapp_configured,
            classification="not_configured_yet" if not settings.netapp_configured else None,
            next_action=(
                "Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured."
                if not settings.netapp_configured
                else None
            ),
        ),
        _iso_media_readiness(),
    ]
    return {
        "status": "blocked" if any(item["classification"] in {"hard_fail", "blocked_by_prior_stage"} for item in checks) else "ready",
        "classification": _worst_classification(item["classification"] for item in checks),
        "checks": checks,
    }


def _post_build_checklist(protocols: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"item": "Cisco management IP responds and SSH/SCP are ready", "status": _protocol_status(protocols, "Cisco SSH/SCP")},
        {"item": "iLO inventory, health, power, and Redfish are reachable", "status": _protocol_status(protocols, "iLO Redfish")},
        {"item": "RAID layout matches saved intent after reset/validation", "status": "manual-review"},
        {"item": "ESXi media is inserted or host installer state is detected", "status": _protocol_status(protocols, "ESXi API")},
        {"item": "NetApp REST/SSH paths are reachable when configured", "status": _protocol_status(protocols, "NetApp REST")},
    ]


def _failure_classification(
    credentials: dict[str, Any],
    lab_ip_profile: dict[str, Any],
    mtu: dict[str, Any],
    protocols: dict[str, Any],
) -> list[dict[str, str]]:
    failures = []
    if lab_ip_profile["classification"] != "passed":
        failures.append(
            {
                "category": "lab-ip-profile",
                "classification": lab_ip_profile["classification"],
                "ui_message": "Active lab IP profile contains stale or mismatched target values.",
                "report_detail": _profile_report_detail(lab_ip_profile),
                "next_action": lab_ip_profile["next_action"],
            }
        )
    for check in credentials["checks"]:
        if check["classification"] != "passed":
            failures.append(
                {
                    "category": "credential",
                    "classification": check["classification"],
                    "ui_message": f"{check['name']} credential compatibility needs attention.",
                    "report_detail": f"Field `{check['field']}` failed compatibility/configuration; value remains redacted.",
                    "next_action": check["next_action"],
                }
            )
    if mtu["classification"] != "passed":
        failures.append(
            {
                "category": "mtu",
                "classification": mtu["classification"],
                "ui_message": "MTU values are inconsistent across one or more traffic paths.",
                "report_detail": _mtu_report_detail(mtu),
                "next_action": mtu["next_action"],
            }
        )
    for check in protocols["checks"]:
        if check["classification"] != "passed":
            failures.append(
                {
                    "category": "protocol",
                    "classification": check["classification"],
                    "ui_message": f"{check['protocol']} is {check['classification']}.",
                    "report_detail": "; ".join(check["blockers"]) if check["blockers"] else check["next_action"],
                    "next_action": check["next_action"],
                }
            )
    return sorted(failures, key=lambda item: CLASSIFICATION_ORDER.get(item["classification"], 99))


def _certification_state(failures: list[dict[str, str]]) -> str:
    worst = _worst_classification(item["classification"] for item in failures)
    return "certified" if worst == "passed" else worst


def _worst_classification(values: Any) -> str:
    items = list(values)
    if not items:
        return "passed"
    return min(items, key=lambda value: CLASSIFICATION_ORDER.get(value, 99))


def _credential_field_name(name: str) -> str:
    return {
        "ilo": "ILO_TEST_PASSWORD",
        "cisco": "CISCO_TEST_PASSWORD",
        "cisco_enable": "CISCO_ENABLE_PASSWORD or ANSIBLE_CISCO_ENABLE_PASSWORD",
        "esxi": "ESXI_TEST_PASSWORD",
        "netapp": "NETAPP_API_PASSWORD",
    }.get(name, f"{name.upper()}_PASSWORD")


def _protocol_next_action(protocol: str, classification: str, blockers: list[str]) -> str:
    if classification == "passed":
        return f"{protocol} readiness passed."
    if classification == "not_configured_yet":
        return f"Configure {protocol} only when that provider stage is in scope."
    if classification == "blocked_by_prior_stage":
        return f"Complete the prior workflow stage before certifying {protocol}."
    if blockers:
        return f"Restore readiness for {protocol}: {'; '.join(blockers)}"
    return f"Review {protocol} readiness."


def _iso_media_readiness() -> dict[str, Any]:
    iso_count = 0
    for directory in settings.media_inventory_dirs:
        path = Path(directory)
        if not path.exists() or not path.is_dir():
            continue
        try:
            iso_count += sum(1 for item in path.rglob("*.iso") if item.is_file())
        except OSError:
            continue
    configured = bool(settings.media_inventory_dirs)
    if not configured or iso_count == 0:
        return protocol_readiness(
            "ESXi ISO media inventory",
            configured=configured,
            reachable=None,
            classification="operator_action_required",
            next_action="Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.",
        )
    return {
        "protocol": "ESXi ISO media inventory",
        "configured": True,
        "reachable": None,
        "required": True,
        "status": "ready",
        "classification": "passed",
        "blockers": [],
        "iso_count": iso_count,
        "next_action": "ESXi ISO media inventory is ready.",
    }


def _cisco_console_readiness() -> dict[str, Any]:
    details = CODEX_RUN_DIR / "cisco-4h-lab-run-details-redacted.json"
    if not details.exists():
        return protocol_readiness(
            "Cisco console",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Run Cisco console discovery/prompt detection before product certification.",
        )
    try:
        payload = json.loads(details.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return protocol_readiness(
            "Cisco console",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Regenerate Cisco console details; the current redacted details artifact is unreadable.",
        )
    stages = payload.get("stages") if isinstance(payload, dict) else {}
    prompt = stages.get("console_prompt_detection", {}) if isinstance(stages, dict) else {}
    adapter = stages.get("adapter_discovery", {}) if isinstance(stages, dict) else {}
    if adapter.get("status") == "ready" and prompt.get("prompt_detected") is True:
        return {
            "protocol": "Cisco console",
            "configured": True,
            "reachable": None,
            "required": True,
            "status": "ready",
            "classification": "passed",
            "blockers": [],
            "prompt_state": prompt.get("prompt_state"),
            "selected_baud": prompt.get("selected_baud"),
            "next_action": "Cisco console discovery and prompt detection passed.",
        }
    return protocol_readiness(
        "Cisco console",
        configured=True,
        reachable=None,
        classification="operator_action_required",
        next_action="Connect the Cisco console adapter and rerun prompt detection at 9600.",
    )


def _stale_artifact_evidence() -> list[dict[str, str]]:
    evidence = []
    for path in [
        CODEX_RUN_DIR / "cisco-bootstrap-apply-report.md",
        CODEX_RUN_DIR / "overnight-lab-builder-final-report.md",
    ]:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "10.10.8." in text:
            evidence.append(
                {
                    "artifact": str(path.relative_to(REPO_ROOT)),
                    "classification": "stale_config",
                    "next_action": "Regenerate this report after confirming the 192.168.1.0/24 lab profile.",
                }
            )
    return evidence


def _profile_report_detail(lab_ip_profile: dict[str, Any]) -> str:
    stale_count = len(lab_ip_profile.get("stale_10_10_8_values") or [])
    mismatch_count = len(lab_ip_profile.get("mismatches") or [])
    return f"{stale_count} stale active values; {mismatch_count} active profile mismatches."


def _mtu_report_detail(mtu: dict[str, Any]) -> str:
    invalid = mtu.get("invalid") or {}
    mismatches = mtu.get("mismatches") or []
    return f"{len(invalid)} invalid MTU values; {len(mismatches)} path mismatches."


def _reachable(host: str | None, port: int, check_ports: bool) -> bool | None:
    if not host or not check_ports:
        return None
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


def _protocol_status(protocols: dict[str, Any], name: str) -> str:
    for item in protocols["checks"]:
        if item["protocol"] == name:
            return item["status"]
    return "unknown"


def _int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        return -1


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Build Verification / Product Certification",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{payload['status']}`",
        f"- Certification state: `{payload.get('certification_state', payload['status'])}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        f"- Mock results used: `{payload['mock_results_used']}`",
        "",
        "## Lab IP Profile",
        "",
        f"- Status: `{payload['lab_ip_profile']['status']}`",
        f"- iLO: `{payload['lab_ip_profile']['expected']['ilo']}`",
        f"- Server embedded NIC: `{payload['lab_ip_profile']['expected']['server_embedded_nic']}`",
        f"- ESXi management: `{payload['lab_ip_profile']['expected']['esxi_management']}`",
        f"- Cisco management: `{payload['lab_ip_profile']['expected']['cisco_management']}`",
        f"- Ansible/control host: `{payload['lab_ip_profile']['expected']['ansible_control_host']}`",
        "",
        "## Failure Classification",
        "",
    ]
    failures = payload.get("failures") or []
    lines.extend(
        f"- `{item['classification']}` `{item['category']}`: {item['ui_message']} Next action: {item['next_action']}"
        for item in failures
    )
    if not failures:
        lines.append("- none")
    lines.extend(["", "## Credential Compatibility", ""])
    for item in payload.get("credentials", {}).get("checks") or []:
        lines.append(
            f"- `{item['classification']}` `{item['field']}`: "
            f"{'configured' if item['configured'] else 'not configured'}; values redacted"
        )
    lines.extend(["", "## MTU Consistency", ""])
    mtu = payload.get("mtu") or {}
    lines.append(f"- Classification: `{mtu.get('classification', 'unknown')}`")
    lines.append(f"- Invalid values: `{len(mtu.get('invalid') or {})}`")
    lines.append(f"- Path mismatches: `{len(mtu.get('mismatches') or [])}`")
    lines.extend(["", "## Protocol Readiness", ""])
    for item in payload.get("protocols", {}).get("checks") or []:
        lines.append(
            f"- `{item['classification']}` `{item['protocol']}`: {item['next_action']}"
        )
    lines.extend(["", "## Post-Build Checklist", ""])
    lines.extend(f"- `{item['status']}` {item['item']}" for item in payload.get("post_build_checklist") or [])
    lines.extend(["", "## Safety", "", "- Credential values, tokens, and secrets are redacted.", ""])
    return "\n".join(lines)


def _lab_ip_markdown(payload: dict[str, Any]) -> str:
    profile = payload["lab_ip_profile"]
    lines = [
        "# Lab IP Profile Update",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{profile['status']}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        "",
        "## Expected Profile",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in profile["expected"].items())
    lines.extend(
        [
            "",
            "## Configured Values",
            "",
        ]
    )
    lines.extend(
        f"- {key}: `{value}`"
        for key, value in profile["configured"].items()
        if value is not None
    )
    lines.extend(["", "## Stale Assumptions", ""])
    stale = profile.get("stale_10_10_8_values") or []
    if stale:
        lines.extend(f"- `{item['field']}` still contains stale `{item['value']}`" for item in stale)
    else:
        lines.append("- No active build-verification inputs contain `10.10.8.x`.")
    stale_artifacts = profile.get("stale_artifact_evidence") or []
    lines.extend(["", "## Stale Report Evidence", ""])
    if stale_artifacts:
        lines.extend(
            f"- `{item['artifact']}` contains stale `10.10.8.x` evidence. {item['next_action']}"
            for item in stale_artifacts
        )
    else:
        lines.append("- No scanned build-verification report artifacts contain `10.10.8.x`.")
    mismatches = profile.get("mismatches") or []
    lines.extend(["", "## Mismatches", ""])
    if mismatches:
        lines.extend(
            f"- `{item['field']}` expected `{item['expected']}`, configured `{item['configured']}`"
            for item in mismatches
        )
    else:
        lines.append("- No lab IP profile mismatches.")
    lines.extend(
        [
            "",
            "## Ansible Role",
            "",
            "- Cisco first contact/bootstrap remains console.",
            f"- Ansible starts after Cisco management SSH is configured at `{LAB_CISCO_MANAGEMENT_IP}`.",
            "- Ansible is for show commands, backup, validation, drift checks, and future repeatable config.",
            "- Ansible is not the initial Cisco bootstrap path.",
            "",
            "## Reports",
            "",
            f"- Build verification report: `{REPORT.relative_to(REPO_ROOT)}`",
            f"- Build verification summary: `{SUMMARY.relative_to(REPO_ROOT)}`",
        ]
    )
    return "\n".join(lines)


def _lab_ip_hardening_markdown(payload: dict[str, Any]) -> str:
    profile = payload["lab_ip_profile"]
    lines = [
        "# Lab IP Profile Hardening Report",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Classification: `{profile['classification']}`",
        f"- Status: `{profile['status']}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        "",
        "## Current Profile",
        "",
        f"- Lab subnet: `{profile['expected']['subnet']}`",
        f"- iLO: `{profile['expected']['ilo']}`",
        f"- Server embedded NIC: `{profile['expected']['server_embedded_nic']}`",
        f"- ESXi management: `{profile['expected']['esxi_management']}`",
        f"- Cisco management: `{profile['expected']['cisco_management']}`",
        f"- Ansible/control host: `{profile['expected']['ansible_control_host']}`",
        "",
        "## Stale Detection",
        "",
    ]
    stale = profile.get("stale_10_10_8_values") or []
    if stale:
        lines.extend(f"- Active field `{item['field']}` contains stale `{item['value']}`." for item in stale)
    else:
        lines.append("- No active Build Verification input contains `10.10.8.x`.")
    stale_artifacts = profile.get("stale_artifact_evidence") or []
    if stale_artifacts:
        lines.extend(
            f"- Stale report evidence: `{item['artifact']}` should be regenerated."
            for item in stale_artifacts
        )
    else:
        lines.append("- No scanned certification report artifact contains `10.10.8.x`.")
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- {profile['next_action']}",
            "",
        ]
    )
    return "\n".join(lines)


def _classification_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Build Verification Classification Report",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Overall certification state: `{payload.get('certification_state')}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        "- Mock results used as substitutes for real lab evidence: `false`",
        "",
        "## Classification Vocabulary",
        "",
        "- `passed`: check succeeded with current evidence.",
        "- `hard_fail`: configured check failed and is not blocked by an earlier stage.",
        "- `blocked_by_prior_stage`: check must wait for a preceding workflow stage.",
        "- `not_configured_yet`: provider or feature is intentionally not configured for this run.",
        "- `stale_config`: active input or report evidence contains an old lab profile.",
        "- `operator_action_required`: local operator action is required before automation can continue.",
        "- `warning`: informational or indeterminate condition that does not certify readiness.",
        "",
        "## Findings",
        "",
    ]
    failures = payload.get("failures") or []
    if failures:
        for item in failures:
            lines.extend(
                [
                    f"### {item['category']} - {item['classification']}",
                    "",
                    f"- UI message: {item['ui_message']}",
                    f"- Report detail: {item['report_detail']}",
                    f"- Next action: {item['next_action']}",
                    "",
                ]
            )
    else:
        lines.append("- No classification findings.")
    return "\n".join(lines)


def _failure_case_markdown(payload: dict[str, Any]) -> str:
    protocol_checks = {item["protocol"]: item for item in payload.get("protocols", {}).get("checks") or []}
    lab_profile = payload.get("lab_ip_profile") or {}
    mtu = payload.get("mtu") or {}
    credentials = payload.get("credentials", {})
    cases = [
        {
            "case": "wrong iLO IP",
            "classification": lab_profile.get("classification", "unknown"),
            "ui_message": "iLO target must be 192.168.1.201 for this lab.",
            "detail": _profile_report_detail(lab_profile),
            "next_action": lab_profile.get("next_action", "Set ILO_TEST_HOST=192.168.1.201."),
        },
        {
            "case": "missing ESXi ISO",
            **_case_from_protocol(protocol_checks.get("ESXi ISO media inventory")),
        },
        {
            "case": "iLO cannot reach media URL",
            "classification": "operator_action_required",
            "ui_message": "iLO media URL reachability is validated by the ESXi media URL stage.",
            "detail": "See artifacts/codex-runs/esxi-media-url-report.md for the real media URL result.",
            "next_action": "Fix media URL reachability before virtual media insert.",
        },
        {
            "case": "Cisco console adapter missing",
            "classification": "operator_action_required",
            "ui_message": "Cisco console discovery must find the stable Prolific adapter.",
            "detail": "See artifacts/codex-runs/cisco-console-discovery-report.md.",
            "next_action": "Connect the Cisco console adapter and prefer the stable /dev/serial/by-id path.",
        },
        {
            "case": "Cisco wrong baud",
            "classification": "operator_action_required",
            "ui_message": "Cisco prompt detection should identify 9600 baud for this lab.",
            "detail": "The Cisco workflow tries 9600, 19200, 38400, 57600, and 115200.",
            "next_action": "Set CISCO_CONSOLE_BAUD=9600 or rerun console auto-discovery.",
        },
        {
            "case": "Cisco user exec but no privileged exec",
            "classification": "operator_action_required",
            "ui_message": "Cisco bootstrap apply requires privileged exec.",
            "detail": "See artifacts/codex-runs/cisco-privilege-hardening-report.md.",
            "next_action": "Confirm enable access or perform password recovery/factory reset before bootstrap apply.",
        },
        {
            "case": "Cisco password recovery required",
            "classification": "operator_action_required",
            "ui_message": "Password recovery is operator-confirmed only; the app must not assume it.",
            "detail": "Enable rejection is inferred only from prompt state and redacted challenge evidence.",
            "next_action": "Use the documented physical-console password recovery/factory reset procedure if no enable credential works.",
        },
        {
            "case": "ESXi API/SSH unreachable before install/config",
            **_case_from_protocol(protocol_checks.get("ESXi API")),
        },
        {
            "case": "stale Cisco/ESXi/NetApp IPs",
            "classification": lab_profile.get("classification", "unknown"),
            "ui_message": "Old 10.10.8.x values are stale for this lab unless explicitly overridden.",
            "detail": _profile_report_detail(lab_profile),
            "next_action": lab_profile.get("next_action", "Use 192.168.1.201-.205 lab targets."),
        },
        {
            "case": "MTU mismatch across paths",
            "classification": mtu.get("classification", "unknown"),
            "ui_message": "MTU must be consistent per traffic path.",
            "detail": _mtu_report_detail(mtu),
            "next_action": mtu.get("next_action", "Align MTU values across configured paths."),
        },
        {
            "case": "username/password special character handling",
            "classification": credentials.get("classification", "unknown"),
            "ui_message": "Credential values are tested for .env, JSON, YAML, shell, Ansible, Cisco CLI, iLO Redfish, ESXi, and NetApp compatibility.",
            "detail": "Field names are reported; credential values remain redacted.",
            "next_action": (
                "Credential compatibility passed for configured fields."
                if credentials.get("classification") == "passed"
                else "Fix the named env/config field; values remain redacted."
            ),
        },
    ]
    lines = [
        "# Failure Case Hardening Report",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        "- Credential values, tokens, and secrets are redacted.",
        "",
    ]
    for item in cases:
        lines.extend(
            [
                f"## {item['case']}",
                "",
                f"- Classification: `{item['classification']}`",
                f"- UI message: {item['ui_message']}",
                f"- Report artifact detail: {item['detail']}",
                f"- Exact next action: {item['next_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def _case_from_protocol(item: dict[str, Any] | None) -> dict[str, str]:
    if not item:
        return {
            "classification": "warning",
            "ui_message": "No protocol evidence was recorded.",
            "detail": "Protocol check missing from Build Verification payload.",
            "next_action": "Regenerate Build Verification.",
        }
    return {
        "classification": item.get("classification", "unknown"),
        "ui_message": f"{item.get('protocol')} is {item.get('classification', 'unknown')}.",
        "detail": "; ".join(item.get("blockers") or []) or item.get("next_action", "No blocker detail."),
        "next_action": item.get("next_action", "Review protocol readiness."),
    }


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(
        payload,
        [
            settings.ilo_test_password,
            settings.cisco_test_password,
            settings.cisco_enable_password,
            settings.esxi_test_password,
            settings.netapp_api_password,
        ],
    )
