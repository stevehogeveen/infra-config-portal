from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
from importlib import util as importlib_util
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import settings
from app.providers.probe_cache import get_probe_result
from app.providers.redaction import redact_sensitive
from app.services.hpe_raid import REPO_ROOT
from app.services.lab_profiles import active_lab_profile_context
from app.services.lab_topology import configured_runtime_values
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.list_utils import unique_preserving_order
from app.services.netapp_state import get_netapp_runtime_state, read_netapp_live_state
from app.services.path_utils import (
    is_directory as _is_directory,
    is_file as _is_file,
    path_exists as _path_exists,
    repo_relative_path,
    rglob_paths,
    safe_read_text,
)
from app.services.status_source import attach_status_source, status_source_metadata

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
REPORT = CODEX_RUN_DIR / "build-verification-report.md"
CURRENT_STATE_REPORT = CODEX_RUN_DIR / "build-verification-current-state-report.md"
EVIDENCE_REPORT = CODEX_RUN_DIR / "build-verification-evidence-report.md"
SUMMARY = CODEX_RUN_DIR / "build-verification-summary-redacted.json"
LAB_IP_REPORT = CODEX_RUN_DIR / "lab-ip-profile-update-report.md"
LAB_IP_HARDENING_REPORT = CODEX_RUN_DIR / "lab-ip-profile-hardening-report.md"
CLASSIFICATION_REPORT = CODEX_RUN_DIR / "build-verification-classification-report.md"
FAILURE_CASE_REPORT = CODEX_RUN_DIR / "failure-case-hardening-report.md"
TOOLCHAIN_AVAILABILITY_REPORT = CODEX_RUN_DIR / "toolchain-availability-report.md"
CLASSIFICATION_ORDER = {
    "hard_fail": 0,
    "stale_config": 1,
    "operator_action_required": 2,
    "blocked_by_prior_stage": 3,
    "not_configured_yet": 4,
    "warning": 5,
    "passed": 6,
    "not_in_scope": 7,
}


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def build_lab_build_verification(*, check_ports: bool = True) -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = datetime.now(UTC).isoformat()
    profile_context = active_lab_profile_context()
    netapp_live_state = _netapp_state_for_verification(
        check_ports=check_ports,
        profile_context=profile_context,
    )
    credentials = _credential_checks(netapp_live_state, profile_context=profile_context)
    lab_ip_profile = _lab_ip_profile_checks(profile_context=profile_context)
    mtu = _mtu_checks(profile_context=profile_context)
    protocols = _protocol_checks(
        check_ports=check_ports,
        netapp_live_state=netapp_live_state,
        profile_context=profile_context,
    )
    toolchain = build_toolchain_availability()
    licenses = _license_checks()
    checklist = _post_build_checklist(protocols)
    failures = _failure_classification(credentials, lab_ip_profile, mtu, protocols)
    runtime_guard = _runtime_mode_guard()
    if runtime_guard:
        failures = [runtime_guard, *failures]
    blockers = unique_preserving_order(
        _blocker_text_with_source(item)
        for item in failures
        if item["classification"]
        in {"hard_fail", "stale_config", "operator_action_required", "blocked_by_prior_stage"}
    )
    warnings = unique_preserving_order(
        _blocker_text_with_source(item)
        for item in failures
        if item["classification"] == "warning"
    )
    source_type = _build_verification_source_type(check_ports=check_ports)
    certification_state = (
        "test_fixture"
        if source_type == "test_fixture"
        else _certification_state(failures)
    )
    payload = {
        "provider_id": "build-verification",
        "checked_at": checked_at,
        "status": "blocked" if blockers else "warning" if warnings else "completed",
        "certification_state": certification_state,
        "message": "Build Verification / Product Certification completed with redacted findings.",
        "provider_mode": settings.provider_mode,
        "operator_runtime_mode": "dev_test" if settings.provider_mode == "mock" else "real_lab",
        "dev_test_banner": (
            "Build Verification is running in test/mock mode. It cannot certify real lab results."
            if settings.provider_mode == "mock"
            else None
        ),
        "lab_ip_profile": lab_ip_profile,
        "active_profile_context": profile_context,
        "credentials": credentials,
        "licenses": licenses,
        "mtu": mtu,
        "protocols": protocols,
        "netapp_live_state": netapp_live_state,
        "toolchain": toolchain,
        "post_build_checklist": checklist,
        "failures": failures,
        "blockers": blockers,
        "warnings": warnings,
        "artifacts": {
            "report": _rel(REPORT),
            "current_state_report": _rel(CURRENT_STATE_REPORT),
            "evidence_report": _rel(EVIDENCE_REPORT),
            "summary_json": _rel(SUMMARY),
            "lab_ip_profile_report": _rel(LAB_IP_REPORT),
            "lab_ip_profile_hardening_report": _rel(LAB_IP_HARDENING_REPORT),
            "classification_report": _rel(CLASSIFICATION_REPORT),
            "failure_case_report": _rel(FAILURE_CASE_REPORT),
            "toolchain_availability_report": _rel(TOOLCHAIN_AVAILABILITY_REPORT),
            "netapp_live_state_report": "artifacts/codex-runs/netapp-live-state-report.md",
            "netapp_state_automanagement_report": "artifacts/codex-runs/netapp-state-automanagement-report.md",
        },
        "next_safe_action": blockers[0] if blockers else "Review warnings, then continue product certification.",
    }
    payload = attach_status_source(
        payload,
        source_type=source_type,
        checked_at=checked_at,
        recheck_command="make provider-lab-build-verification-live",
        evidence_artifacts=[
            _rel(REPORT),
            _rel(CURRENT_STATE_REPORT),
            _rel(EVIDENCE_REPORT),
            _rel(SUMMARY),
        ],
        is_operator_visible=source_type != "test_fixture",
    )
    sanitized = _sanitize(payload)
    write_text_value(REPORT, _markdown(sanitized))
    write_text_value(CURRENT_STATE_REPORT, _current_state_markdown(sanitized))
    write_text_value(EVIDENCE_REPORT, _evidence_markdown(sanitized))
    write_text_value(LAB_IP_REPORT, _lab_ip_markdown(sanitized))
    write_text_value(LAB_IP_HARDENING_REPORT, _lab_ip_hardening_markdown(sanitized))
    write_text_value(CLASSIFICATION_REPORT, _classification_markdown(sanitized))
    write_text_value(FAILURE_CASE_REPORT, _failure_case_markdown(sanitized))
    write_json_object(SUMMARY, sanitized)
    return sanitized


