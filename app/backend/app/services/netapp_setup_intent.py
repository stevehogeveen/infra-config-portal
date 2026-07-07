from __future__ import annotations

import os
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import settings
from app.providers.action_policy import LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.env_utils import env_flag as _env_flag
from app.services.json_file_store import write_json_object, write_text_value
from app.services.lab_profiles import active_lab_profile_context
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.netapp_state import get_netapp_runtime_state, validate_netapp_setup
from app.services.path_utils import path_exists, repo_relative_path

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

BASELINE_REPORT = CODEX_RUN_DIR / "netapp-setup-upgrade-baseline-report.md"
SETUP_PLAN_REPORT = CODEX_RUN_DIR / "netapp-setup-plan-report.md"
SETUP_PREVIEW_REPORT = CODEX_RUN_DIR / "netapp-setup-preview-report.md"
SETUP_PREVIEW_JSON = CODEX_RUN_DIR / "netapp-setup-preview-redacted.json"
SETUP_APPLY_REPORT = CODEX_RUN_DIR / "netapp-cluster-setup-apply-report.md"
SETUP_APPLY_JSON = CODEX_RUN_DIR / "netapp-cluster-setup-apply-redacted.json"
POST_SETUP_VALIDATION_REPORT = CODEX_RUN_DIR / "netapp-post-setup-validation-report.md"
POST_SETUP_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-post-setup-validation-redacted.json"

SETUP_CONFIRM_PHRASE = "APPLY NETAPP CLUSTER SETUP"
SETUP_SUPPORTED_STATES = {"cluster_setup_wizard", "node_setup_wizard"}
DEFAULT_CLUSTER_NAME = "lab-netapp-cluster"
DEFAULT_NODE_A_NAME = "lab-netapp-node-a"
DEFAULT_NODE_B_NAME = "lab-netapp-node-b"
DEFAULT_SVM_NAME = "esxi_svm"
DEFAULT_SEARCH_DOMAIN = "lab.local"
SETUP_ENV_FIELDS = {
    "cluster_name": ("NETAPP_CLUSTER_NAME", DEFAULT_CLUSTER_NAME),
    "node_a_name": ("NETAPP_NODE_A_NAME", DEFAULT_NODE_A_NAME),
    "node_b_name": ("NETAPP_NODE_B_NAME", DEFAULT_NODE_B_NAME),
    "svm_name": ("NETAPP_SVM_NAME", DEFAULT_SVM_NAME),
    "dns_servers": ("NETAPP_DNS_SERVERS", "active profile DNS or lab gateway"),
    "ntp_servers": ("NETAPP_NTP_SERVERS", "active profile NTP or control host"),
    "search_domains": ("NETAPP_SEARCH_DOMAINS", DEFAULT_SEARCH_DOMAIN),
    "admin_access_source": ("NETAPP_ADMIN_ACCESS_SOURCE", ".env.local.real-lab NetApp admin access reference"),
}


def get_netapp_setup_intent() -> dict[str, Any]:
    if not _netapp_in_scope():
        return _not_in_scope_payload("setup-intent")
    access_state = _admin_access_state()
    profile_defaults = _active_profile_setup_defaults()
    intent = {
        "cluster_name": settings.netapp_cluster_name or DEFAULT_CLUSTER_NAME,
        "node_a_name": settings.netapp_node_a_name or DEFAULT_NODE_A_NAME,
        "node_b_name": settings.netapp_node_b_name or DEFAULT_NODE_B_NAME,
        "cluster_mgmt_ip": settings.netapp_cluster_mgmt_ip,
        "node_a_mgmt_ip": settings.netapp_node_a_mgmt_ip,
        "node_b_mgmt_ip": settings.netapp_node_b_mgmt_ip,
        "svm_name": settings.netapp_svm_name or DEFAULT_SVM_NAME,
        "svm_mgmt_ip": settings.netapp_svm_mgmt_ip,
        "nfs_lifs": list(settings.netapp_nfs_lifs),
        "nfs_volume": settings.netapp_nfs_volume,
        "nfs_mount_path": settings.netapp_nfs_mount_path,
        "export_policy": settings.netapp_nfs_export_policy,
        "export_client_match": settings.netapp_nfs_client_match,
        "dns_servers": _list_or_default(settings.netapp_dns_servers, profile_defaults["dns_servers"]),
        "ntp_servers": _list_or_default(settings.netapp_ntp_servers, profile_defaults["ntp_servers"]),
        "search_domains": _list_or_default(settings.netapp_search_domains, profile_defaults["search_domains"]),
        "admin_access_source": access_state["source"],
        "admin_access_configured": access_state["configured"],
        "admin_access_redacted": True,
    }
    missing = _missing_setup_fields(intent)
    return {
        "provider_id": PROVIDER_ID,
        "intent": intent,
        "complete": not missing,
        "missing_fields": missing,
        "remediation_items": [_remediation_item(field) for field in missing],
    }


