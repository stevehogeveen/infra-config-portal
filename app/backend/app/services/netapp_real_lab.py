from __future__ import annotations

import glob
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.lab_profiles import active_lab_profile_context
from app.services.list_utils import unique_preserving_order
from app.services.serial_console_discovery import (
    SerialConsoleDiscoveryPaths,
    SerialConsoleProbeOptions,
    discover_serial_console_candidates,
    probe_serial_candidates,
    selectable_serial_candidates,
    serial_baud_order,
)
from app.services.netapp_state import (
    get_netapp_runtime_state,
    read_netapp_live_state,
    update_netapp_runtime_state_from_console_probe,
    validate_netapp_setup,
)
from app.services.path_utils import display_path, is_file, path_exists

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

CONSOLE_DISCOVERY_REPORT = CODEX_RUN_DIR / "netapp-console-autodiscovery-report.md"
CONSOLE_DISCOVERY_JSON = CODEX_RUN_DIR / "netapp-console-autodiscovery-redacted.json"
CONSOLE_STATE_REPORT = CODEX_RUN_DIR / "netapp-console-state-report.md"
CONSOLE_STATE_JSON = CODEX_RUN_DIR / "netapp-console-state-redacted.json"
CONSOLE_LOGIN_STATE_REPORT = CODEX_RUN_DIR / "netapp-console-login-state-report.md"
CONSOLE_LOGIN_STATE_JSON = CODEX_RUN_DIR / "netapp-console-login-state-redacted.json"
NFS_VCENTER_READINESS_REPORT = CODEX_RUN_DIR / "netapp-nfs-vcenter-readiness-report.md"
NFS_VCENTER_READINESS_JSON = CODEX_RUN_DIR / "netapp-nfs-vcenter-readiness-redacted.json"

CONSOLE_GLOBS = (
    "/dev/serial/by-id/*",
    "/dev/ttyUSB*",
    "/dev/ttyACM*",
)
USB_SERIAL_NAME_HINTS = (
    "NetApp",
    "MCP2221",
    "Microchip",
    "FTDI",
    "Prolific",
    "Silicon_Labs",
    "CP210",
    "USB-Serial",
)
COMMON_NETAPP_CONSOLE_BAUDS = (115200, 9600, 19200, 38400, 57600)
VALID_NETAPP_STATES = {
    "loader_prompt",
    "boot_menu",
    "cluster_setup_prompt",
    "node_setup_prompt",
    "existing_cluster_shell",
    "login_required",
    "password_required",
    "booting",
    "sp_bmc_login",
}
NETAPP_SERIAL_WAKE_SEQUENCES = (
    ("newline", b"\n"),
    ("carriage-return", b"\r"),
)
NETAPP_MAX_PROBE_CANDIDATES = 4
NOT_ATTEMPTED = [
    "Ctrl+C, Ctrl+Z, break, boot menu selection, or any boot interruption",
    "username or password entry",
    "cluster setup commands",
    "SP, node, SVM, LIF, volume, export, or datastore creation",
    "ONTAP API write",
    "vCenter or ESXi datastore mount",
    "controller reboot, takeover/giveback, wipe, or upgrade",
]
READ_ONLY_ONTAP_COMMANDS = (
    ("disable_paging", "set -rows 0"),
    ("ontap_version", "version"),
    ("node_identity", "system node show -fields node,model,health,uptime"),
    ("cluster_status", "cluster show"),
    (
        "network_interface_summary",
        "network interface show -fields vserver,lif,address,role,home-node,home-port,status-admin,status-oper",
    ),
    ("storage_aggregate_summary", "storage aggregate show -fields aggregate,node,state,size,availsize,usedsize"),
)


@dataclass(frozen=True)
class NetAppConsoleCandidate:
    path: str
    stable_path: bool
    exists: bool
    readable: bool | None
    writable: bool | None
    label: str | None
    target_path: str | None
    in_use: bool
    rank: int
    recommendation: str


def get_latest_netapp_console_discovery() -> dict[str, Any]:
    latest = _latest_or_not_run(
        CONSOLE_DISCOVERY_JSON,
        action="console-discovery",
        message="NetApp console discovery has not run yet.",
        next_safe_action="Run `make provider-lab-netapp-console-autodiscovery`.",
    )
    return {**latest, "runtime_state": get_netapp_runtime_state()}


def get_latest_netapp_console_state() -> dict[str, Any]:
    latest = _latest_or_not_run(
        CONSOLE_STATE_JSON,
        action="console-read-state",
        message="NetApp console read-state has not run yet.",
        next_safe_action="Run `make provider-lab-netapp-console-read-state` after console cables are connected.",
    )
    return {**latest, "runtime_state": get_netapp_runtime_state()}


def run_netapp_console_discovery(*, session: Session | None = None) -> dict[str, Any]:
    return _run_console_probe(
        action="console-discovery",
        report_path=CONSOLE_DISCOVERY_REPORT,
        json_path=CONSOLE_DISCOVERY_JSON,
        message="NetApp console discovery completed.",
        session=session,
    )


def run_netapp_console_read_state(*, session: Session | None = None) -> dict[str, Any]:
    return _run_console_probe(
        action="console-read-state",
        report_path=CONSOLE_STATE_REPORT,
        json_path=CONSOLE_STATE_JSON,
        message="NetApp console state read completed.",
        session=session,
    )


def run_netapp_console_login_state() -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    console_state = get_latest_netapp_console_state()
    selected_port = console_state.get("selected_port")
    selected_baud = console_state.get("selected_baud")
    prompt_state = console_state.get("selected_prompt_state")
    identified_state = _identify_console_state(prompt_state)
    credentials = _netapp_console_credential_state()
    login_attempted = False
    read_only_commands_attempted = False
    command_results: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings = [
        "Guarded console login only uses NetApp-specific console credentials or NetApp API credentials as a fallback.",
        "Read-only commands are fixed and only run after an ONTAP shell prompt is detected.",
        "No setup, cluster creation, network configuration, storage provisioning, reboot, wipe, or upgrade commands are sent.",
    ]

    if not selected_port or not selected_baud:
        blockers.append("No selected NetApp console port/baud exists; rerun console read-state first.")
    elif identified_state in {"cluster_setup_wizard", "node_setup_wizard"}:
        warnings.append(
            f"Current console state is `{identified_state}`; this is identified state, but no setup command is allowed in this stage."
        )
    elif identified_state in {"loader", "boot_menu", "sp_bmc_login"}:
        blockers.append(
            f"Current console state is `{identified_state}`; credential entry and ONTAP read-only commands are not safe in this state."
        )
    elif identified_state == "login_required" and not credentials["usable"]:
        blockers.append("NetApp console/API credentials are missing; guarded login was skipped.")
    elif identified_state == "ontap_shell":
        read_only_commands_attempted = True
        command_results = _run_console_read_only_commands(
            str(selected_port),
            int(selected_baud),
            credentials=None,
        )
    elif identified_state == "login_required" and credentials["usable"]:
        login_attempted = True
        read_only_commands_attempted = True
        command_results = _run_console_read_only_commands(
            str(selected_port),
            int(selected_baud),
            credentials=credentials,
        )
        if not command_results:
            blockers.append("Guarded console login did not reach an ONTAP shell prompt.")
    else:
        blockers.append(f"Current console state is `{identified_state}`; no safe login/read-only command path is available.")

    status = "ready" if identified_state in {"cluster_setup_wizard", "node_setup_wizard", "ontap_shell"} and not command_results else "blocked"
    if command_results and all(item.get("status") == "captured" for item in command_results):
        status = "ready"
    elif command_results:
        status = "warning"
    effective_identified_state = _identified_state_after_commands(identified_state, command_results)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "console-login-state",
        "checked_at": checked_at,
        "status": status,
        "message": "NetApp console login/read-only state identification completed.",
        "mode": settings.provider_mode,
        "selected_port": selected_port,
        "selected_baud": selected_baud,
        "prompt_state": prompt_state,
        "initial_identified_state": identified_state,
        "identified_state": effective_identified_state,
        "credential_state": {
            "console_username_configured": credentials["console_username_configured"],
            "console_password_configured": credentials["console_password_configured"],
            "api_username_configured": credentials["api_username_configured"],
            "api_password_configured": credentials["api_password_configured"],
            "usable": credentials["usable"],
        },
        "login_attempted": login_attempted,
        "read_only_commands_attempted": read_only_commands_attempted,
        "read_only_commands": [
            {"id": command_id, "command": command} for command_id, command in READ_ONLY_ONTAP_COMMANDS
        ],
        "command_results": command_results,
        "blockers": blockers,
        "warnings": warnings,
        "artifacts": {
            "report": _rel(CONSOLE_LOGIN_STATE_REPORT),
            "json": _rel(CONSOLE_LOGIN_STATE_JSON),
            "console_state": _rel(CONSOLE_STATE_JSON),
        },
        "not_attempted": [
            "cluster setup commands",
            "SP, node, SVM, LIF, volume, export, datastore, user, or iSCSI configuration",
            "ONTAP API write",
            "vCenter or ESXi datastore mount",
            "controller reboot, takeover/giveback, wipe, or upgrade",
        ],
        "next_safe_action": _console_login_next_action(effective_identified_state, credentials, blockers, command_results),
    }
    sanitized = _sanitize(payload)
    runtime_state = update_netapp_runtime_state_from_console_probe(
        _login_runtime_probe_payload(sanitized),
    )
    sanitized["runtime_state"] = runtime_state
    _write_json(CONSOLE_LOGIN_STATE_JSON, sanitized)
    write_text_value(CONSOLE_LOGIN_STATE_REPORT, _console_login_markdown(sanitized))
    return sanitized