def build_toolchain_availability() -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    tools = [
        _python_tool(
            "pyserial",
            "serial",
            "Cisco local serial console first contact.",
            required=True,
        ),
        _python_tool(
            "netmiko",
            "netmiko",
            "Cisco SSH command execution after console bootstrap enables management SSH.",
            required=False,
        ),
        _cli_tool(
            "ansible",
            "ansible",
            "Cisco, NetApp, and future workflow orchestration after safe inventory is available.",
            required=False,
        ),
        _ansible_collection_tool(
            "cisco.ios collection",
            "cisco.ios",
            "Cisco IOS managed-state modules after SSH is enabled.",
            required=False,
        ),
        _cli_tool(
            "govc",
            "govc",
            "ESXi/vSphere post-install validation and deployment operations.",
            required=False,
        ),
        _cli_tool(
            "ilorest",
            "ilorest",
            "HPE iLO inventory, settings, firmware, and Redfish-backed operations.",
            required=False,
        ),
        _python_tool(
            "netapp-ontap",
            "netapp_ontap",
            "NetApp ONTAP REST client for managed-state setup and upgrade validation.",
            required=False,
        ),
        _optional_python_family_tool(
            "pyATS/Genie",
            ("pyats", "genie"),
            "Cisco parsing, learning, and validation when installed.",
        ),
    ]
    required_missing = [tool["name"] for tool in tools if tool["required"] and not tool["available"]]
    optional_missing = [tool["name"] for tool in tools if not tool["required"] and not tool["available"]]
    payload = {
        "provider_id": "toolchain-readiness",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "blocked" if required_missing else "warning" if optional_missing else "ready",
        "provider_mode": settings.provider_mode,
        "tools": tools,
        "required_missing": required_missing,
        "optional_missing": optional_missing,
        "managed_state": _managed_state_plan(),
        "firmware_strategy": _firmware_toolchain_strategy(),
        "artifacts": {
            "report": _rel(TOOLCHAIN_AVAILABILITY_REPORT),
        },
        "next_safe_action": (
            "Install missing required local packages before console-first lab workflows."
            if required_missing
            else "Use available tools only through staged readiness, preview, approval, and audit gates."
        ),
    }
    payload = attach_status_source(
        payload,
        source_type="live_probe",
        checked_at=payload["checked_at"],
        recheck_command="make provider-lab-toolchain-check",
        evidence_artifacts=[_rel(TOOLCHAIN_AVAILABILITY_REPORT)],
    )
    sanitized = _sanitize(payload)
    write_text_value(TOOLCHAIN_AVAILABILITY_REPORT, _toolchain_markdown(sanitized))
    return sanitized


def get_lab_build_verification() -> dict[str, Any]:
    payload = read_json_object(SUMMARY)
    if payload:
        if settings.provider_mode != "mock" and _cached_summary_is_test_fixture(payload):
            return _not_checked_build_verification(
                message=(
                    "Current live Build Verification has not run in this runtime. "
                    "The cached test-fixture summary is historical evidence only."
                ),
                evidence_artifacts=[
                    _rel(REPORT),
                    _rel(CURRENT_STATE_REPORT),
                    _rel(EVIDENCE_REPORT),
                    _rel(SUMMARY),
                ],
            )
        if "source_type" not in payload:
            source_type = "test_fixture" if payload.get("provider_mode") == "mock" else "live_cached"
            payload = attach_status_source(
                payload,
                source_type=source_type,
                checked_at=payload.get("checked_at"),
                recheck_command="make provider-lab-build-verification-live",
                evidence_artifacts=[
                    _rel(REPORT),
                    _rel(SUMMARY),
                ],
                is_operator_visible=source_type != "test_fixture",
            )
            if source_type == "test_fixture":
                payload["certification_state"] = "test_fixture"
                payload["dev_test_banner"] = (
                    "Cached Build Verification summary came from test/mock mode and cannot certify real lab results."
                )
        return payload
    return _not_checked_build_verification()


def _cached_summary_is_test_fixture(payload: dict[str, Any]) -> bool:
    return payload.get("source_type") == "test_fixture" or payload.get("provider_mode") == "mock"


def _not_checked_build_verification(
    *,
    message: str = "Build verification has not been generated yet.",
    evidence_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    artifacts = {
        "report": _rel(REPORT),
        "current_state_report": _rel(CURRENT_STATE_REPORT),
        "evidence_report": _rel(EVIDENCE_REPORT),
        "summary_json": _rel(SUMMARY),
    }
    return attach_status_source(
        {
            "provider_id": "build-verification",
            "checked_at": None,
            "status": "not_run",
            "certification_state": "not_checked",
            "message": message,
            "warnings": [],
            "blockers": [],
            "artifacts": artifacts,
            "next_safe_action": "Run `make provider-lab-build-verification-live`.",
        },
        source_type="not_checked",
        checked_at=None,
        recheck_command="make provider-lab-build-verification-live",
        evidence_artifacts=evidence_artifacts or list(artifacts.values()),
    )

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
    if final_classification == "not_in_scope":
        status_value = "not_in_scope"
    else:
        status_value = (
            "blocked"
            if blockers
            else "skipped"
            if not configured
            else "ready"
            if reachable is not None
            else "unknown"
        )
    status = {
        "protocol": protocol,
        "configured": configured,
        "reachable": reachable,
        "required": required,
        "status": status_value,
        "classification": final_classification,
        "blockers": blockers,
        "next_action": next_action or _protocol_next_action(protocol, final_classification, blockers),
    }
    source_type = "live_probe" if reachable is not None else "not_checked"
    return {
        **status,
        **status_source_metadata(
            source_type=source_type,
            checked_at=datetime.now(UTC).isoformat() if source_type == "live_probe" else None,
            recheck_command="make provider-lab-live-status",
            evidence_artifacts=[],
        ),
    }


def _not_in_scope_protocol(protocol: str, reason: str) -> dict[str, Any]:
    return protocol_readiness(
        protocol,
        configured=False,
        reachable=None,
        required=False,
        classification="not_in_scope",
        next_action=reason,
    )


def find_stale_lab_ip_assumptions(values: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"field": key, "value": value}
        for key, value in values.items()
        if isinstance(value, str) and "10.10.8." in value
    ]