def build_netapp_setup_baseline(*, run_address_scan: bool = False, write_report: bool = True) -> dict[str, Any]:
    if not _netapp_in_scope():
        payload = _not_in_scope_payload("setup-upgrade-baseline", report_path=BASELINE_REPORT)
        if write_report:
            CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
            write_text_value(BASELINE_REPORT, _baseline_markdown(payload))
        return payload
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    detected_state = _detected_setup_state(runtime_state)
    address_scan = scan_planned_netapp_addresses(enabled=run_address_scan)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "setup-upgrade-baseline",
        "checked_at": checked_at,
        "status": "ready" if detected_state in SETUP_SUPPORTED_STATES and _scan_is_free(address_scan) else "blocked",
        "message": "NetApp setup/upgrade baseline generated with redacted local evidence.",
        "mode": settings.provider_mode,
        "detected_state": detected_state,
        "console": _console_summary(runtime_state),
        "planned_targets": _planned_targets(),
        "address_conflict_scan": address_scan,
        "latest_reports_read": _existing_reports(
            [
                "artifacts/codex-runs/netapp-console-current-report.md",
                "artifacts/codex-runs/netapp-console-state-report.md",
                "artifacts/codex-runs/netapp-management-network-scan-report.md",
                "artifacts/codex-runs/netapp-setup-plan-report.md",
                "artifacts/codex-runs/netapp-live-state-report.md",
                "artifacts/codex-runs/netapp-real-bringup-final-report.md",
            ]
        ),
        "blockers": _baseline_blockers(detected_state, address_scan),
        "warnings": [
            "Historical reports are evidence only; this baseline records the latest runtime cache and optional fresh address scan.",
            "No NetApp setup, storage, upgrade, reboot, wipe, or apply command was run.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {"report": _rel(BASELINE_REPORT)},
        "next_safe_action": "Run `make provider-lab-netapp-setup-preview` and review missing setup intent fields before any apply attempt.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        write_text_value(BASELINE_REPORT, _baseline_markdown(sanitized))
    return sanitized


def build_netapp_setup_plan(*, run_address_scan: bool = False, write_report: bool = True) -> dict[str, Any]:
    return _build_setup_preview(
        action="setup-plan",
        report_path=SETUP_PLAN_REPORT,
        run_address_scan=run_address_scan,
        write_report=write_report,
    )


def build_netapp_setup_preview(*, run_address_scan: bool = False, write_report: bool = True) -> dict[str, Any]:
    return _build_setup_preview(
        action="setup-preview",
        report_path=SETUP_PREVIEW_REPORT,
        json_path=SETUP_PREVIEW_JSON,
        run_address_scan=run_address_scan,
        write_report=write_report,
    )


def apply_netapp_setup(*, write_report: bool = True) -> dict[str, Any]:
    if not _netapp_in_scope():
        payload = _not_in_scope_payload(
            "setup-apply",
            report_path=SETUP_APPLY_REPORT,
            json_path=SETUP_APPLY_JSON,
        )
        if write_report:
            _write_report_payload(SETUP_APPLY_JSON, SETUP_APPLY_REPORT, payload, _setup_apply_markdown)
        return payload
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    detected_state = _detected_setup_state(runtime_state)
    intent = get_netapp_setup_intent()
    address_scan = scan_planned_netapp_addresses(enabled=True)
    gates = _setup_apply_gates(detected_state, intent, address_scan)
    blocked = bool(gates["blockers"])
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "setup-apply",
        "checked_at": checked_at,
        "status": "blocked" if blocked else "ready_to_apply",
        "message": (
            "NetApp setup apply was refused before any console or ONTAP write command."
            if blocked
            else "NetApp setup apply gates passed. The interactive setup executor is intentionally not auto-started by tests or preview runs."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": not blocked,
        "detected_state": detected_state,
        "required_flags": _setup_required_flags(),
        "flag_state": gates["flag_state"],
        "intent": intent["intent"],
        "missing_fields": intent["missing_fields"],
        "remediation_items": intent["remediation_items"],
        "address_conflict_scan": address_scan,
        "before": {
            "detected_state": detected_state,
            "console": _console_summary(runtime_state),
            "report": runtime_state.get("last_report_path"),
        },
        "apply": {
            "serial_writes_attempted": False,
            "ontap_writes_attempted": False,
            "transcript_summary": [
                "No transcript was captured because apply gates did not start an interactive setup session."
                if blocked
                else "Apply gates passed, but this workflow requires a human-started guarded console executor before commands are sent.",
            ],
            "expected_stop_conditions": [
                "unexpected prompt or boot menu",
                "prompt not classified as cluster setup wizard or node setup wizard",
                "address scan conflict",
                "missing setup intent field",
                "missing exact confirmation phrase",
            ],
        },
        "after": {
            "post_setup_validation_run": False,
            "validation_report": _rel(POST_SETUP_VALIDATION_REPORT),
        },
        "blockers": gates["blockers"],
        "warnings": [
            "No secrets are printed or written to the apply report.",
            "Run post-setup validation only after a guarded setup session completes.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(SETUP_APPLY_REPORT),
            "json": _rel(SETUP_APPLY_JSON),
        },
        "next_safe_action": (
            "Set missing intent values and required flags, then rerun `make provider-lab-netapp-setup-apply`."
            if blocked
            else "Start the guarded console executor only from an attended real-lab session, then run post-setup validation."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_report_payload(SETUP_APPLY_JSON, SETUP_APPLY_REPORT, sanitized, _setup_apply_markdown)
    return sanitized


def run_netapp_post_setup_validation(*, write_report: bool = True) -> dict[str, Any]:
    if not _netapp_in_scope():
        payload = _not_in_scope_payload(
            "post-setup-validation",
            report_path=POST_SETUP_VALIDATION_REPORT,
            json_path=POST_SETUP_VALIDATION_JSON,
        )
        if write_report:
            _write_report_payload(
                POST_SETUP_VALIDATION_JSON,
                POST_SETUP_VALIDATION_REPORT,
                payload,
                _post_setup_validation_markdown,
            )
        return payload
    validation = validate_netapp_setup(check_ports=True, write_report=True)
    payload = {
        **validation,
        "action": "post-setup-validation",
        "artifacts": {
            **(validation.get("artifacts") if isinstance(validation.get("artifacts"), dict) else {}),
            "report": _rel(POST_SETUP_VALIDATION_REPORT),
            "json": _rel(POST_SETUP_VALIDATION_JSON),
        },
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_report_payload(
            POST_SETUP_VALIDATION_JSON,
            POST_SETUP_VALIDATION_REPORT,
            sanitized,
            _post_setup_validation_markdown,
        )
    return sanitized


def scan_planned_netapp_addresses(*, enabled: bool) -> dict[str, Any]:
    if not _netapp_in_scope():
        return {
            "status": "not_in_scope",
            "checked_at": None,
            "required_before_apply": False,
            "targets": [],
            "results": [],
            "free": False,
            "conflicts": [],
            "message": "NetApp is disabled by the active lab profile.",
            "recheck_command": "make provider-lab-validation",
        }
    checked_at = _now()
    targets = _address_targets()
    if not enabled:
        return {
            "status": "not_checked",
            "checked_at": None,
            "required_before_apply": True,
            "targets": targets,
            "results": [],
            "free": False,
            "conflicts": [],
            "message": "Address conflict scan was not run for this read-only API preview.",
            "recheck_command": "make provider-lab-netapp-setup-preview",
        }
    results = [_probe_address(target) for target in targets]
    conflicts = [item for item in results if item["classification"] == "in_use_or_conflict"]
    return {
        "status": "ready" if not conflicts else "blocked",
        "checked_at": checked_at,
        "required_before_apply": True,
        "targets": targets,
        "results": results,
        "free": not conflicts,
        "conflicts": conflicts,
        "message": (
            "All planned NetApp addresses had no ICMP/TCP response during this scan."
            if not conflicts
            else "One or more planned NetApp addresses responded and must not be assigned."
        ),
        "recheck_command": "make provider-lab-netapp-setup-preview",
    }


def _build_setup_preview(
    *,
    action: str,
    report_path: Path,
    run_address_scan: bool,
    write_report: bool,
    json_path: Path | None = None,
) -> dict[str, Any]:
    if not _netapp_in_scope():
        payload = _not_in_scope_payload(action, report_path=report_path, json_path=json_path)
        if write_report:
            _write_report_payload(json_path, report_path, payload, _setup_preview_markdown)
        return payload
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    detected_state = _detected_setup_state(runtime_state)
    intent = get_netapp_setup_intent()
    address_scan = scan_planned_netapp_addresses(enabled=run_address_scan)
    blockers = _preview_blockers(detected_state, intent, address_scan)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": action,
        "checked_at": checked_at,
        "status": "blocked" if blockers else "preview_only",
        "message": "NetApp setup preview generated. No setup/apply command was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "detected_state": detected_state,
        "console": _console_summary(runtime_state),
        "setup_intent": intent["intent"],
        "missing_fields": intent["missing_fields"],
        "remediation_items": intent["remediation_items"],
        "address_conflict_scan": address_scan,
        "wizard_api_path_options": _wizard_api_path_options(detected_state),
        "exact_changes": _setup_changes(intent["intent"]),
        "apply_command": _setup_apply_command(),
        "required_flags": _setup_required_flags(),
        "pre_apply_requirements": [
            "Rerun address conflict scan immediately before apply.",
            "Console prompt must still classify as cluster_setup_wizard or node_setup_wizard.",
            "All setup intent fields must be configured in .env.local.real-lab.",
            "Required apply flags and exact confirmation phrase must be present.",
        ],
        "blockers": blockers,
        "warnings": [
            "Preview only. No NetApp setup, storage, ONTAP API write, reboot, wipe, or upgrade command was run.",
            "Admin access values are represented only as configured/missing/redacted state.",
        ],
        "not_attempted": _not_attempted(),
        "artifacts": {"report": _rel(report_path), **({"json": _rel(json_path)} if json_path else {})},
        "next_safe_action": (
            "Resolve missing fields and rerun preview; apply remains blocked until flags and a fresh conflict scan pass."
            if blockers
            else "Review the preview and only run setup apply from an attended real-lab session with explicit flags."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_report_payload(json_path, report_path, sanitized, _setup_preview_markdown)
    return sanitized


def _missing_setup_fields(intent: dict[str, Any]) -> list[str]:
    fields = [
        "cluster_name",
        "node_a_name",
        "node_b_name",
        "svm_name",
        "dns_servers",
        "ntp_servers",
        "search_domains",
        "admin_access_source",
    ]
    missing = []
    for field in fields:
        value = intent.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    if not intent.get("admin_access_configured"):
        if "admin_access_source" not in missing:
            missing.append("admin_access_source")
    return missing


def _remediation_item(field: str) -> dict[str, Any]:
    env_name, suggested = SETUP_ENV_FIELDS.get(field, (field.upper(), None))
    return {
        "field_name": field,
        "where_to_set": f".env.local.real-lab: {env_name}",
        "suggested_value": suggested,
        "recheck_command": "make provider-lab-netapp-setup-preview",
    }


def _admin_access_state() -> dict[str, Any]:
    configured = bool(
        (os.getenv("NETAPP_CONSOLE_USERNAME") and os.getenv("NETAPP_CONSOLE_PASSWORD"))
        or (settings.netapp_api_username and settings.netapp_api_password)
    )
    return {
        "configured": configured,
        "source": settings.netapp_admin_access_source
        or ("redacted .env.local.real-lab reference" if configured else None),
    }


def _active_profile_setup_defaults() -> dict[str, list[str]]:
    context = active_lab_profile_context()
    active = context.get("active_profile") if isinstance(context.get("active_profile"), dict) else {}
    global_settings = active.get("global_settings") if isinstance(active.get("global_settings"), dict) else {}
    address_plan = (
        context.get("resolved_address_plan")
        if isinstance(context.get("resolved_address_plan"), dict)
        else active.get("resolved_address_plan")
        if isinstance(active.get("resolved_address_plan"), dict)
        else active.get("address_plan")
        if isinstance(active.get("address_plan"), dict)
        else {}
    )

    dns_servers = _string_list(global_settings.get("dns_servers"))
    if not dns_servers:
        gateway = _clean_string(global_settings.get("gateway") or active.get("gateway") or os.getenv("LAB_GATEWAY"))
        dns_servers = [gateway] if gateway else []

    ntp_servers = _string_list(global_settings.get("ntp_servers"))
    if not ntp_servers:
        control_host = _clean_string(address_plan.get("ansible_control_host") or os.getenv("ANSIBLE_CONTROL_HOST"))
        ntp_servers = [control_host] if control_host else []

    search_domain = _clean_string(
        global_settings.get("domain_name")
        or os.getenv("LAB_SEARCH_DOMAIN")
        or os.getenv("LAB_DOMAIN_NAME")
        or os.getenv("CISCO_DOMAIN_NAME")
        or DEFAULT_SEARCH_DOMAIN
    )
    return {
        "dns_servers": dns_servers,
        "ntp_servers": ntp_servers,
        "search_domains": [search_domain] if search_domain else [],
    }


def _list_or_default(values: tuple[str, ...] | list[str], default: list[str]) -> list[str]:
    cleaned = _string_list(values)
    return cleaned if cleaned else list(default)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        return []
    return _unique([item for item in (_clean_string(candidate) for candidate in candidates) if item])


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _setup_apply_gates(
    detected_state: str,
    intent: dict[str, Any],
    address_scan: dict[str, Any],
) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "netapp_setup_apply": _env_flag("NETAPP_SETUP_APPLY"),
        "netapp_setup_confirm": os.getenv("NETAPP_SETUP_CONFIRM") == SETUP_CONFIRM_PHRASE,
        "netapp_setup_allow_cluster_create": _env_flag("NETAPP_SETUP_ALLOW_CLUSTER_CREATE"),
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
    }
    blockers = []
    blockers.extend(unique_strings(policy.action_blockers("netapp.initial-setup", "storage_config")))
    if detected_state not in SETUP_SUPPORTED_STATES:
        blockers.append(f"Console state is `{detected_state}`; setup apply only supports cluster/node setup wizard states.")
    if intent["missing_fields"]:
        blockers.append("NetApp setup intent has missing required fields.")
    if address_scan.get("free") is not True:
        blockers.append("Fresh pre-apply address conflict scan did not prove planned addresses are free.")
    if not flag_state["netapp_setup_apply"]:
        blockers.append("NETAPP_SETUP_APPLY=true is required.")
    if not flag_state["netapp_setup_confirm"]:
        blockers.append(f'NETAPP_SETUP_CONFIRM="{SETUP_CONFIRM_PHRASE}" is required.')
    if not flag_state["netapp_setup_allow_cluster_create"]:
        blockers.append("NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true is required.")
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _preview_blockers(
    detected_state: str,
    intent: dict[str, Any],
    address_scan: dict[str, Any],
) -> list[str]:
    blockers = []
    if detected_state not in SETUP_SUPPORTED_STATES:
        blockers.append(f"Detected state `{detected_state}` is not a supported setup wizard state.")
    if intent["missing_fields"]:
        blockers.append("Required NetApp setup intent fields are missing.")
    if address_scan.get("status") == "blocked":
        blockers.append("Planned address conflict scan found at least one in-use address.")
    return blockers


def _baseline_blockers(detected_state: str, address_scan: dict[str, Any]) -> list[str]:
    blockers = []
    if detected_state not in SETUP_SUPPORTED_STATES:
        blockers.append(f"Console is `{detected_state}`, not cluster_setup_wizard.")
    if address_scan.get("status") == "blocked":
        blockers.append("Planned address conflict scan found at least one in-use address.")
    if address_scan.get("status") == "not_checked":
        blockers.append("Planned address conflict scan was not run.")
    return blockers


def _detected_setup_state(runtime_state: dict[str, Any]) -> str:
    console = runtime_state.get("console") if isinstance(runtime_state.get("console"), dict) else {}
    prompt_state = str(console.get("prompt_state") or "")
    configured_state = str(runtime_state.get("configured_state") or "")
    if prompt_state == "cluster_setup_prompt" or configured_state == "setup_wizard":
        return "cluster_setup_wizard"
    if prompt_state == "node_setup_prompt":
        return "node_setup_wizard"
    if prompt_state == "existing_cluster_shell" or configured_state in {"ontap_detected", "configured"}:
        return "ontap_shell"
    if prompt_state in {"login_required", "password_required"}:
        return "login_required"
    return configured_state or "unknown"


def _planned_targets() -> dict[str, Any]:
    return {
        "lab_subnet": settings.lab_subnet_cidr,
        "controller_a_sp": settings.netapp_controller_a_sp,
        "controller_b_sp": settings.netapp_controller_b_sp,
        "cluster_mgmt": settings.netapp_cluster_mgmt_ip,
        "node_a_mgmt": settings.netapp_node_a_mgmt_ip,
        "node_b_mgmt": settings.netapp_node_b_mgmt_ip,
        "svm_mgmt": settings.netapp_svm_mgmt_ip,
        "nfs_lifs": list(settings.netapp_nfs_lifs),
        "future_iscsi_lifs": list(settings.netapp_iscsi_lifs),
    }


def _address_targets() -> list[dict[str, str]]:
    rows = [
        ("controller_a_sp", "Controller A SP", settings.netapp_controller_a_sp),
        ("controller_b_sp", "Controller B SP", settings.netapp_controller_b_sp),
        ("cluster_mgmt", "Cluster management", settings.netapp_cluster_mgmt_ip),
        ("node_a_mgmt", "Node A management", settings.netapp_node_a_mgmt_ip),
        ("node_b_mgmt", "Node B management", settings.netapp_node_b_mgmt_ip),
        ("svm_mgmt", "SVM management", settings.netapp_svm_mgmt_ip),
    ]
    rows.extend((f"nfs_lif_{index}", f"NFS LIF {index}", ip) for index, ip in enumerate(settings.netapp_nfs_lifs, start=1))
    return [{"id": item_id, "label": label, "address": address} for item_id, label, address in rows if address]


def _probe_address(target: dict[str, str]) -> dict[str, Any]:
    address = target["address"]
    ping_ok = _ping(address)
    tcp_443 = _tcp(address, 443)
    tcp_22 = _tcp(address, 22)
    neighbor = _neighbor_state(address)
    in_use = ping_ok or tcp_443 or tcp_22 or neighbor in {"REACHABLE", "STALE", "DELAY", "PROBE"}
    return {
        **target,
        "ping": "reply" if ping_ok else "no_reply",
        "tcp_443": "open" if tcp_443 else "closed",
        "tcp_22": "open" if tcp_22 else "closed",
        "neighbor_state": neighbor or "not_present",
        "classification": "in_use_or_conflict" if in_use else "unused_free",
    }


def _ping(address: str) -> bool:
    if which("ping") is None:
        return False
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _tcp(address: str, port: int) -> bool:
    try:
        with socket.create_connection((address, port), timeout=1.0):
            return True
    except OSError:
        return False


def _neighbor_state(address: str) -> str | None:
    if which("ip") is None:
        return None
    try:
        result = subprocess.run(
            ["ip", "neigh", "show", address],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip()
    for state in ("REACHABLE", "STALE", "DELAY", "PROBE", "FAILED", "INCOMPLETE"):
        if state in text:
            return state
    return None


def _console_summary(runtime_state: dict[str, Any]) -> dict[str, Any]:
    console = runtime_state.get("console") if isinstance(runtime_state.get("console"), dict) else {}
    return {
        "selected_port": console.get("discovered_port"),
        "selected_baud": console.get("baud") or settings.netapp_console_baud,
        "prompt_state": console.get("prompt_state"),
        "prompt_label": console.get("prompt_label"),
        "source": console.get("source"),
        "confidence": console.get("confidence"),
        "checked_at": console.get("last_seen") or runtime_state.get("checked_at"),
    }


def _wizard_api_path_options(detected_state: str) -> list[dict[str, Any]]:
    return [
        {
            "path": "console_wizard",
            "available": detected_state in SETUP_SUPPORTED_STATES,
            "description": "Use the serial console setup wizard for initial cluster creation.",
            "status": "supported_when_gated",
        },
        {
            "path": "ontap_rest_after_cluster_mgmt",
            "available": False,
            "description": "Use ONTAP REST only after cluster management exists and safe GET validation succeeds.",
            "status": "blocked_until_cluster_management",
        },
        {
            "path": "ssh_cli_after_cluster_mgmt",
            "available": False,
            "description": "Use fixed ONTAP CLI commands only after SSH/access validation and approval.",
            "status": "blocked_until_cluster_management",
        },
    ]


def _setup_changes(intent: dict[str, Any]) -> list[dict[str, Any]]:
    services_value = (
        f"DNS {', '.join(intent.get('dns_servers') or []) or 'missing'}; "
        f"NTP {', '.join(intent.get('ntp_servers') or []) or 'missing'}; "
        f"search {', '.join(intent.get('search_domains') or []) or 'missing'}"
    )
    return [
        {"area": "cluster", "change": "Create or join cluster", "value": intent.get("cluster_name")},
        {"area": "cluster_mgmt", "change": "Assign cluster management IP", "value": intent.get("cluster_mgmt_ip")},
        {"area": "node_a", "change": "Assign node A name and management IP", "value": f"{intent.get('node_a_name') or 'missing'} / {intent.get('node_a_mgmt_ip')}"},
        {"area": "node_b", "change": "Assign node B name and management IP", "value": f"{intent.get('node_b_name') or 'missing'} / {intent.get('node_b_mgmt_ip')}"},
        {"area": "svm", "change": "Create SVM and management LIF", "value": f"{intent.get('svm_name') or 'missing'} / {intent.get('svm_mgmt_ip')}"},
        {"area": "nfs", "change": "Create NFS LIFs", "value": ", ".join(intent.get("nfs_lifs") or [])},
        {"area": "nfs", "change": "Create datastore volume/export", "value": f"{intent.get('nfs_volume')} at {intent.get('nfs_mount_path')}"},
        {"area": "services", "change": "Configure DNS, NTP, and search domains", "value": services_value},
    ]


def _setup_apply_command() -> str:
    return (
        'NETAPP_SETUP_APPLY=true NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP" '
        "NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true PROVIDER_MODE=local-lab-readwrite "
        "make provider-lab-netapp-setup-apply"
    )


def _setup_required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "NETAPP_SETUP_APPLY=true",
        f'NETAPP_SETUP_CONFIRM="{SETUP_CONFIRM_PHRASE}"',
        "NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true",
    ]


def _scan_is_free(address_scan: dict[str, Any]) -> bool:
    return bool(address_scan.get("free"))


def _existing_reports(paths: list[str]) -> list[str]:
    existing: list[str] = []
    for path in paths:
        if path_exists(REPO_ROOT / path):
            existing.append(path)
    return existing


def _not_attempted() -> list[str]:
    return [
        "cluster setup wizard answers",
        "ONTAP API write",
        "SSH/CLI configuration command",
        "SVM, LIF, volume, export, datastore, or iSCSI creation",
        "controller reboot, takeover/giveback, wipe, or ONTAP upgrade",
    ]


def _write_report_payload(
    json_path: Path | None,
    report_path: Path,
    payload: dict[str, Any],
    markdown_builder: Any,
) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    if json_path is not None:
        write_json_object(json_path, payload)
    write_text_value(report_path, markdown_builder(payload))


def _netapp_in_scope() -> bool:
    features = active_lab_profile_context().get("enabled_features") or {}
    return bool(features.get("netapp_enabled"))


def _not_in_scope_payload(
    action: str,
    *,
    report_path: Path | None = None,
    json_path: Path | None = None,
) -> dict[str, Any]:
    checked_at = _now()
    artifacts = {}
    if report_path is not None:
        artifacts["report"] = _rel(report_path)
    if json_path is not None:
        artifacts["json"] = _rel(json_path)
    return {
        "provider_id": PROVIDER_ID,
        "action": action,
        "checked_at": checked_at,
        "status": "not_in_scope",
        "message": "NetApp is disabled by the active lab profile.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "detected_state": "not_in_scope",
        "console": {},
        "setup_intent": {},
        "complete": True,
        "missing_fields": [],
        "remediation_items": [],
        "planned_targets": {},
        "address_conflict_scan": {
            "status": "not_in_scope",
            "checked_at": None,
            "required_before_apply": False,
            "targets": [],
            "results": [],
            "free": False,
            "conflicts": [],
            "message": "NetApp is disabled by the active lab profile.",
        },
        "exact_changes": [],
        "apply": {
            "serial_writes_attempted": False,
            "ontap_writes_attempted": False,
            "transcript_summary": ["NetApp is not in scope for the active lab profile."],
        },
        "required_flags": [],
        "blockers": [],
        "warnings": ["NetApp is not in scope for the active lab profile; this is not a blocker."],
        "not_attempted": _not_attempted(),
        "artifacts": artifacts,
        "next_safe_action": "Enable NetApp in the active lab profile when this workflow is intentionally in scope.",
    }


def _baseline_markdown(payload: dict[str, Any]) -> str:
    scan = payload.get("address_conflict_scan") if isinstance(payload.get("address_conflict_scan"), dict) else {}
    lines = [
        "# NetApp Setup + Upgrade Baseline Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Provider mode: `{payload.get('mode')}`",
        f"- Detected state: `{payload.get('detected_state')}`",
        f"- Address scan: `{scan.get('status')}` free=`{scan.get('free')}`",
        "- Setup/apply commands run: `no`",
        "- Upgrade/apply commands run: `no`",
        "",
        "## Console",
    ]
    for key, value in (payload.get("console") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Planned Address Scan", "", "| Role | Address | Classification |", "| --- | --- | --- |"])
    for result in scan.get("results") or []:
        lines.append(f"| `{result.get('label')}` | `{result.get('address')}` | `{result.get('classification')}` |")
    lines.extend(["", "## Reports Read"])
    lines.extend(f"- `{path}`" for path in payload.get("latest_reports_read") or ["none"])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- No secrets are written to this report.", "- Historical artifacts are evidence only."])
    return "\n".join(lines) + "\n"


def _setup_preview_markdown(payload: dict[str, Any]) -> str:
    intent = payload.get("setup_intent") if isinstance(payload.get("setup_intent"), dict) else {}
    scan = payload.get("address_conflict_scan") if isinstance(payload.get("address_conflict_scan"), dict) else {}
    lines = [
        "# NetApp Setup Preview Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Detected state: `{payload.get('detected_state')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Apply command: `{payload.get('apply_command')}`",
        "",
        "## Setup Intent",
    ]
    for key, value in intent.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Remediation Items"])
    for item in payload.get("remediation_items") or []:
        lines.append(
            f"- `{item.get('field_name')}`: set `{item.get('where_to_set')}`"
            + (f" suggested `{item.get('suggested_value')}`" if item.get("suggested_value") else "")
            + f"; recheck `{item.get('recheck_command')}`"
        )
    if not payload.get("remediation_items"):
        lines.append("- None")
    lines.extend(["", "## Address Conflict Scan"])
    lines.append(f"- Status: `{scan.get('status')}` free=`{scan.get('free')}`")
    for result in scan.get("results") or []:
        lines.append(f"- `{result.get('label')}` `{result.get('address')}`: `{result.get('classification')}`")
    lines.extend(["", "## Exact Changes"])
    lines.extend(f"- {item.get('area')}: {item.get('change')} -> `{item.get('value')}`" for item in payload.get("exact_changes") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- Preview only; no NetApp setup/apply/upgrade command was run.", "- Secrets are represented only as configured/missing/redacted state."])
    return "\n".join(lines) + "\n"


def _setup_apply_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp Cluster Setup Apply Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Detected state: `{payload.get('detected_state')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "- Serial writes attempted: `False`",
        "- ONTAP writes attempted: `False`",
        "",
        "## Required Flags",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Missing Setup Intent Fields"])
    lines.extend(f"- `{item}`" for item in payload.get("missing_fields") or ["None"])
    lines.extend(["", "## Remediation Items"])
    for item in payload.get("remediation_items") or []:
        lines.append(
            f"- `{item.get('field_name')}`: set `{item.get('where_to_set')}`"
            + (f" suggested `{item.get('suggested_value')}`" if item.get("suggested_value") else "")
            + f"; recheck `{item.get('recheck_command')}`"
        )
    if not payload.get("remediation_items"):
        lines.append("- None")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Transcript Summary"])
    apply_section = payload.get("apply") if isinstance(payload.get("apply"), dict) else {}
    lines.extend(f"- {item}" for item in apply_section.get("transcript_summary") or ["No transcript."])
    lines.extend(["", "## Safety", "- No secrets are written to this report."])
    return "\n".join(lines) + "\n"


def _post_setup_validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp Post-Setup Validation Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Configured: `{payload.get('configured')}`",
        f"- Configured state: `{payload.get('configured_state')}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- Validation uses read-only checks and writes redacted reports only."])
    return "\n".join(lines) + "\n"


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for key, value in os.environ.items()
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie"))
    ]


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unique(values: list[str]) -> list[str]:
    return unique_preserving_order(values)