def latest_console_ontap_version() -> dict[str, Any]:
    payload = read_json_object(CONSOLE_LOGIN_STATE_JSON)
    if not payload:
        return {"version": None, "source": "not_available", "checked_at": None}
    version = _ontap_version_from_console_payload(payload)
    return {
        "version": version,
        "source": "console_read_only" if version else "not_available",
        "checked_at": payload.get("checked_at"),
        "identified_state": payload.get("identified_state"),
    }


def _ontap_version_from_console_payload(payload: dict[str, Any]) -> str | None:
    results = payload.get("command_results")
    if not isinstance(results, list):
        return None
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("id") != "ontap_version":
            continue
        text = str(result.get("output_excerpt") or "")
        match = re.search(r"NetApp Release\s+([0-9][0-9A-Za-z_.-]*)", text)
        if match:
            return match.group(1).rstrip(":,;")
    return None


def _login_runtime_probe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    effective_state = payload.get("identified_state")
    selected_prompt_state = (
        "existing_cluster_shell"
        if effective_state == "ontap_shell"
        else payload.get("prompt_state")
    )
    selected_prompt_label = (
        "Existing ONTAP cluster shell"
        if selected_prompt_state == "existing_cluster_shell"
        else "NetApp login prompt"
        if selected_prompt_state in {"login_required", "password_required"}
        else None
    )
    return {
        **payload,
        "selected_prompt_state": selected_prompt_state,
        "selected_prompt_label": selected_prompt_label,
        "selection_source": "console-login-state",
    }


def _identified_state_after_commands(
    identified_state: str,
    command_results: list[dict[str, Any]],
) -> str:
    captured = [item for item in command_results if item.get("status") == "captured"]
    if not captured:
        return identified_state
    if any(item.get("prompt_state") == "existing_cluster_shell" for item in captured):
        return "ontap_shell"
    if len(captured) == len(command_results):
        return "ontap_shell"
    return identified_state


def get_netapp_live_state(*, write_report: bool = False) -> dict[str, Any]:
    state = get_netapp_runtime_state()
    payload = {
        **state,
        "action": "cached-live-state",
        "status": "ready" if state.get("configured") else "not_run" if state.get("source") == "none" else "blocked",
        "message": (
            "Cached NetApp configured state is verified by live check."
            if state.get("configured")
            else "Cached NetApp live state is not configured yet."
        ),
        "warnings": ["Manual env flag not required."],
    }
    if write_report:
        read_netapp_live_state(check_ports=False, write_report=True)
    return payload


def run_netapp_live_state() -> dict[str, Any]:
    return read_netapp_live_state(write_report=True)


def run_netapp_setup_validation() -> dict[str, Any]:
    return validate_netapp_setup(write_report=True)