def _lab_ip_profile_checks(*, profile_context: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    active_lab_profile = profile_context["active_profile"]
    active_plan = dict(profile_context.get("resolved_address_plan") or {})
    features = profile_context.get("enabled_features") or {}
    netapp_enabled = bool(features.get("netapp_enabled"))
    expected_netapp_iscsi_lifs = (
        ",".join(active_plan.get("netapp_iscsi_lifs") or [])
        if netapp_enabled
        else "not_in_scope"
    )
    expected_netapp_nfs_lifs = (
        ",".join(active_plan.get("netapp_nfs_lifs") or [])
        if netapp_enabled
        else "not_in_scope"
    )
    expected = {
        "subnet": active_plan.get("subnet"),
        "ilo": active_plan.get("ilo"),
        "server_embedded_nic": active_plan.get("server_embedded_nic"),
        "esxi_management": active_plan.get("esxi_management"),
        "cisco_management": active_plan.get("cisco_management"),
        "ansible_control_host": active_plan.get("ansible_control_host"),
        "netapp_controller_a_sp": active_plan.get("netapp_controller_a_sp") if netapp_enabled else "not_in_scope",
        "netapp_controller_b_sp": active_plan.get("netapp_controller_b_sp") if netapp_enabled else "not_in_scope",
        "netapp_cluster_mgmt": active_plan.get("netapp_cluster_mgmt") if netapp_enabled else "not_in_scope",
        "netapp_node_a_mgmt": active_plan.get("netapp_node_a_mgmt") if netapp_enabled else "not_in_scope",
        "netapp_node_b_mgmt": active_plan.get("netapp_node_b_mgmt") if netapp_enabled else "not_in_scope",
        "netapp_svm_mgmt": active_plan.get("netapp_svm_mgmt") if netapp_enabled else "not_in_scope",
        "netapp_nfs_lifs": expected_netapp_nfs_lifs,
        "netapp_iscsi_lifs": expected_netapp_iscsi_lifs,
    }
    configured = configured_runtime_values()
    configured.update(
        {
            "runtime_subnet_default": settings.lab_subnet_cidr,
            "runtime_provider_mode": settings.provider_mode,
        }
    )
    raw_env = {
        "cisco_target_ip_env": os.getenv("CISCO_TARGET_IP"),
        "ansible_cisco_host_env": os.getenv("ANSIBLE_CISCO_HOST"),
        "netapp_controller_a_sp_env": os.getenv("NETAPP_CONTROLLER_A_SP"),
        "netapp_controller_b_sp_env": os.getenv("NETAPP_CONTROLLER_B_SP"),
        "netapp_cluster_mgmt_ip_env": os.getenv("NETAPP_CLUSTER_MGMT_IP"),
        "netapp_node_a_mgmt_ip_env": os.getenv("NETAPP_NODE_A_MGMT_IP"),
        "netapp_node_b_mgmt_ip_env": os.getenv("NETAPP_NODE_B_MGMT_IP"),
        "netapp_svm_mgmt_ip_env": os.getenv("NETAPP_SVM_MGMT_IP"),
        "netapp_nfs_lifs_env": os.getenv("NETAPP_NFS_LIFS"),
        "netapp_iscsi_lifs_env": os.getenv("NETAPP_ISCSI_LIFS"),
    }
    configured.update(raw_env)
    mismatches = [
        {
            "field": item.get("field"),
            "expected": item.get("expected_value"),
            "configured": item.get("current_value"),
            "env_field": item.get("env_field"),
            "recommended_action": item.get("recommended_action"),
        }
        for item in profile_context.get("mismatch_warnings") or []
    ]
    stale_values = find_stale_lab_ip_assumptions(configured)
    stale_artifacts = _stale_artifact_evidence()
    selected_profile_name = active_lab_profile.get("name") or "Runtime environment"
    return {
        "status": "blocked" if mismatches or stale_values else "ready",
        "classification": "stale_config" if mismatches or stale_values else "passed",
        "active_lab_profile": {
            "id": active_lab_profile.get("id"),
            "name": active_lab_profile.get("name") or selected_profile_name,
            "source": active_lab_profile.get("source"),
            "version": active_lab_profile.get("version"),
            "topology": profile_context.get("topology"),
            "selected_for_portal": True,
            "provider_env_overrides_required": bool(mismatches),
            "ignored_for_current_runtime": False,
        },
        "effective_profile": {
            "name": selected_profile_name,
            "source": active_lab_profile.get("source"),
            "reason": "Active profile selected for current checks.",
        },
        "features": features,
        "not_in_scope_stages": list(profile_context.get("not_in_scope_stages") or []),
        "expected": expected,
        "configured": configured,
        "mismatches": mismatches,
        "stale_10_10_8_values": stale_values,
        "stale_artifact_evidence": stale_artifacts,
        "next_action": (
            f"Update provider environment inputs to match `{selected_profile_name}` or remove out-of-scope overrides before certification."
            if mismatches or stale_values
            else f"Active lab IP profile matches `{selected_profile_name}`."
        ),
        "ansible_role": {
            "first_contact": "Cisco console bootstrap",
            "starts_after": f"Cisco management SSH is configured at {expected['cisco_management']}",
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


def _netapp_state_for_verification(
    *,
    check_ports: bool,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled"):
        return {
            "provider_id": "netapp-ontap",
            "device_role": "storage-controller",
            "status": "not_in_scope",
            "configured": False,
            "configured_state": "not_in_scope",
            "source": "active_lab_profile",
            "source_type": "not_checked",
            "freshness": "not_checked",
            "manual_env_flag_required": False,
            "console": {},
            "management": {},
            "api": {},
            "storage": {},
            "blockers": [],
            "next_safe_action": "NetApp is disabled by the active lab profile.",
        }
    try:
        cached = get_netapp_runtime_state()
        if (
            not settings.netapp_configured
            and cached.get("configured_state") in {"not_detected", "console_detected", "login_required", "setup_wizard", "ontap_detected"}
        ):
            return cached
        if check_ports:
            return read_netapp_live_state(check_ports=True, write_report=True)
        return cached
    except Exception as exc:  # pragma: no cover - defensive around local runtime DB/network failures
        return {
            "provider_id": "netapp-ontap",
            "device_role": "storage-controller",
            "status": "blocked",
            "configured": False,
            "configured_state": "blocked",
            "source": "live_state_error",
            "manual_env_flag_required": False,
            "legacy_env": {
                "netapp_configured_env": settings.netapp_configured,
                "netapp_configured_env_role": "legacy_override_or_desired_flag",
                "manual_state_tracking_required": False,
            },
            "console": {},
            "management": {},
            "api": {},
            "storage": {},
            "blockers": [f"NetApp live state service failed with {exc.__class__.__name__}."],
            "next_safe_action": "Fix NetApp runtime-state validation, then rerun Build Verification.",
        }


def _credential_checks(
    netapp_live_state: dict[str, Any],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    checks = [
        validate_credential_compatibility("ilo", settings.ilo_test_password),
        validate_credential_compatibility("cisco", settings.cisco_test_password),
        validate_credential_compatibility("cisco_enable", settings.cisco_enable_password),
        validate_credential_compatibility("esxi", settings.esxi_test_password),
    ]
    if features.get("netapp_enabled") and (settings.netapp_configured or netapp_live_state.get("configured")):
        checks.append(validate_credential_compatibility("netapp", settings.netapp_api_password))
    return {
        "status": "blocked" if any(item["status"] == "blocked" for item in checks) else "ready",
        "classification": _worst_classification(item["classification"] for item in checks),
        "checks": checks,
    }


def _license_checks() -> dict[str, Any]:
    netapp_count = _netapp_license_count()
    checks = [
        _license_item("ESXi", "ESXI_LICENSE_KEY", bool(settings.esxi_license_key), 1 if settings.esxi_license_key else 0),
        _license_item("vCenter", "VCENTER_LICENSE_KEY", bool(settings.vcenter_license_key), 1 if settings.vcenter_license_key else 0),
        _license_item("NetApp ONTAP", "NETAPP_LICENSE_KEYS_FILE or NETAPP_LICENSE_KEYS", netapp_count > 0, netapp_count),
    ]
    return {
        "status": "ready" if all(item["configured"] for item in checks) else "warning",
        "classification": "passed" if all(item["configured"] for item in checks) else "warning",
        "checks": checks,
        "warnings": [
            f"{item['product']} license material is not configured."
            for item in checks
            if not item["configured"]
        ],
    }


def _license_item(product: str, field: str, configured: bool, count: int) -> dict[str, Any]:
    return {
        "product": product,
        "field": field,
        "configured": configured,
        "license_count": count,
        "value_redacted": True,
        "classification": "passed" if configured else "warning",
        "next_action": (
            f"{product} license material is present; apply only through a guarded vendor workflow."
            if configured
            else f"Set {field} in an ignored local env or secret file before license apply."
        ),
        **status_source_metadata(
            source_type="live_cached",
            checked_at=datetime.now(UTC).isoformat(),
            recheck_command="make provider-lab-build-verification-live",
        ),
    }


def _netapp_license_count() -> int:
    values = list(settings.netapp_license_keys)
    path = Path(settings.netapp_license_keys_file) if settings.netapp_license_keys_file else None
    if path and not path.is_absolute():
        path = REPO_ROOT / path
    if path and _is_file(path):
        for line in safe_read_text(path).splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            if cleaned.lower().startswith("license add "):
                cleaned = cleaned.split(None, 2)[2].strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return len(values)


def _mtu_checks(*, profile_context: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    netapp_enabled = bool(features.get("netapp_enabled"))
    values = {
        "cisco_management": _int_env("CISCO_MANAGEMENT_MTU"),
        "esxi_management": _int_env("ESXI_MANAGEMENT_MTU"),
        "cisco_iscsi": _int_env("CISCO_ISCSI_MTU"),
        "esxi_iscsi": _int_env("ESXI_ISCSI_MTU"),
        "cisco_vmotion": _int_env("CISCO_VMOTION_MTU"),
        "esxi_vmotion": _int_env("ESXI_VMOTION_MTU"),
        "cisco_backup": _int_env("CISCO_BACKUP_MTU"),
    }
    if netapp_enabled:
        values.update(
            {
                "netapp_management": _int_env("NETAPP_MANAGEMENT_MTU"),
                "netapp_iscsi": _int_env("NETAPP_ISCSI_MTU"),
                "netapp_backup": _int_env("NETAPP_BACKUP_MTU"),
            }
        )
    return validate_mtu_consistency(values)


def _protocol_checks(
    *,
    check_ports: bool,
    netapp_live_state: dict[str, Any],
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    plan = profile_context.get("resolved_address_plan") or {}
    features = profile_context.get("enabled_features") or {}
    ilo_host = plan.get("ilo") or settings.ilo_test_host
    cisco_host = plan.get("cisco_management") or settings.cisco_target_ip
    esxi_host = plan.get("esxi_management") or settings.esxi_test_host
    cisco_ssh_reachable = (
        _reachable(cisco_host, 22, check_ports)
        if settings.cisco_mgmt_configured
        else None
    )
    esxi_api_reachable = (
        _reachable(esxi_host, 443, check_ports)
        if settings.esxi_configured
        else None
    )
    esxi_ssh_reachable = (
        _reachable(esxi_host, 22, check_ports)
        if settings.esxi_configured
        else None
    )
    checks = [
        protocol_readiness("iLO Redfish", configured=bool(ilo_host), reachable=_reachable(ilo_host, 443, check_ports)),
        protocol_readiness("iLO XML fallback", configured=bool(ilo_host), reachable=_reachable(ilo_host, 443, check_ports)),
        _cisco_console_readiness(),
        protocol_readiness(
            "Cisco SSH/SCP",
            configured=bool(cisco_host),
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
            configured=bool(esxi_host),
            reachable=esxi_api_reachable,
            classification="blocked_by_prior_stage" if not settings.esxi_configured else None,
            next_action=(
                f"Install/configure ESXi management at {esxi_host or 'the active profile ESXi IP'}, then set ESXI_CONFIGURED=true before API certification."
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
        _iso_media_readiness(),
    ]
    if features.get("netapp_enabled"):
        checks.extend(
            [
                _netapp_protocol_readiness("NetApp REST", netapp_live_state, "rest_443_reachable"),
                _netapp_protocol_readiness("NetApp SSH", netapp_live_state, "ssh_22_reachable"),
                _netapp_console_readiness(profile_context=profile_context),
            ]
        )
    else:
        checks.extend(
            [
                _not_in_scope_protocol("NetApp REST", "NetApp is disabled by the active lab profile."),
                _not_in_scope_protocol("NetApp SSH", "NetApp is disabled by the active lab profile."),
                _not_in_scope_protocol("NetApp console", "NetApp is disabled by the active lab profile."),
            ]
        )
    if features.get("netapp_enabled") and features.get("vcenter_enabled"):
        checks.append(_netapp_nfs_vcenter_readiness(profile_context=profile_context))
    else:
        checks.append(
            _not_in_scope_protocol(
                "NetApp NFS/vCenter",
                "NetApp or vCenter is disabled by the active lab profile.",
            )
        )
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
        {"item": "NetApp console discovery/read-state evidence exists", "status": _protocol_status(protocols, "NetApp console")},
        {"item": "NetApp NFS/vCenter readiness has been reviewed", "status": _protocol_status(protocols, "NetApp NFS/vCenter")},
    ]


def _failure_classification(
    credentials: dict[str, Any],
    lab_ip_profile: dict[str, Any],
    mtu: dict[str, Any],
    protocols: dict[str, Any],
) -> list[dict[str, Any]]:
    failures = []
    if lab_ip_profile["classification"] != "passed":
        failures.append(
            {
                "category": "lab-ip-profile",
                "classification": lab_ip_profile["classification"],
                "ui_message": "Active lab IP profile contains stale or mismatched target values.",
                "report_detail": _profile_report_detail(lab_ip_profile),
                "next_action": lab_ip_profile["next_action"],
                **status_source_metadata(
                    source_type="live_cached",
                    checked_at=datetime.now(UTC).isoformat(),
                    recheck_command="make provider-lab-build-verification-live",
                    evidence_artifacts=[_rel(LAB_IP_REPORT)],
                ),
            }
        )
    for check in credentials["checks"]:
        if check["classification"] not in {"passed", "not_in_scope"}:
            failures.append(
                {
                    "category": "credential",
                    "classification": check["classification"],
                    "ui_message": f"{check['name']} credential compatibility needs attention.",
                    "report_detail": f"Field `{check['field']}` failed compatibility/configuration; value remains redacted.",
                    "next_action": check["next_action"],
                    **status_source_metadata(
                        source_type="live_cached",
                        checked_at=datetime.now(UTC).isoformat(),
                        recheck_command="make provider-lab-build-verification-live",
                        evidence_artifacts=[_rel(REPORT)],
                    ),
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
                **status_source_metadata(
                    source_type="live_cached",
                    checked_at=datetime.now(UTC).isoformat(),
                    recheck_command="make provider-lab-build-verification-live",
                    evidence_artifacts=[_rel(REPORT)],
                ),
            }
        )
    for check in protocols["checks"]:
        if check["classification"] not in {"passed", "not_in_scope"}:
            failures.append(
                {
                    "category": "protocol",
                    "classification": check["classification"],
                    "ui_message": f"{check['protocol']} is {check['classification']}.",
                    "report_detail": "; ".join(check["blockers"]) if check["blockers"] else check["next_action"],
                    "next_action": check["next_action"],
                    "source_type": check.get("source_type", "not_checked"),
                    "checked_at": check.get("checked_at"),
                    "freshness": check.get("freshness", "unknown"),
                    "ttl_seconds": check.get("ttl_seconds"),
                    "stale_after_seconds": check.get("stale_after_seconds"),
                    "is_current": check.get("is_current", False),
                    "is_operator_visible": check.get("is_operator_visible", True),
                    "recheck_command": check.get("recheck_command"),
                    "evidence_artifacts": check.get("evidence_artifacts", []),
                }
            )
    return sorted(failures, key=lambda item: CLASSIFICATION_ORDER.get(item["classification"], 99))


def _runtime_mode_guard() -> dict[str, Any] | None:
    if settings.provider_mode != "mock":
        return None
    return {
        "category": "runtime-mode",
        "classification": "operator_action_required",
        "ui_message": "Build Verification is running in test/mock mode.",
        "report_detail": "Test fixtures cannot produce real lab certification.",
        "next_action": "Run `make provider-lab-build-verification-live` with PROVIDER_MODE=local-lab-readwrite.",
        **status_source_metadata(
            source_type="test_fixture",
            checked_at=datetime.now(UTC).isoformat(),
            stale_after_seconds=None,
            recheck_command="make provider-lab-build-verification-live",
            evidence_artifacts=[_rel(REPORT)],
            is_operator_visible=False,
        ),
    }


def _build_verification_source_type(*, check_ports: bool) -> str:
    if settings.provider_mode == "mock":
        return "test_fixture"
    return "live_probe" if check_ports else "live_cached"


def _blocker_text_with_source(item: dict[str, Any]) -> str:
    return f"{_source_display(item)}: {item['next_action']}"


def _source_display(item: dict[str, Any]) -> str:
    source_type = item.get("source_type")
    freshness = item.get("freshness")
    if source_type == "live_probe":
        return "Live check"
    if source_type == "live_cached":
        return "Last live result" if freshness == "current" else "Stale live result"
    if source_type == "historical_artifact":
        return "Stale evidence"
    if source_type == "test_fixture":
        return "Test fixture"
    return "Not checked"


def _certification_state(failures: list[dict[str, Any]]) -> str:
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
    if classification == "not_in_scope":
        return f"{protocol} is not in scope for the active lab profile."
    if classification == "blocked_by_prior_stage":
        return f"Complete the prior workflow stage before certifying {protocol}."
    if blockers:
        return f"Restore readiness for {protocol}: {'; '.join(blockers)}"
    return f"Review {protocol} readiness."


def _netapp_source_metadata(netapp_live_state: dict[str, Any]) -> dict[str, Any]:
    checked_at = (
        netapp_live_state.get("checked_at")
        or netapp_live_state.get("verified_at")
        or netapp_live_state.get("last_successful_probe_at")
    )
    source = str(netapp_live_state.get("source") or "")
    source_type = "not_checked" if source in {"", "none"} and not checked_at else "live_cached"
    return status_source_metadata(
        source_type=source_type,
        checked_at=checked_at,
        recheck_command="make provider-lab-refresh-live-state",
        evidence_artifacts=["artifacts/codex-runs/netapp-live-state-report.md"],
    )


def _netapp_protocol_readiness(
    protocol: str,
    netapp_live_state: dict[str, Any],
    reachability_key: str,
) -> dict[str, Any]:
    source_metadata = _netapp_source_metadata(netapp_live_state)
    management = netapp_live_state.get("management") if isinstance(netapp_live_state.get("management"), dict) else {}
    reachable = management.get(reachability_key)
    live_configured = bool(netapp_live_state.get("configured"))
    live_state = str(netapp_live_state.get("configured_state") or "not_detected")
    legacy_env_configured = bool(settings.netapp_configured)
    no_live_state = netapp_live_state.get("source") in {None, "none"} and live_state == "not_detected"
    if live_configured:
        return {
            "protocol": protocol,
            "configured": True,
            "reachable": reachable,
            "required": True,
            "status": "blocked" if reachable is False else "ready",
            "classification": "hard_fail" if reachable is False else "passed",
            "blockers": [f"{protocol} required port is not reachable."] if reachable is False else [],
            "configured_state": live_state,
            "configured_source": netapp_live_state.get("source"),
            "manual_env_flag_required": False,
            "next_action": (
                f"{protocol} is configured from live verification; manual env flag not required."
                if reachable is not False
                else f"Live NetApp state was previously configured, but {protocol} reachability failed."
            ),
            **source_metadata,
        }
    if live_state in {"console_detected", "ontap_detected"}:
        classification = "blocked_by_prior_stage"
        next_action = "Complete NetApp setup validation before certifying REST/SSH."
    elif live_state in {"login_required", "setup_wizard"}:
        classification = "operator_action_required"
        next_action = netapp_live_state.get("next_safe_action") or "Operator action is required before NetApp can be marked configured."
    elif no_live_state and not legacy_env_configured:
        classification = "not_configured_yet"
        next_action = "Run Discover NetApp Console, Read NetApp State, then Validate NetApp Setup."
    elif legacy_env_configured:
        classification = "stale_config" if reachable is False or live_state in {"blocked", "not_detected"} else "operator_action_required"
        next_action = (
            "NETAPP_CONFIGURED=true is legacy/desired state only; live validation failed or has not verified configured state."
        )
    else:
        classification = "hard_fail" if live_state == "blocked" else "not_configured_yet"
        next_action = netapp_live_state.get("next_safe_action") or "Run NetApp live-state validation."
    return {
        "protocol": protocol,
        "configured": False,
        "reachable": reachable,
        "required": legacy_env_configured,
        "status": "blocked" if classification in {"hard_fail", "stale_config", "operator_action_required", "blocked_by_prior_stage"} else "skipped",
        "classification": classification,
        "blockers": list(netapp_live_state.get("blockers") or []),
        "configured_state": live_state,
        "configured_source": netapp_live_state.get("source"),
        "legacy_netapp_configured_env": legacy_env_configured,
        "manual_env_flag_required": False,
        "next_action": next_action,
        **source_metadata,
    }


def _iso_media_readiness() -> dict[str, Any]:
    iso_count = 0
    for directory in settings.media_inventory_dirs:
        path = Path(directory)
        if not _is_directory(path):
            continue
        iso_count += sum(1 for item in rglob_paths(path, "*.iso") if _is_file(item))
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
        **status_source_metadata(
            source_type="live_probe",
            checked_at=datetime.now(UTC).isoformat(),
            recheck_command="make provider-lab-build-verification-live",
        ),
    }


def _cisco_console_readiness() -> dict[str, Any]:
    if settings.cisco_mgmt_configured:
        probe, checked_at = get_probe_result("cisco-ansible")
        command_results = probe.get("command_results") if isinstance(probe, dict) else {}
        show_version = command_results.get("show version") if isinstance(command_results, dict) else {}
        if isinstance(probe, dict) and probe.get("status") == "ok" and isinstance(show_version, dict) and show_version.get("version_hint"):
            return {
                "protocol": "Cisco console",
                "configured": True,
                "reachable": True,
                "required": True,
                "status": "ready",
                "classification": "passed",
                "blockers": [],
                "source": probe.get("provider_id") or "cisco-ansible",
                "fallback": probe.get("fallback"),
                "ios_xe_version": show_version.get("version_hint"),
                "next_action": "Cisco management SSH proof passed; serial console remains optional break-glass evidence.",
                **status_source_metadata(
                    source_type="live_cached",
                    checked_at=checked_at,
                    recheck_command="make provider-lab-refresh-live-state",
                    evidence_artifacts=["artifacts/codex-runs/provider-probe-cache"],
                ),
            }
    details = CODEX_RUN_DIR / "cisco-4h-lab-run-details-redacted.json"
    if not _path_exists(details):
        return protocol_readiness(
            "Cisco console",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Run Cisco console discovery/prompt detection before product certification.",
        )
    payload = read_json_object(details)
    if not payload:
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
            **status_source_metadata(
                source_type="live_cached",
                checked_at=payload.get("checked_at"),
                recheck_command="make provider-lab-cisco-console-ethernet-readiness",
                evidence_artifacts=["artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json"],
            ),
        }
    return protocol_readiness(
        "Cisco console",
        configured=True,
        reachable=None,
        classification="operator_action_required",
        next_action="Connect the Cisco console adapter and rerun prompt detection at 9600.",
    )


def _netapp_console_readiness(*, profile_context: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled"):
        return _not_in_scope_protocol("NetApp console", "NetApp is disabled by the active lab profile.")
    runtime_state = get_netapp_runtime_state()
    console = runtime_state.get("console") if isinstance(runtime_state.get("console"), dict) else {}
    if console.get("discovered_port"):
        return {
            "protocol": "NetApp console",
            "configured": True,
            "reachable": None,
            "required": True,
            "status": "ready",
            "classification": "passed",
            "blockers": [],
            "selected_port": console.get("discovered_port"),
            "selected_baud": console.get("baud"),
            "prompt_state": console.get("prompt_state"),
            "confidence": console.get("confidence"),
            "last_seen": console.get("last_seen"),
            "selection_source": console.get("source"),
            "manual_env_update_required": False,
            "next_action": "NetApp console was detected automatically; no .env port update is required.",
            **_netapp_source_metadata(runtime_state),
        }
    discovery = CODEX_RUN_DIR / "netapp-console-autodiscovery-redacted.json"
    legacy_discovery = CODEX_RUN_DIR / "netapp-console-discovery-redacted.json"
    state = CODEX_RUN_DIR / "netapp-console-state-redacted.json"
    discovery_artifact = discovery if _path_exists(discovery) else legacy_discovery
    if not _path_exists(discovery_artifact):
        return protocol_readiness(
            "NetApp console",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Run NetApp console discovery now that console cables are connected.",
        )
    payload = _read_json_artifact(state if _path_exists(state) else discovery_artifact)
    if not payload:
        return protocol_readiness(
            "NetApp console",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Regenerate NetApp console discovery; the current redacted artifact is unreadable.",
        )
    if payload.get("status") == "ready" and payload.get("selected_port"):
        return {
            "protocol": "NetApp console",
            "configured": True,
            "reachable": None,
            "required": True,
            "status": "ready",
            "classification": "passed",
            "blockers": [],
            "selected_port": payload.get("selected_port"),
            "selected_baud": payload.get("selected_baud"),
            "prompt_state": payload.get("selected_prompt_state"),
            "next_action": "NetApp console discovery/read-state has usable adapter and prompt evidence.",
            **status_source_metadata(
                source_type="live_cached",
                checked_at=payload.get("checked_at"),
                recheck_command="make provider-lab-netapp-console-read-state",
                evidence_artifacts=["artifacts/codex-runs/netapp-console-state-report.md"],
            ),
        }
    return protocol_readiness(
        "NetApp console",
        configured=True,
        reachable=None,
        classification="operator_action_required",
        next_action=payload.get("next_safe_action")
        or "Fix NetApp console cable, adapter ownership, permissions, or baud, then rerun discovery.",
    )


def _netapp_nfs_vcenter_readiness(*, profile_context: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled") or not features.get("vcenter_enabled"):
        return _not_in_scope_protocol(
            "NetApp NFS/vCenter",
            "NetApp or vCenter is disabled by the active lab profile.",
        )
    runtime_state = get_netapp_runtime_state()
    if runtime_state.get("configured"):
        storage = runtime_state.get("storage") if isinstance(runtime_state.get("storage"), dict) else {}
        return {
            "protocol": "NetApp NFS/vCenter",
            "configured": True,
            "reachable": None,
            "required": True,
            "status": "ready",
            "classification": "passed",
            "blockers": [],
            "configured_state": runtime_state.get("configured_state"),
            "configured_source": runtime_state.get("source"),
            "storage": storage,
            "next_action": "NetApp configured state is verified by live check; manual env flag not required.",
            **_netapp_source_metadata(runtime_state),
        }
    path = CODEX_RUN_DIR / "netapp-nfs-vcenter-readiness-redacted.json"
    if not _path_exists(path):
        return protocol_readiness(
            "NetApp NFS/vCenter",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Run NetApp NFS/vCenter readiness before datastore planning.",
        )
    payload = _read_json_artifact(path)
    if not payload:
        return protocol_readiness(
            "NetApp NFS/vCenter",
            configured=True,
            reachable=None,
            classification="operator_action_required",
            next_action="Regenerate NetApp NFS/vCenter readiness; the current redacted artifact is unreadable.",
        )
    if payload.get("status") == "ready":
        return {
            "protocol": "NetApp NFS/vCenter",
            "configured": True,
            "reachable": None,
            "required": True,
            "status": "ready",
            "classification": "passed",
            "blockers": [],
            "single_management_port_mode": payload.get("single_management_port_mode"),
            "next_action": "NetApp NFS/vCenter readiness preview is clear; apply remains a separate future workflow.",
            **status_source_metadata(
                source_type="live_cached",
                checked_at=payload.get("checked_at"),
                recheck_command="make provider-lab-netapp-nfs-vcenter-readiness",
                evidence_artifacts=["artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md"],
            ),
        }
    return protocol_readiness(
        "NetApp NFS/vCenter",
        configured=True,
        reachable=None,
        classification="blocked_by_prior_stage",
        next_action=payload.get("next_safe_action")
        or "Complete NetApp API, ESXi, and vCenter prerequisites before NFS datastore apply.",
    )


def _read_json_artifact(path: Path) -> dict[str, Any] | None:
    payload = read_json_object(path)
    return payload or None


def _stale_artifact_evidence() -> list[dict[str, str]]:
    evidence = []
    for path in [
        CODEX_RUN_DIR / "cisco-bootstrap-apply-report.md",
        CODEX_RUN_DIR / "overnight-lab-builder-final-report.md",
    ]:
        if not _path_exists(path):
            continue
        text = safe_read_text(path)
        if not text:
            continue
        if "10.10.8." in text:
            evidence.append(
                {
                    "artifact": _rel(path),
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


def _python_tool(name: str, module: str, purpose: str, *, required: bool) -> dict[str, Any]:
    spec = importlib_util.find_spec(module)
    return {
        "name": name,
        "type": "python-package",
        "module": module,
        "available": spec is not None,
        "required": required,
        "version": _python_module_version(module) if spec else None,
        "purpose": purpose,
        "check": f"import {module}",
    }


def _optional_python_family_tool(name: str, modules: tuple[str, ...], purpose: str) -> dict[str, Any]:
    checks = [
        {
            "module": module,
            "available": importlib_util.find_spec(module) is not None,
            "version": _python_module_version(module),
        }
        for module in modules
    ]
    return {
        "name": name,
        "type": "python-package-family",
        "modules": checks,
        "available": all(item["available"] for item in checks),
        "required": False,
        "purpose": purpose,
        "check": " and ".join(f"import {module}" for module in modules),
    }


def _python_module_version(module: str) -> str | None:
    try:
        package_name = {
            "serial": "pyserial",
            "netapp_ontap": "netapp-ontap",
        }.get(module, module)
        from importlib import metadata

        return metadata.version(package_name)
    except Exception:
        return None


def _cli_tool(name: str, command: str, purpose: str, *, required: bool) -> dict[str, Any]:
    path = _command_path(command)
    return {
        "name": name,
        "type": "cli",
        "command": command,
        "available": path is not None,
        "required": required,
        "path": path,
        "version": _cli_version(command, path) if path else None,
        "purpose": purpose,
        "check": f"{command} --version",
    }


def _command_path(command: str) -> str | None:
    path = which(command)
    if path:
        return path
    for directory in (Path(sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        candidate = directory / command
        if _path_exists(candidate) and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _tool_env() -> dict[str, str]:
    env = dict(os.environ)
    venv_bin = str(Path(sys.executable).parent)
    local_bin = str(REPO_ROOT / ".local" / "bin")
    env["PATH"] = os.pathsep.join([venv_bin, local_bin, env.get("PATH", "")])
    local_collections = str(REPO_ROOT / ".local" / "ansible" / "collections")
    existing_collections = env.get("ANSIBLE_COLLECTIONS_PATH")
    env["ANSIBLE_COLLECTIONS_PATH"] = (
        os.pathsep.join([local_collections, existing_collections])
        if existing_collections
        else local_collections
    )
    return env


def _cli_version(command: str, path: str) -> str | None:
    version_args = {
        "ansible": [path, "--version"],
        "govc": [path, "version"],
        "ilorest": [path, "--version"],
    }.get(command, [path, "--version"])
    try:
        result = subprocess.run(
            version_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3.0,
            check=False,
            env=_tool_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first_line = (result.stdout or "").splitlines()[0:1]
    return first_line[0].strip() if first_line else None


def _ansible_collection_tool(name: str, collection: str, purpose: str, *, required: bool) -> dict[str, Any]:
    ansible_galaxy = _command_path("ansible-galaxy")
    available = False
    version = None
    if ansible_galaxy:
        try:
            result = subprocess.run(
                [ansible_galaxy, "collection", "list", collection],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5.0,
                check=False,
                env=_tool_env(),
            )
            available = result.returncode == 0 and collection in (result.stdout or "")
            for line in (result.stdout or "").splitlines():
                if line.strip().startswith(collection):
                    parts = line.split()
                    version = parts[1] if len(parts) > 1 else None
                    break
        except (OSError, subprocess.TimeoutExpired):
            available = False
    return {
        "name": name,
        "type": "ansible-collection",
        "collection": collection,
        "available": available,
        "required": required,
        "version": version,
        "purpose": purpose,
        "check": f"ansible-galaxy collection list {collection}",
    }


def _managed_state_plan() -> dict[str, Any]:
    return {
        "cisco": {
            "sequence": [
                "Use console bootstrap first via local_serial or tcp_console/ser2net.",
                "Enable management SSH only through an explicit guarded bootstrap workflow.",
                "Use Ansible cisco.ios, Netmiko, and pyATS/Genie parsing for read-only validation and later managed state after SSH is enabled.",
            ],
            "primary_tools": ["local_serial", "tcp_console/ser2net", "Ansible cisco.ios", "Netmiko"],
            "optional_tools": ["pyATS/Genie"],
            "safety": "No configure, write memory, reload, copy, erase, or SSH changes run from this check.",
        },
        "hpe_ilo": {
            "sequence": [
                "Use Redfish direct as the default API path.",
                "Use HPE iLOrest when vendor tooling provides better coverage for iLO settings, firmware, or inventory.",
                "Keep all iLO write lanes behind explicit local-lab-readwrite acknowledgements.",
            ],
            "primary_tools": ["Redfish direct", "HPE iLOrest"],
            "safety": "Availability checks do not contact iLO.",
        },
        "esxi_vsphere": {
            "sequence": [
                "Install ESXi through iLO virtual media and Kickstart readiness gates.",
                "Use govc after the management network is configured.",
                "Reserve deployment operations for approved post-install workflows.",
            ],
            "primary_tools": ["Kickstart", "govc"],
            "safety": "This run checks local tools only and does not deploy or reconfigure hosts.",
        },
        "netapp": {
            "sequence": [
                "Use local serial console discovery/read-state first for physical/controller state evidence.",
                "Use netapp-ontap Python client or ONTAP REST as the primary managed-state path.",
                "Use ONTAP REST direct where simple GET/compare logic is enough after cluster management is configured.",
                "Keep NFS/vCenter datastore apply and all ONTAP writes behind explicit NetApp stage gates.",
            ],
            "primary_tools": ["local serial console", "netapp-ontap Python client", "ONTAP REST", "govc"],
            "safety": "NetApp console discovery is newline-only; ONTAP/NFS/vCenter apply remains disabled.",
        },
    }


def _firmware_toolchain_strategy() -> dict[str, Any]:
    return {
        "baseline_source": "config/firmware-baselines/real-lab.yml",
        "inventory_sources": [
            "Cisco show version from console or SSH after readiness gates",
            "HPE iLO Redfish/iLOrest inventory",
            "ESXi/vSphere version from govc after install",
            "NetApp ONTAP REST/system version after read-only discovery is approved",
        ],
        "rule": "Compare local baseline manifest to vendor package inventory before any firmware apply lane is enabled.",
    }


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
        f"- Source: `{payload.get('source_type')}`",
        f"- Freshness: `{payload.get('freshness')}`",
        f"- Current: `{payload.get('is_current')}`",
        f"- Operator visible: `{payload.get('is_operator_visible')}`",
        f"- Recheck command: `{payload.get('recheck_command')}`",
        "",
        "## Lab IP Profile",
        "",
        f"- Status: `{payload['lab_ip_profile']['status']}`",
        f"- Profile: `{payload['lab_ip_profile']['effective_profile']['name']}`",
        f"- Topology: `{payload['lab_ip_profile']['active_lab_profile'].get('topology')}`",
        f"- Not in scope: `{', '.join(payload['lab_ip_profile'].get('not_in_scope_stages') or []) or 'none'}`",
        f"- iLO: `{payload['lab_ip_profile']['expected']['ilo']}`",
        f"- Server embedded NIC: `{payload['lab_ip_profile']['expected']['server_embedded_nic']}`",
        f"- ESXi management: `{payload['lab_ip_profile']['expected']['esxi_management']}`",
        f"- Cisco management: `{payload['lab_ip_profile']['expected']['cisco_management']}`",
        f"- Ansible/control host: `{payload['lab_ip_profile']['expected']['ansible_control_host']}`",
        f"- NetApp Controller A SP: `{payload['lab_ip_profile']['expected']['netapp_controller_a_sp']}`",
        f"- NetApp Controller B SP: `{payload['lab_ip_profile']['expected']['netapp_controller_b_sp']}`",
        f"- NetApp cluster management: `{payload['lab_ip_profile']['expected']['netapp_cluster_mgmt']}`",
        f"- NetApp node management: `{payload['lab_ip_profile']['expected']['netapp_node_a_mgmt']}` / `{payload['lab_ip_profile']['expected']['netapp_node_b_mgmt']}`",
        f"- NetApp SVM management: `{payload['lab_ip_profile']['expected']['netapp_svm_mgmt']}`",
        f"- NetApp NFS LIFs: `{payload['lab_ip_profile']['expected']['netapp_nfs_lifs']}`",
        f"- NetApp iSCSI LIFs: `{payload['lab_ip_profile']['expected']['netapp_iscsi_lifs']}`",
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
    lines.extend(["", "## License Material", ""])
    for item in payload.get("licenses", {}).get("checks") or []:
        lines.append(
            f"- `{item['classification']}` `{item['product']}`: "
            f"{'configured' if item['configured'] else 'not configured'}; "
            f"count=`{item.get('license_count', 0)}`; values redacted"
        )
    lines.extend(["", "## MTU Consistency", ""])
    mtu = payload.get("mtu") or {}
    lines.append(f"- Classification: `{mtu.get('classification', 'unknown')}`")
    lines.append(f"- Invalid values: `{len(mtu.get('invalid') or {})}`")
    lines.append(f"- Path mismatches: `{len(mtu.get('mismatches') or [])}`")
    netapp_state = payload.get("netapp_live_state") or {}
    console = netapp_state.get("console") if isinstance(netapp_state.get("console"), dict) else {}
    lines.extend(["", "## NetApp Live State", ""])
    lines.append(f"- Configured state: `{netapp_state.get('configured_state', 'unknown')}`")
    lines.append(f"- Configured: `{netapp_state.get('configured', False)}`")
    lines.append(f"- Source: `{netapp_state.get('source', 'unknown')}`")
    lines.append(f"- Manual env flag required: `{netapp_state.get('manual_env_flag_required', False)}`")
    lines.append(f"- Discovered console port: `{console.get('discovered_port') or 'none'}`")
    lines.append(f"- Console baud: `{console.get('baud') or 'none'}`")
    lines.append(f"- Console confidence: `{console.get('confidence') or 'none'}`")
    lines.extend(["", "## Protocol Readiness", ""])
    for item in payload.get("protocols", {}).get("checks") or []:
        lines.append(
            f"- `{item['classification']}` `{item['protocol']}`: {item['next_action']}"
        )
    toolchain = payload.get("toolchain") or {}
    lines.extend(["", "## Toolchain Readiness", ""])
    lines.append(f"- Status: `{toolchain.get('status', 'unknown')}`")
    lines.append(
        "- Missing required: "
        + (", ".join(f"`{item}`" for item in toolchain.get("required_missing") or []) or "none")
    )
    lines.append(
        "- Missing optional: "
        + (", ".join(f"`{item}`" for item in toolchain.get("optional_missing") or []) or "none")
    )
    for item in toolchain.get("tools") or []:
        lines.append(
            f"- `{'available' if item.get('available') else 'missing'}` `{item.get('name')}`: {item.get('purpose')}"
        )
    lines.extend(["", "## Post-Build Checklist", ""])
    lines.extend(f"- `{item['status']}` {item['item']}" for item in payload.get("post_build_checklist") or [])
    lines.extend(["", "## Safety", "", "- Credential values, tokens, and secrets are redacted.", ""])
    return "\n".join(lines)


def _current_state_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Build Verification Current State Report",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{payload['status']}`",
        f"- Source: `{payload.get('source_type')}`",
        f"- Freshness: `{payload.get('freshness')}`",
        f"- Current: `{payload.get('is_current')}`",
        f"- Recheck: `{payload.get('recheck_command')}`",
        "",
        "## Current Blockers",
        "",
    ]
    blockers = _current_report_blockers(payload)
    lines.extend(f"- {blocker}" for blocker in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(["", "## Current Warnings", ""])
    warnings = payload.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- none")
    lines.extend(["", "## Current Protocol Checks", ""])
    for item in payload.get("protocols", {}).get("checks") or []:
        if item.get("source_type") == "historical_artifact":
            continue
        lines.append(
            f"- `{item.get('classification')}` `{item.get('protocol')}` "
            f"source=`{item.get('source_type')}` freshness=`{item.get('freshness')}` "
            f"current=`{item.get('is_current')}`"
        )
    lines.extend(["", "## Current License Material", ""])
    for item in payload.get("licenses", {}).get("checks") or []:
        lines.append(
            f"- `{item.get('classification')}` `{item.get('product')}` "
            f"configured=`{item.get('configured')}` count=`{item.get('license_count', 0)}` values=`redacted`"
        )
    lines.extend(["", "## Safety", "", "- No secrets or raw transcripts are included.", ""])
    return "\n".join(lines)


def _current_report_blockers(payload: dict[str, Any]) -> list[str]:
    blockers = list(payload.get("blockers") or [])
    for item in payload.get("protocols", {}).get("checks") or []:
        if item.get("source_type") == "historical_artifact":
            continue
        if item.get("classification") in {"passed", "not_in_scope"}:
            continue
        protocol = item.get("protocol") or "Protocol"
        detail = "; ".join(item.get("blockers") or []) or item.get("next_action") or "Needs operator attention."
        blockers.append(f"{protocol}: {detail}")
    return unique_preserving_order(str(item) for item in blockers if item)


def _evidence_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Build Verification Evidence Report",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        "- Historical artifacts are evidence only and do not create current blockers by themselves.",
        "",
        "## Evidence Artifacts",
        "",
    ]
    artifacts = payload.get("evidence_artifacts") or []
    lines.extend(f"- `{artifact}`" for artifact in artifacts)
    stale_artifacts = payload.get("lab_ip_profile", {}).get("stale_artifact_evidence") or []
    lines.extend(["", "## Stale Evidence", ""])
    if stale_artifacts:
        lines.extend(
            f"- `{item.get('artifact')}`: {item.get('next_action')}"
            for item in stale_artifacts
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Raw Finding Sources", ""])
    for item in payload.get("failures") or []:
        lines.append(
            f"- `{item.get('classification')}` `{item.get('category')}` "
            f"source=`{item.get('source_type')}` freshness=`{item.get('freshness')}` "
            f"current=`{item.get('is_current')}`"
        )
    lines.extend(["", "## Safety", "", "- Credential values, tokens, and secrets are redacted.", ""])
    return "\n".join(lines)


def _toolchain_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Toolchain Availability Report",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{payload['status']}`",
        f"- Provider mode: `{payload['provider_mode']}`",
        f"- Next safe action: {payload['next_safe_action']}",
        "",
        "## Local Tool Checks",
        "",
    ]
    for tool in payload.get("tools") or []:
        version = tool.get("version")
        lines.append(
            f"- `{'available' if tool.get('available') else 'missing'}` `{tool.get('name')}` "
            f"required=`{tool.get('required')}` check=`{tool.get('check')}`"
            + (f" version=`{version}`" if version else "")
        )
        lines.append(f"  - Purpose: {tool.get('purpose')}")
    lines.extend(
        [
            "",
            "## Managed-State Plan",
            "",
            "### Cisco",
        ]
    )
    for line in payload["managed_state"]["cisco"]["sequence"]:
        lines.append(f"- {line}")
    lines.extend(["", "### HPE / iLO"])
    for line in payload["managed_state"]["hpe_ilo"]["sequence"]:
        lines.append(f"- {line}")
    lines.extend(["", "### ESXi / vSphere"])
    for line in payload["managed_state"]["esxi_vsphere"]["sequence"]:
        lines.append(f"- {line}")
    lines.extend(["", "### NetApp"])
    for line in payload["managed_state"]["netapp"]["sequence"]:
        lines.append(f"- {line}")
    firmware = payload.get("firmware_strategy") or {}
    lines.extend(
        [
            "",
            "## Firmware Strategy",
            "",
            f"- Baseline source: `{firmware.get('baseline_source')}`",
            f"- Rule: {firmware.get('rule')}",
        ]
    )
    for source in firmware.get("inventory_sources") or []:
        lines.append(f"- Inventory source: {source}")
    lines.extend(["", "## Safety", "", "- This check does not contact real infrastructure or run destructive workflows.", ""])
    return "\n".join(lines)


def _lab_ip_markdown(payload: dict[str, Any]) -> str:
    profile = payload["lab_ip_profile"]
    lines = [
        "# Lab IP Profile Update",
        "",
        f"- Checked at: `{payload['checked_at']}`",
        f"- Status: `{profile['status']}`",
        f"- Source: `{payload.get('source_type')}`",
        f"- Freshness: `{payload.get('freshness')}`",
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
            f"- Ansible starts after Cisco management SSH is configured at `{profile['expected']['cisco_management']}`.",
            "- Ansible is for show commands, backup, validation, drift checks, and future repeatable config.",
            "- Ansible is not the initial Cisco bootstrap path.",
            "",
            "## Reports",
            "",
            f"- Build verification report: `{_rel(REPORT)}`",
            f"- Build verification summary: `{_rel(SUMMARY)}`",
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
        f"- Source: `{payload.get('source_type')}`",
        f"- Freshness: `{payload.get('freshness')}`",
        "",
        "## Current Profile",
        "",
        f"- Lab subnet: `{profile['expected']['subnet']}`",
        f"- iLO: `{profile['expected']['ilo']}`",
        f"- Server embedded NIC: `{profile['expected']['server_embedded_nic']}`",
        f"- ESXi management: `{profile['expected']['esxi_management']}`",
        f"- Cisco management: `{profile['expected']['cisco_management']}`",
        f"- Ansible/control host: `{profile['expected']['ansible_control_host']}`",
        f"- NetApp Controller A SP: `{profile['expected']['netapp_controller_a_sp']}`",
        f"- NetApp Controller B SP: `{profile['expected']['netapp_controller_b_sp']}`",
        f"- NetApp cluster management: `{profile['expected']['netapp_cluster_mgmt']}`",
        f"- NetApp Node A management/e0M: `{profile['expected']['netapp_node_a_mgmt']}`",
        f"- NetApp Node B management/e0M: `{profile['expected']['netapp_node_b_mgmt']}`",
        f"- NetApp SVM management: `{profile['expected']['netapp_svm_mgmt']}`",
        f"- NetApp NFS LIFs: `{profile['expected']['netapp_nfs_lifs']}`",
        f"- NetApp iSCSI LIFs: `{profile['expected']['netapp_iscsi_lifs']}`",
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
        f"- Source: `{payload.get('source_type')}`",
        f"- Freshness: `{payload.get('freshness')}`",
        f"- Current: `{payload.get('is_current')}`",
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
            "next_action": lab_profile.get("next_action", "Use 192.168.1.201-.215 lab targets."),
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