def get_netapp_nfs_vcenter_readiness(*, check_ports: bool | None = None, write_report: bool = True) -> dict[str, Any]:
    if check_ports is None:
        check_ports = settings.provider_mode in REAL_CONTACT_MODES
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    profile_context = active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    plan = profile_context.get("resolved_address_plan") or {}
    vcenter_in_scope = features.get("vcenter_enabled") is True
    if not features.get("netapp_enabled"):
        payload = {
            "provider_id": PROVIDER_ID,
            "action": "nfs-vcenter-readiness",
            "checked_at": checked_at,
            "status": "not_in_scope",
            "message": "NetApp NFS readiness is not in scope for the active lab profile.",
            "mode": settings.provider_mode,
            "apply_enabled": False,
            "ontap_apply_enabled": False,
            "vcenter_apply_enabled": False,
            "esxi_apply_enabled": False,
            "manual_env_flag_required": False,
            "live_state": {"configured": False, "configured_state": "not_in_scope"},
            "single_management_port_mode": None,
            "management_topology": {
                "connected_management_ports": [],
                "note": "NetApp is not in scope for the active lab profile.",
            },
            "planned_nfs": {
                "storage_protocol": features.get("storage_protocol") or "none",
                "svm_management_ip": None,
                "nfs_lifs": [],
                "volume": None,
                "export_policy": None,
                "mount_path": None,
                "datastore_name": settings.netapp_nfs_datastore_name,
                "client_match": plan.get("subnet"),
            },
            "targets": {
                "netapp_cluster_mgmt_ip": None,
                "netapp_configured_source": "not_in_scope",
                "legacy_netapp_configured_env": False,
                "esxi_management_ip": plan.get("esxi_management"),
                "vcenter_host_configured": False,
                "vcenter_configured": False,
                "govc_available": False,
            },
            "connectivity": {},
            "plan_preview": {
                "ontap_steps": [],
                "vcenter_steps": [],
                "govc_preview": "not_in_scope",
                "esxi_fallback_preview": "not_in_scope",
            },
            "artifacts": {
                "report": _rel(NFS_VCENTER_READINESS_REPORT),
                "json": _rel(NFS_VCENTER_READINESS_JSON),
            },
            "warnings": [
                "NetApp is disabled by the active lab profile; this is not a blocker.",
            ],
            "blockers": [],
            "not_attempted": NOT_ATTEMPTED,
            "next_safe_action": "Enable NetApp in the active lab profile when this readiness lane is intentionally in scope.",
        }
        sanitized = _sanitize(payload)
        if write_report:
            _write_json(NFS_VCENTER_READINESS_JSON, sanitized)
            write_text_value(NFS_VCENTER_READINESS_REPORT, _nfs_vcenter_markdown(sanitized))
        return sanitized
    netapp_live_state = (
        read_netapp_live_state(check_ports=check_ports, write_report=False)
        if check_ports
        else get_netapp_runtime_state()
    )
    live_configured = bool(netapp_live_state.get("configured"))
    legacy_env_configured = bool(settings.netapp_configured)
    nfs_lifs = list(settings.netapp_nfs_lifs)
    first_nfs_lif = nfs_lifs[0] if nfs_lifs else settings.netapp_svm_mgmt_ip
    connected_management_ports = list(settings.netapp_connected_management_ports)
    single_management_port = len(connected_management_ports) <= 1
    netapp_credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
    vcenter_credentials_present = bool(settings.vcenter_username and settings.vcenter_password)
    govc_available = _tool_available("govc")
    netapp_api_configured = bool((live_configured or legacy_env_configured) and settings.netapp_cluster_mgmt_ip)
    vcenter_target_host = _host_from_url(settings.vcenter_host) or settings.vcenter_management_ip
    vcenter_configured = bool(settings.vcenter_configured or settings.vcenter_host or settings.vcenter_management_ip)
    esxi_configured = bool(settings.esxi_configured and settings.esxi_test_host)

    connectivity = {
        "netapp_cluster_rest_443": _tcp_check(
            settings.netapp_cluster_mgmt_ip,
            443,
            enabled=bool(check_ports and netapp_api_configured),
            disabled_reason=(
                "NetApp live configured state has not been verified; cluster management REST is planned but not live."
                if not live_configured and not legacy_env_configured
                else "Port checks disabled for this run."
            ),
        ),
        "netapp_cluster_ssh_22": _tcp_check(
            settings.netapp_cluster_mgmt_ip,
            22,
            enabled=bool(check_ports and netapp_api_configured),
            disabled_reason=(
                "NetApp live configured state has not been verified; cluster management SSH is planned but not live."
                if not live_configured and not legacy_env_configured
                else "Port checks disabled for this run."
            ),
        ),
        "vcenter_443": _tcp_check(
            vcenter_target_host,
            443,
            enabled=bool(check_ports and vcenter_configured),
            disabled_reason=(
                "VCENTER_CONFIGURED=false and VCENTER_HOST/GOVC_URL/VCENTER_MANAGEMENT_IP is missing."
                if not vcenter_configured
                else "Port checks disabled for this run."
            ),
        ),
        "esxi_api_443": _tcp_check(
            settings.esxi_test_host,
            443,
            enabled=bool(check_ports and esxi_configured),
            disabled_reason=(
                "ESXI_CONFIGURED=false or ESXI_TEST_HOST is missing."
                if not esxi_configured
                else "Port checks disabled for this run."
            ),
        ),
        "planned_nfs_lifs_2049": [
            _tcp_check(
                lif,
                2049,
                enabled=bool(check_ports and netapp_api_configured),
                disabled_reason=(
                    "NFS LIFs are planned only until NetApp setup live verification confirms data readiness."
                    if not live_configured and not legacy_env_configured
                    else "Port checks disabled for this run."
                ),
            )
            for lif in nfs_lifs
        ],
    }

    blockers = []
    if not live_configured:
        if legacy_env_configured:
            blockers.append(
                "NETAPP_CONFIGURED=true is a legacy/desired flag, but live NetApp validation has not verified configured state."
            )
        else:
            blockers.append("No live NetApp configured state exists yet; run Validate NetApp Setup.")
    if not netapp_credentials_present:
        blockers.append("NetApp API credentials are missing; values must stay in .env.local.real-lab when ready.")
    if not esxi_configured:
        blockers.append("ESXi management is not configured yet; NFS datastore mount validation is blocked.")
    if vcenter_in_scope and not vcenter_configured:
        blockers.append("vCenter/govc target is not configured yet; vCenter datastore validation is blocked.")
    if vcenter_in_scope and vcenter_configured and not vcenter_credentials_present:
        blockers.append("vCenter credentials are missing; values must stay in .env.local.real-lab when ready.")
    if vcenter_in_scope and vcenter_configured and not govc_available:
        blockers.append("govc is not installed or not on PATH; vCenter validation cannot run.")

    warnings = [
        "Only one NetApp management path is connected; this is acceptable for initial console/API bring-up but not full HA validation."
        if single_management_port
        else "Multiple NetApp management paths are listed as connected.",
        "NFS readiness is preview-only. No ONTAP, vCenter, ESXi, or storage apply action is run.",
    ]
    if not vcenter_in_scope:
        warnings.append("vCenter is disabled by the active lab profile; direct NetApp NFS readiness can still be validated.")
    if settings.netapp_storage_protocol.lower() != "nfs":
        warnings.append(f"NETAPP_STORAGE_PROTOCOL={settings.netapp_storage_protocol} is set; this readiness pass is for NFS.")

    payload = {
        "provider_id": PROVIDER_ID,
        "action": "nfs-vcenter-readiness",
        "checked_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "message": "NetApp NFS readiness generated. Preview only; no changes were made.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "ontap_apply_enabled": False,
        "vcenter_apply_enabled": False,
        "esxi_apply_enabled": False,
        "manual_env_flag_required": False,
        "live_state": netapp_live_state,
        "single_management_port_mode": single_management_port,
        "management_topology": {
            "connected_management_ports": connected_management_ports,
            "note": settings.netapp_management_topology_note,
            "initial_bringup_ok": True,
            "full_ha_validation_ready": not single_management_port,
        },
        "planned_nfs": {
            "storage_protocol": settings.netapp_storage_protocol,
            "svm_management_ip": settings.netapp_svm_mgmt_ip,
            "nfs_lifs": nfs_lifs,
            "volume": settings.netapp_nfs_volume,
            "export_policy": settings.netapp_nfs_export_policy,
            "mount_path": settings.netapp_nfs_mount_path,
            "datastore_name": settings.netapp_nfs_datastore_name,
            "client_match": settings.netapp_nfs_client_match,
        },
        "targets": {
            "netapp_cluster_mgmt_ip": settings.netapp_cluster_mgmt_ip,
            "netapp_configured_source": "live_verification" if live_configured else "not_verified",
            "legacy_netapp_configured_env": legacy_env_configured,
            "esxi_management_ip": settings.esxi_test_host,
            "vcenter_host_configured": bool(vcenter_in_scope and vcenter_target_host),
            "vcenter_management_ip": settings.vcenter_management_ip,
            "vcenter_configured": bool(vcenter_in_scope and settings.vcenter_configured),
            "govc_available": bool(vcenter_in_scope and govc_available),
        },
        "connectivity": connectivity,
        "plan_preview": {
            "ontap_steps": [
                "Confirm cluster management REST is reachable.",
                "Confirm or create the target SVM.",
                "Confirm or create NFS data LIFs on the connected data path.",
                "Enable or confirm NFS service on the SVM.",
                "Confirm or create the ESXi datastore volume.",
                "Confirm or create export policy and rule for the ESXi management/client network.",
            ],
            "vcenter_steps": (
                [
                    "Use govc after vCenter is reachable and credentials are configured.",
                    "Add or confirm the NFS datastore against the intended ESXi host or cluster.",
                    "Validate datastore visibility from ESXi/vCenter.",
                ]
                if vcenter_in_scope
                else ["vCenter datastore registration is not in scope for this direct NetApp setup."]
            ),
            "govc_preview": (
                (
                    "govc datastore.create -type nfs "
                    f"-name {settings.netapp_nfs_datastore_name} "
                    f"-remote-host {first_nfs_lif} "
                    f"-remote-path {settings.netapp_nfs_mount_path}"
                )
                if vcenter_in_scope
                else "not_in_scope"
            ),
            "esxi_fallback_preview": (
                "esxcli storage nfs add "
                f"-H {first_nfs_lif} "
                f"-s {settings.netapp_nfs_mount_path} "
                f"-v {settings.netapp_nfs_datastore_name}"
            ),
        },
        "artifacts": {
            "report": _rel(NFS_VCENTER_READINESS_REPORT),
            "json": _rel(NFS_VCENTER_READINESS_JSON),
        },
        "warnings": warnings,
        "blockers": blockers,
        "not_attempted": NOT_ATTEMPTED,
        "next_safe_action": (
            "Use console/API read-only discovery to identify the NetApp state, then resolve the listed NFS readiness blockers."
            if blockers
            else "Review the preview and keep apply disabled until an explicit NetApp NFS apply workflow is added."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(NFS_VCENTER_READINESS_JSON, sanitized)
        write_text_value(NFS_VCENTER_READINESS_REPORT, _nfs_vcenter_markdown(sanitized))
    return sanitized


def _run_console_probe(
    *,
    action: str,
    report_path: Path,
    json_path: Path,
    message: str,
    session: Session | None = None,
) -> dict[str, Any]:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    discovery_paths = (
        SerialConsoleDiscoveryPaths(by_id_glob="", usb_glob="", acm_glob="", ttys_glob="")
        if settings.netapp_console_autodiscovery_disabled
        else None
    )
    candidates = discover_serial_console_candidates(
        configured_hint=settings.netapp_console_port,
        paths=discovery_paths,
        collect_details=True,
        device_hint="netapp",
    )
    candidate_selection = _best_ranked_candidate(candidates)
    policy = current_lab_action_policy(settings.provider_mode)
    policy_blockers = policy.readonly_blockers() if settings.provider_mode in REAL_CONTACT_MODES else [
        "PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite is required before opening a real NetApp console."
    ]
    warnings = [
        "Only newline and carriage return wake bytes are allowed for this NetApp console probe.",
        "No NetApp credentials, commands, boot interrupts, or configuration actions are sent.",
        "Serial auto-discovery includes Linux /dev serial adapters and Windows COM ports.",
    ]
    if settings.netapp_console_port and not any(
        candidate.get("display_path") == settings.netapp_console_port for candidate in candidates
    ):
        warnings.append("Configured NETAPP_CONSOLE_PORT was treated as a hint but is not present in discovered candidates.")
    if len(settings.netapp_connected_management_ports) <= 1:
        warnings.append(settings.netapp_management_topology_note)

    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    blockers = list(policy_blockers)
    serial_import_error: str | None = None
    serial_module: Any | None = None
    if not policy_blockers:
        try:
            import serial  # type: ignore[import-untyped]

            serial_module = serial
        except ImportError:
            serial_import_error = "pyserial is not installed; real NetApp console workflow cannot open serial."
            blockers.append(serial_import_error)

    baud_rates = serial_baud_order(settings.netapp_console_baud)
    if not blockers and serial_module is not None:
        selectable = selectable_serial_candidates(candidates)
        if not selectable:
            if candidates:
                blockers.append(
                    "NetApp console candidates were found, but none were selectable. Fix device permissions or close the process using the adapter."
                )
            else:
                blockers.append(
                    "No OS-visible serial console candidates were found at /dev/serial/by-id/*, /dev/ttyUSB*, /dev/ttyACM*, or /dev/ttyS*."
                )
        probe_result = probe_serial_candidates(
            serial_module,
            candidates,
            options=SerialConsoleProbeOptions(
                configured_baud=settings.netapp_console_baud,
                timeout_seconds=settings.netapp_console_timeout_seconds,
                device_hint="netapp",
                max_candidates=NETAPP_MAX_PROBE_CANDIDATES,
                wake_sequences=NETAPP_SERIAL_WAKE_SEQUENCES,
            ),
        )
        attempts = list(probe_result["attempts"])
        probed_candidate_count = int(probe_result.get("probed_candidate_count") or 0)
        skipped_candidate_count = int(probe_result.get("skipped_candidate_count") or 0)
        prompt_attempt = _netapp_prompt_attempt(probe_result.get("selected"), attempts)
        if prompt_attempt:
            candidate = _candidate_for_attempt(candidates, prompt_attempt)
            selected = _selection_from_prompt_attempt(candidate, prompt_attempt)
    else:
        probed_candidate_count = 0
        skipped_candidate_count = 0

    if selected is None and candidate_selection is not None:
        selected = _selection_from_candidate(candidate_selection, attempts)

    prompt_selected = bool(selected and selected.get("prompt_state") in VALID_NETAPP_STATES)
    if prompt_selected:
        status = "ready"
        blockers = []
        message = f"{message} NetApp console produced {selected['prompt_label']}."
    else:
        status = "blocked"
        if not blockers:
            blockers.append(
                "Serial candidates were discovered, but no valid NetApp prompt, boot state, or login flow was detected."
            )

    payload = {
        "provider_id": PROVIDER_ID,
        "action": action,
        "checked_at": checked_at,
        "status": status,
        "message": (
            message
            if prompt_selected
            else "NetApp console autodiscovery selected a serial candidate, but no usable NetApp prompt/state was detected."
            if selected
            else "NetApp console discovery did not identify a usable serial candidate or prompt/state."
        ),
        "mode": settings.provider_mode,
        "configured_port_hint": settings.netapp_console_port,
        "configured_port_hint_role": "optional_hint_only",
        "autodiscovery_enabled": not settings.netapp_console_autodiscovery_disabled,
        "manual_env_update_required": False,
        "selected_port": selected["path"] if selected else None,
        "selected_baud": selected["baud"] if selected else None,
        "selected_prompt_state": selected["prompt_state"] if selected else None,
        "selected_prompt_label": selected["prompt_label"] if selected else None,
        "selection_source": selected["selection_source"] if selected else None,
        "selection_origin": _selection_origin(selected),
        "detected_automatically": _selection_origin(selected) == "autodiscovery",
        "selection_confidence": selected["confidence"] if selected else None,
        "selection_reason": selected["selection_reason"] if selected else None,
        "selected_device_type": selected["device_type"] if selected else None,
        "selected_classification": selected["classification"] if selected else None,
        "prompt_detected": prompt_selected,
        "candidate_count": len(candidates),
        "selectable_candidate_count": len(selectable_serial_candidates(candidates)),
        "probed_candidate_count": probed_candidate_count,
        "skipped_candidate_count": skipped_candidate_count,
        "candidate_counts": _candidate_counts(candidates),
        "candidates": candidates,
        "bauds_tried": list(baud_rates),
        "attempt_count": len(attempts),
        "attempts": attempts,
        "last_console_blocker": blockers[-1] if blockers else None,
        "serial_import_error": serial_import_error,
        "management_topology": {
            "connected_management_ports": list(settings.netapp_connected_management_ports),
            "note": settings.netapp_management_topology_note,
        },
        "artifacts": {"report": _rel(report_path), "json": _rel(json_path)},
        "warnings": warnings,
        "blockers": blockers,
        "not_attempted": NOT_ATTEMPTED,
        "next_safe_action": (
            "Use the selected console adapter/baud for read-only NetApp state capture."
            if prompt_selected
            else "Use the selected candidate as the next physical console check, then verify cable placement, adapter ownership, power state, and baud before rerunning discovery."
            if selected
            else "Check console cable, adapter ownership, backend device permissions, and baud, then rerun discovery."
        ),
    }
    sanitized = _sanitize(payload)
    runtime_state = update_netapp_runtime_state_from_console_probe(sanitized, session=session)
    sanitized["runtime_state"] = runtime_state
    _write_json(json_path, sanitized)
    write_text_value(report_path, _console_markdown(sanitized))
    return sanitized


def _identify_console_state(prompt_state: object) -> str:
    state = str(prompt_state or "").strip()
    if state == "existing_cluster_shell":
        return "ontap_shell"
    if state == "cluster_setup_prompt":
        return "cluster_setup_wizard"
    if state == "node_setup_prompt":
        return "node_setup_wizard"
    if state in {"login_required", "password_required"}:
        return "login_required"
    if state == "loader_prompt":
        return "loader"
    if state == "boot_menu":
        return "boot_menu"
    if state == "sp_bmc_login":
        return "sp_bmc_login"
    if state == "booting":
        return "booting"
    return "unknown"


def _netapp_console_credential_state() -> dict[str, Any]:
    console_username = os.getenv("NETAPP_CONSOLE_USERNAME")
    console_password = os.getenv("NETAPP_CONSOLE_PASSWORD")
    api_username = os.getenv("NETAPP_API_USERNAME")
    api_password = os.getenv("NETAPP_API_PASSWORD")
    username = console_username or api_username
    password = console_password or api_password
    return {
        "console_username_configured": bool(console_username),
        "console_password_configured": bool(console_password),
        "api_username_configured": bool(api_username),
        "api_password_configured": bool(api_password),
        "usable": bool(username and password),
        "_username": username,
        "_password": password,
    }


def _run_console_read_only_commands(
    port: str,
    baud: int,
    *,
    credentials: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        return [
            {
                "id": "serial",
                "command": None,
                "status": "blocked",
                "reason": "pyserial is not installed; console login/read-only commands cannot run.",
            }
        ]

    try:
        with serial.Serial(port=port, baudrate=baud, timeout=0.45, write_timeout=0.5) as conn:
            _safe_reset_input(conn)
            conn.write(b"\r\n")
            _safe_flush(conn)
            initial_text = _read_serial(conn, window=max(settings.netapp_console_timeout_seconds, 1.0))
            if credentials is not None:
                login_result = _complete_netapp_console_login(conn, initial_text, credentials)
                if login_result.get("status") != "ontap_shell":
                    return [login_result]
                initial_text = str(login_result.get("output_excerpt") or "")
            classification = _classify_netapp_console(initial_text)
            if classification["state"] != "existing_cluster_shell":
                return [
                    {
                        "id": "prompt",
                        "command": None,
                        "status": "blocked",
                        "prompt_state": classification["state"],
                        "reason": "ONTAP shell prompt was not detected; read-only ONTAP commands were skipped.",
                        "output_excerpt": _printable_excerpt(_redact_console_text(initial_text, credentials)),
                    }
                ]
            results: list[dict[str, Any]] = []
            for command_id, command in READ_ONLY_ONTAP_COMMANDS:
                conn.write(command.encode("utf-8") + b"\r")
                _safe_flush(conn)
                text = _read_serial(conn, window=3.0)
                prompt = _classify_netapp_console(text)
                results.append(
                    {
                        "id": command_id,
                        "command": command,
                        "status": "captured" if text else "no_output",
                        "prompt_state": prompt["state"],
                        "output_excerpt": _printable_excerpt(_redact_console_text(text, credentials), max_chars=1200),
                    }
                )
            return results
    except Exception as exc:  # pragma: no cover - hardware dependent
        return [
            {
                "id": "serial",
                "command": None,
                "status": "blocked",
                "reason": _serial_error_summary(exc),
            }
        ]


def _complete_netapp_console_login(
    conn: Any,
    initial_text: str,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    text = initial_text
    username = credentials.get("_username")
    password = credentials.get("_password")
    if not username or not password:
        return {
            "id": "login",
            "command": None,
            "status": "blocked",
            "reason": "NetApp console/API credentials are missing.",
        }
    lower = text.lower()
    transitions: list[str] = []
    if "username:" in lower or "login:" in lower:
        transitions.append("username_prompt_seen")
        conn.write(str(username).encode("utf-8") + b"\r")
        _safe_flush(conn)
        text += _read_serial(conn, window=1.5)
        lower = text.lower()
    if "password:" in lower:
        transitions.append("password_prompt_seen")
        conn.write(str(password).encode("utf-8") + b"\r")
        _safe_flush(conn)
        text += _read_serial(conn, window=2.5)
    conn.write(b"\r")
    _safe_flush(conn)
    text += _read_serial(conn, window=1.5)
    classification = _classify_netapp_console(text)
    return {
        "id": "login",
        "command": None,
        "status": "ontap_shell" if classification["state"] == "existing_cluster_shell" else "blocked",
        "prompt_state": classification["state"],
        "login_state_transitions": transitions,
        "reason": (
            "ONTAP shell prompt detected after guarded credential exchange."
            if classification["state"] == "existing_cluster_shell"
            else "Guarded credential exchange did not reach an ONTAP shell prompt."
        ),
        "output_excerpt": _printable_excerpt(_redact_console_text(text, credentials), max_chars=1200),
    }


def _redact_console_text(text: str, credentials: dict[str, Any] | None) -> str:
    redacted = text
    for key in ("_username", "_password"):
        value = credentials.get(key) if credentials else None
        if value:
            redacted = redacted.replace(str(value), "REDACTED")
    return redacted


def _console_login_next_action(
    identified_state: str,
    credentials: dict[str, Any],
    blockers: list[str],
    command_results: list[dict[str, Any]],
) -> str:
    if identified_state in {"cluster_setup_wizard", "node_setup_wizard"}:
        return "Build and review the setup plan; do not enter setup commands until a guarded apply workflow and explicit apply confirmations exist."
    if identified_state == "login_required" and not credentials.get("usable"):
        return "Configure NetApp console or API credentials locally, then rerun `make provider-lab-netapp-console-login-state`."
    if command_results and not blockers:
        return "Review the read-only ONTAP identity outputs and proceed to management reachability/setup planning."
    if identified_state == "ontap_shell" and not blockers:
        return "Review the read-only ONTAP identity outputs and proceed to management reachability/setup planning."
    return "Rerun console read-state after resolving the current console state blocker."


def _best_ranked_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    selectable = selectable_serial_candidates(candidates)
    if selectable:
        return selectable[0]
    existing = [candidate for candidate in candidates if candidate.get("exists")]
    return existing[0] if existing else (candidates[0] if candidates else None)


def _candidate_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    existing = [candidate for candidate in candidates if candidate.get("exists")]
    return {
        "total": len(candidates),
        "existing": len(existing),
        "selectable": len(selectable_serial_candidates(candidates)),
        "stable_existing": len([candidate for candidate in existing if candidate.get("stable_path")]),
        "usb_existing": len(
            [
                candidate
                for candidate in existing
                if candidate.get("path_type") in {"by-id", "ttyUSB", "ttyACM"}
            ]
        ),
        "ttys_existing": len([candidate for candidate in existing if candidate.get("path_type") == "ttyS"]),
        "in_use": len([candidate for candidate in existing if candidate.get("in_use")]),
        "inaccessible": len(
            [
                candidate
                for candidate in existing
                if not candidate.get("readable") or not candidate.get("writable")
            ]
        ),
    }


def _netapp_prompt_attempt(
    selected_attempt: object,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(selected_attempt, dict) and selected_attempt.get("prompt_state") in VALID_NETAPP_STATES:
        return selected_attempt
    return next(
        (
            attempt
            for attempt in attempts
            if attempt.get("prompt_state") in VALID_NETAPP_STATES
            and attempt.get("device_type") == "netapp"
        ),
        None,
    )


def _candidate_for_attempt(
    candidates: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> dict[str, Any] | None:
    path = attempt.get("path")
    if not isinstance(path, str):
        return None
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.get("display_path") == path or candidate.get("path") == path
        ),
        None,
    )


def _selection_from_prompt_attempt(
    candidate: dict[str, Any] | None,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    detail = attempt.get("classification_detail") if isinstance(attempt.get("classification_detail"), dict) else {}
    signals = detail.get("signals") if isinstance(detail.get("signals"), list) else []
    return {
        "path": str((candidate or {}).get("display_path") or attempt.get("path")),
        "baud": attempt.get("baud"),
        "prompt_state": attempt.get("prompt_state"),
        "prompt_label": attempt.get("prompt_label"),
        "selection_source": "prompt-evidence",
        "output_excerpt": attempt.get("output_excerpt") or "",
        "confidence": detail.get("confidence") or (candidate or {}).get("confidence") or "medium",
        "selection_reason": "; ".join(str(signal) for signal in signals)
        or _candidate_reason(candidate)
        or "NetApp prompt evidence matched this serial candidate.",
        "device_type": attempt.get("device_type"),
        "classification": attempt.get("classification"),
    }


def _selection_from_candidate(
    candidate: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    attempt = _best_attempt_for_candidate(candidate, attempts)
    return {
        "path": str(candidate.get("display_path") or candidate.get("path")),
        "baud": attempt.get("baud") if attempt else None,
        "prompt_state": attempt.get("prompt_state") if attempt else None,
        "prompt_label": attempt.get("prompt_label") if attempt else "Candidate selected by OS evidence",
        "selection_source": _selection_source_from_candidate(candidate),
        "output_excerpt": attempt.get("output_excerpt") if attempt else "",
        "confidence": candidate.get("confidence") or "low",
        "selection_reason": _candidate_reason(candidate)
        or "Highest-ranked selectable serial candidate from OS discovery.",
        "device_type": attempt.get("device_type") if attempt else None,
        "classification": attempt.get("classification") if attempt else None,
    }


def _best_attempt_for_candidate(
    candidate: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    path = str(candidate.get("display_path") or candidate.get("path") or "")
    matching = [attempt for attempt in attempts if attempt.get("path") == path]
    captured = [attempt for attempt in matching if attempt.get("captured")]
    return (captured or matching or [None])[0]


def _selection_source_from_candidate(candidate: dict[str, Any]) -> str:
    if settings.netapp_console_port and candidate.get("display_path") == settings.netapp_console_port:
        return "configured-port-hint"
    if candidate.get("stable_path"):
        return "auto-stable-candidate"
    if candidate.get("path_type") == "ttyS":
        return "auto-ttys-candidate"
    return "auto-fallback-candidate"


def _selection_origin(selected: dict[str, Any] | None) -> str:
    if not selected:
        return "none"
    path = selected.get("path")
    if settings.netapp_console_port and path == settings.netapp_console_port:
        return "hint"
    source = str(selected.get("selection_source") or "")
    if source == "configured-port-hint":
        return "hint"
    return "autodiscovery"


def _candidate_reason(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return ""
    reasons = candidate.get("selection_reasons")
    if isinstance(reasons, list) and reasons:
        return "; ".join(str(reason) for reason in reasons)
    return str(candidate.get("recommendation") or "")


def _discover_console_candidates() -> list[NetAppConsoleCandidate]:
    paths: list[str] = []
    if settings.netapp_console_port:
        paths.append(settings.netapp_console_port)
    for pattern in CONSOLE_GLOBS:
        paths.extend(_glob_strings(pattern))
    deduped = unique_preserving_order(paths)
    return [_candidate(path) for path in deduped]


def _glob_strings(pattern: str) -> list[str]:
    try:
        return glob.glob(pattern)
    except OSError:
        return []


def _candidate(path: str) -> NetAppConsoleCandidate:
    path_obj = Path(path)
    exists = path_exists(path_obj)
    stable_path = path.startswith("/dev/serial/by-id/")
    readable = os.access(path, os.R_OK) if exists else False
    writable = os.access(path, os.W_OK) if exists else False
    target_path = str(path_obj.resolve(strict=False)) if exists else None
    label = path_obj.name if path_obj.name else path
    in_use = _path_in_use(path) if exists else False
    rank = _candidate_rank(
        path=path,
        stable_path=stable_path,
        exists=exists,
        readable=readable,
        writable=writable,
        in_use=in_use,
    )
    return NetAppConsoleCandidate(
        path=path,
        stable_path=stable_path,
        exists=exists,
        readable=readable,
        writable=writable,
        label=label,
        target_path=target_path,
        in_use=in_use,
        rank=rank,
        recommendation=_candidate_recommendation(
            path=path,
            stable_path=stable_path,
            exists=exists,
            readable=readable,
            writable=writable,
            in_use=in_use,
        ),
    )


def _candidate_rank(
    *,
    path: str,
    stable_path: bool,
    exists: bool,
    readable: bool,
    writable: bool,
    in_use: bool,
) -> int:
    rank = 0
    if settings.netapp_console_port and path == settings.netapp_console_port:
        rank -= 1000
    if stable_path:
        rank -= 200
    if _name_has_usb_hint(path):
        rank -= 100
    if not exists:
        rank += 500
    if not readable or not writable:
        rank += 300
    if in_use:
        rank += 250
    return rank


def _rank_candidates(candidates: list[NetAppConsoleCandidate]) -> list[NetAppConsoleCandidate]:
    return sorted(candidates, key=lambda candidate: (candidate.rank, candidate.path))


def _candidate_recommendation(
    *,
    path: str,
    stable_path: bool,
    exists: bool,
    readable: bool,
    writable: bool,
    in_use: bool,
) -> str:
    if settings.netapp_console_port and path == settings.netapp_console_port:
        return "configured-port-hint"
    if not exists:
        return "missing"
    if not readable or not writable:
        return "permission-blocked"
    if in_use:
        return "in-use"
    if stable_path:
        return "preferred-stable-path"
    if _name_has_usb_hint(path):
        return "usb-serial-name-match"
    return "fallback-serial-candidate"


def _candidate_selectable(candidate: NetAppConsoleCandidate) -> bool:
    return bool(candidate.exists and candidate.readable and candidate.writable and not candidate.in_use)


def _selection_source(candidate: NetAppConsoleCandidate) -> str:
    if settings.netapp_console_port and candidate.path == settings.netapp_console_port:
        return "configured-port-hint"
    if candidate.stable_path:
        return "auto-stable-candidate"
    return "auto-fallback-candidate"


def _name_has_usb_hint(path: str) -> bool:
    lowered = path.lower()
    return any(hint.lower() in lowered for hint in USB_SERIAL_NAME_HINTS)


def _path_in_use(path: str) -> bool:
    for command in (["fuser", "-s", path], ["lsof", "-t", path]):
        executable = which(command[0])
        if executable is None:
            continue
        try:
            result = subprocess.run(
                [executable, *command[1:]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=1.0,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return True
    return False


def _baud_order(first_baud: int | None) -> tuple[int, ...]:
    values = [first_baud, *COMMON_NETAPP_CONSOLE_BAUDS] if first_baud else list(COMMON_NETAPP_CONSOLE_BAUDS)
    return tuple(unique_preserving_order(int(value) for value in values if value))


def _probe_candidate(serial_module: Any, candidate: NetAppConsoleCandidate, baud: int) -> dict[str, Any]:
    started_at = _now()
    try:
        with serial_module.Serial(
            port=candidate.path,
            baudrate=baud,
            timeout=0.35,
            write_timeout=0.5,
        ) as conn:
            _safe_reset_input(conn)
            conn.write(b"\r\n")
            _safe_flush(conn)
            text = _read_serial(conn, window=settings.netapp_console_timeout_seconds)
            classification = _classify_netapp_console(text)
            return {
                "path": candidate.path,
                "baud": baud,
                "started_at": started_at,
                "status": "ready" if classification["state"] in VALID_NETAPP_STATES else "unknown",
                "bytes": len(text.encode("utf-8", errors="replace")),
                "captured": bool(text),
                "prompt_state": classification["state"],
                "prompt_label": classification["label"],
                "output_excerpt": _printable_excerpt(text),
                "blocker": None
                if classification["state"] in VALID_NETAPP_STATES
                else "No valid NetApp prompt/state detected at this path and baud.",
            }
    except Exception as exc:  # pragma: no cover - hardware dependent
        return {
            "path": candidate.path,
            "baud": baud,
            "started_at": started_at,
            "status": "blocked",
            "bytes": 0,
            "captured": False,
            "prompt_state": _serial_error_state(exc),
            "prompt_label": _serial_error_label(exc),
            "output_excerpt": "",
            "blocker": _serial_error_summary(exc),
        }


def _safe_reset_input(conn: Any) -> None:
    try:
        conn.reset_input_buffer()
    except Exception:
        return


def _safe_flush(conn: Any) -> None:
    try:
        conn.flush()
    except Exception:
        return


def _read_serial(conn: Any, *, window: float) -> str:
    deadline = time.monotonic() + max(window, 0.25)
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        try:
            waiting = int(getattr(conn, "in_waiting", 0) or 0)
            chunk = conn.read(waiting or 1)
        except Exception:
            break
        if chunk:
            chunks.append(chunk)
            if sum(len(item) for item in chunks) >= 8192:
                break
        else:
            time.sleep(0.05)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _classify_netapp_console(text: str) -> dict[str, str]:
    if not text:
        return {"state": "no_output", "label": "No console output"}
    if text.count("\ufffd") > max(2, len(text) // 10):
        return {"state": "unreadable", "label": "Unreadable console text"}
    lower = text.lower()
    if re.search(r"(?im)(?:^|\n|\r)loader[-_a-z0-9]*>\s*$", text) or "loader>" in lower:
        return {"state": "loader_prompt", "label": "LOADER prompt"}
    if "boot menu" in lower or ("selection" in lower and "wipeconfig" in lower):
        return {"state": "boot_menu", "label": "Boot menu"}
    if "cluster setup" in lower or "initial configuration dialog" in lower:
        return {"state": "cluster_setup_prompt", "label": "Cluster setup prompt"}
    if "node setup" in lower or "node setup wizard" in lower:
        return {"state": "node_setup_prompt", "label": "Node setup wizard"}
    if re.search(r"(?m)[A-Za-z0-9_.:-]+::\*?>\s*$", text):
        return {"state": "existing_cluster_shell", "label": "Existing ONTAP cluster shell"}
    if "sp login" in lower or "bmc login" in lower:
        return {"state": "sp_bmc_login", "label": "SP/BMC login"}
    if "username:" in lower or "login:" in lower:
        return {"state": "login_required", "label": "Login prompt"}
    if "password:" in lower:
        return {"state": "password_required", "label": "Password prompt"}
    if "press ctrl-c" in lower or "booting" in lower or "starting ontap" in lower:
        return {"state": "booting", "label": "ONTAP booting"}
    return {"state": "unknown_output", "label": "Unclassified console output"}


def _printable_excerpt(text: str, *, max_chars: int = 1600) -> str:
    if not text:
        return ""
    printable = "".join(ch if ch in "\n\r\t" or 32 <= ord(ch) <= 126 else "." for ch in text)
    lines = [line.rstrip() for line in printable.replace("\r", "\n").splitlines()]
    compact = "\n".join(line for line in lines if line.strip())
    return compact[:max_chars]


def _serial_error_state(exc: Exception) -> str:
    message = str(exc).lower()
    if "permission" in message:
        return "permission_denied"
    if "resource busy" in message or "device or resource busy" in message:
        return "port_in_use"
    if "no such file" in message or "could not open port" in message:
        return "missing_port"
    return "serial_open_failed"


def _serial_error_label(exc: Exception) -> str:
    return {
        "permission_denied": "Permission denied",
        "port_in_use": "Port in use",
        "missing_port": "Missing serial port",
        "serial_open_failed": "Serial open failed",
    }[_serial_error_state(exc)]


def _serial_error_summary(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)[:180]}"


def _tcp_check(host: str | None, port: int, *, enabled: bool, disabled_reason: str) -> dict[str, Any]:
    if not host:
        return {
            "host": host,
            "port": port,
            "enabled": False,
            "reachable": None,
            "status": "missing-host",
            "reason": "Host is not configured.",
        }
    if not enabled:
        return {
            "host": host,
            "port": port,
            "enabled": False,
            "reachable": None,
            "status": "not-probed",
            "reason": disabled_reason,
        }
    try:
        with socket.create_connection((host, port), timeout=2.5):
            return {"host": host, "port": port, "enabled": True, "reachable": True, "status": "ready"}
    except OSError as exc:
        return {
            "host": host,
            "port": port,
            "enabled": True,
            "reachable": False,
            "status": "blocked",
            "reason": f"{exc.__class__.__name__}: {str(exc)[:140]}",
        }


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", cleaned)
    if "@" in cleaned:
        cleaned = cleaned.rsplit("@", 1)[-1]
    cleaned = cleaned.split("/", 1)[0]
    return cleaned.split(":", 1)[0] or None


def _tool_available(name: str) -> bool:
    return _tool_path(name) is not None


def _tool_path(name: str) -> Path | None:
    found = which(name)
    if found:
        return Path(found)
    for directory in (Path(sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        candidate = directory / name
        if is_file(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _latest_or_not_run(path: Path, *, action: str, message: str, next_safe_action: str) -> dict[str, Any]:
    payload = read_json_object(path)
    if payload:
        return payload
    return {
        "provider_id": PROVIDER_ID,
        "action": action,
        "checked_at": None,
        "status": "not_run",
        "message": message,
        "mode": settings.provider_mode,
        "configured_port_hint": settings.netapp_console_port,
        "selected_port": None,
        "selected_baud": None,
        "candidate_count": 0,
        "last_console_blocker": "No report has been generated yet.",
        "artifacts": {"report": _rel(_report_for_action(action))},
        "warnings": [],
        "blockers": [message],
        "next_safe_action": next_safe_action,
    }


def _report_for_action(action: str) -> Path:
    if action == "console-read-state":
        return CONSOLE_STATE_REPORT
    return CONSOLE_DISCOVERY_REPORT


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_object(path, payload, default=str)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value:
            continue
        if any(
            fragment in key.lower()
            for fragment in ("password", "token", "secret", "credential", "authorization", "cookie")
        ):
            values.append(value)
    return values


def _console_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp Console Discovery",
        "",
        f"Checked at: {payload['checked_at']}",
        f"Action: `{payload['action']}`",
        f"Status: `{payload['status']}`",
        f"Provider mode: `{payload['mode']}`",
        "",
        "## Selection",
        f"- Configured port hint: `{payload.get('configured_port_hint') or 'not set'}`",
        f"- Hint role: `{payload.get('configured_port_hint_role') or 'optional_hint_only'}`",
        f"- Autodiscovery enabled: `{payload.get('autodiscovery_enabled')}`",
        f"- Manual env update required: `{payload.get('manual_env_update_required')}`",
        f"- Selected port: `{payload.get('selected_port') or 'none'}`",
        f"- Selected baud: `{payload.get('selected_baud') or 'none'}`",
        f"- Prompt/state: `{payload.get('selected_prompt_label') or 'not detected'}`",
        f"- Prompt detected: `{payload.get('prompt_detected')}`",
        f"- Selection confidence: `{payload.get('selection_confidence') or 'none'}`",
        f"- Selection source: `{payload.get('selection_source') or 'none'}`",
        f"- Selection origin: `{payload.get('selection_origin') or 'none'}`",
        f"- Selection reason: {payload.get('selection_reason') or 'none'}",
        f"- Candidate count: `{payload.get('candidate_count', 0)}`",
        f"- Selectable candidates: `{payload.get('selectable_candidate_count', 0)}`",
        f"- Probed candidates: `{payload.get('probed_candidate_count', 0)}`",
        f"- Skipped candidates: `{payload.get('skipped_candidate_count', 0)}`",
        f"- Attempt count: `{payload.get('attempt_count', 0)}`",
        f"- Last console blocker: `{payload.get('last_console_blocker') or 'none'}`",
        "",
        "## Candidate Summary",
    ]
    candidates = payload.get("candidates") or []
    if candidates:
        for candidate in candidates[:40]:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                "- "
                f"`{candidate.get('display_path') or candidate.get('path')}` | "
                f"type=`{candidate.get('path_type')}` | exists=`{candidate.get('exists')}` | "
                f"rw=`{candidate.get('readable')}/{candidate.get('writable')}` | "
                f"in_use=`{candidate.get('in_use')}` | mtime=`{candidate.get('modified_time') or 'unknown'}` | "
                f"rank=`{candidate.get('rank')}` | confidence=`{candidate.get('confidence')}` | "
                f"reason={'; '.join(str(item) for item in candidate.get('selection_reasons', [])[:3])}"
            )
    else:
        lines.append("- No serial candidates were discovered.")
    lines.extend(
        [
            "",
            "## Management Topology",
            f"- Connected management ports: `{', '.join(payload.get('management_topology', {}).get('connected_management_ports', [])) or 'none listed'}`",
            f"- Note: {payload.get('management_topology', {}).get('note') or 'none'}",
            "",
            "## Attempts",
        ]
    )
    attempts = payload.get("attempts") or []
    if attempts:
        for attempt in attempts:
            lines.append(
                f"- `{attempt.get('path')}` @ `{attempt.get('baud')}`: "
                f"{attempt.get('prompt_label')} ({attempt.get('status')})"
            )
    else:
        lines.append("- No serial open/read attempts were made.")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers", []) or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings", []) or ["None"])
    lines.extend(["", "## Not Attempted"])
    lines.extend(f"- {item}" for item in payload.get("not_attempted", []))
    lines.append("")
    return "\n".join(lines)


def _console_login_markdown(payload: dict[str, Any]) -> str:
    credentials = payload.get("credential_state") or {}
    lines = [
        "# NetApp Console Login / Read-Only State",
        "",
        f"Checked at: {payload['checked_at']}",
        f"Status: `{payload['status']}`",
        f"Provider mode: `{payload['mode']}`",
        "",
        "## Current Console",
        f"- Selected port: `{payload.get('selected_port') or 'none'}`",
        f"- Selected baud: `{payload.get('selected_baud') or 'none'}`",
        f"- Prompt state: `{payload.get('prompt_state') or 'unknown'}`",
        f"- Initial identified state: `{payload.get('initial_identified_state') or payload.get('identified_state') or 'unknown'}`",
        f"- Identified state: `{payload.get('identified_state') or 'unknown'}`",
        "",
        "## Credential State",
        f"- NETAPP_CONSOLE_USERNAME: `{'configured' if credentials.get('console_username_configured') else 'missing'}`",
        f"- NETAPP_CONSOLE_PASSWORD: `{'configured' if credentials.get('console_password_configured') else 'missing'}`",
        f"- NETAPP_API_USERNAME: `{'configured' if credentials.get('api_username_configured') else 'missing'}`",
        f"- NETAPP_API_PASSWORD: `{'configured' if credentials.get('api_password_configured') else 'missing'}`",
        f"- Usable credential pair: `{bool(credentials.get('usable'))}`",
        "",
        "## Actions",
        f"- Guarded login attempted: `{payload.get('login_attempted')}`",
        f"- Read-only commands attempted: `{payload.get('read_only_commands_attempted')}`",
        "",
        "## Fixed Read-Only Command Set",
    ]
    for item in payload.get("read_only_commands") or []:
        lines.append(f"- `{item.get('id')}`: `{item.get('command')}`")
    lines.extend(["", "## Command Results"])
    results = payload.get("command_results") or []
    if results:
        for item in results:
            lines.append(
                f"- `{item.get('id')}` status=`{item.get('status')}` prompt=`{item.get('prompt_state') or 'none'}`"
            )
            if item.get("reason"):
                lines.append(f"  Reason: {item.get('reason')}")
    else:
        lines.append("- No console login or ONTAP shell read-only command was attempted.")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers", []) or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings", []) or ["None"])
    lines.extend(["", "## Not Attempted"])
    lines.extend(f"- {item}" for item in payload.get("not_attempted", []))
    lines.extend(["", "## Next Action", "", payload.get("next_safe_action") or "Review current console state."])
    lines.append("")
    return "\n".join(lines)


def _nfs_vcenter_markdown(payload: dict[str, Any]) -> str:
    nfs = payload["planned_nfs"]
    targets = payload["targets"]
    lines = [
        "# NetApp NFS / vCenter Readiness",
        "",
        f"Checked at: {payload['checked_at']}",
        f"Status: `{payload['status']}`",
        f"Provider mode: `{payload['mode']}`",
        f"Apply enabled: `{payload['apply_enabled']}`",
        "",
        "## Management Topology",
        f"- Single management port mode: `{payload['single_management_port_mode']}`",
        f"- Connected management ports: `{', '.join(payload['management_topology']['connected_management_ports']) or 'none listed'}`",
        f"- Note: {payload['management_topology']['note']}",
        "",
        "## Planned NFS",
        f"- SVM management IP: `{nfs['svm_management_ip']}`",
        f"- NFS LIFs: `{', '.join(nfs['nfs_lifs'])}`",
        f"- Volume: `{nfs['volume']}`",
        f"- Export policy: `{nfs['export_policy']}`",
        f"- Mount path: `{nfs['mount_path']}`",
        f"- Datastore: `{nfs['datastore_name']}`",
        f"- Client match: `{nfs['client_match']}`",
        "",
        "## Tool / Target State",
        f"- NetApp cluster management: `{targets['netapp_cluster_mgmt_ip']}`",
        f"- ESXi management: `{targets.get('esxi_management_ip') or 'not configured'}`",
        f"- vCenter configured: `{targets['vcenter_configured']}`",
        f"- govc available: `{targets['govc_available']}`",
        "",
        "## Preview Commands",
        f"- `{payload['plan_preview']['govc_preview']}`",
        f"- `{payload['plan_preview']['esxi_fallback_preview']}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers", []) or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings", []) or ["None"])
    lines.extend(["", "## Not Attempted"])
    lines.extend(f"- {item}" for item in payload.get("not_attempted", []))
    lines.append("")
    return "\n".join(lines)


def _rel(path: Path) -> str:
    return display_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()
