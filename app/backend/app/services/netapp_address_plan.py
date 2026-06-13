from __future__ import annotations

import json
import os
import re
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import (
    ActionCategory,
    LOCAL_LAB_READWRITE_MODE,
    REAL_CONTACT_MODES,
    current_lab_action_policy,
)
from app.providers.redaction import redact_sensitive
from app.services.netapp_real_lab import run_netapp_console_login_state
from app.services.netapp_setup_intent import scan_planned_netapp_addresses
from app.services.netapp_state import get_netapp_runtime_state

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

CONSOLE_LOGIN_STATE_JSON = CODEX_RUN_DIR / "netapp-console-login-state-redacted.json"
ADDRESS_PLAN_REPORT = CODEX_RUN_DIR / "netapp-address-remediation-plan-report.md"
ADDRESS_PLAN_JSON = CODEX_RUN_DIR / "netapp-address-remediation-plan-redacted.json"
ADDRESS_PREVIEW_REPORT = CODEX_RUN_DIR / "netapp-address-remediation-preview-report.md"
ADDRESS_PREVIEW_JSON = CODEX_RUN_DIR / "netapp-address-remediation-preview-redacted.json"
ADDRESS_APPLY_REPORT = CODEX_RUN_DIR / "netapp-address-remediation-apply-report.md"
ADDRESS_APPLY_JSON = CODEX_RUN_DIR / "netapp-address-remediation-apply-redacted.json"
ADDRESS_VALIDATION_REPORT = CODEX_RUN_DIR / "netapp-address-remediation-validation-report.md"
ADDRESS_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-address-remediation-validation-redacted.json"
HA_NODE_REPORT = CODEX_RUN_DIR / "netapp-ha-node-remediation-report.md"
HA_NODE_JSON = CODEX_RUN_DIR / "netapp-ha-node-remediation-redacted.json"

ADDRESS_CONFIRM_PHRASE = "APPLY NETAPP ADDRESS REMEDIATION"
ADDRESS_DEFAULT_NETMASK = "255.255.255.0"


def build_netapp_address_remediation_plan(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    console_facts = latest_console_network_facts()
    current = console_facts["current_targets"]
    planned = _planned_targets()
    comparisons = _address_comparisons(current, planned)
    reachability = _reachability_snapshot(current, planned)
    blockers = _blockers(console_facts, comparisons, reachability)
    warnings = [
        "Read-only plan only. No ONTAP network modify, route, SVM, LIF, export, datastore, reboot, takeover, giveback, wipe, or upgrade command was run.",
        "Readdressing an existing ONTAP cluster is a separate attended workflow from first-time setup wizard apply.",
    ]
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "address-remediation-plan",
        "checked_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "message": "NetApp address remediation plan generated from redacted console read-only evidence.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_cached",
        "freshness": "current" if console_facts["checked_at"] else "not_checked",
        "runtime_state": {
            "configured": bool(runtime_state.get("configured")),
            "configured_state": runtime_state.get("configured_state"),
            "source": runtime_state.get("source"),
        },
        "console_facts": console_facts,
        "planned_targets": planned,
        "current_targets": current,
        "address_comparisons": comparisons,
        "reachability": reachability,
        "operator_paths": _operator_paths(comparisons, console_facts),
        "required_before_apply": [
            "Fresh console login/read-only state showing node health and LIF layout.",
            "Cluster management REST or SSH reachable from this host.",
            "Node health and cluster HA warnings resolved.",
            "Explicit choice to readdress ONTAP to the lab profile or update the lab profile to the existing ONTAP network.",
            "Attended change window and exact guarded confirmation flags for any future write lane.",
        ],
        "blockers": blockers,
        "warnings": warnings,
        "not_attempted": [
            "ONTAP network interface modify",
            "route create or modify",
            "broadcast-domain, port, failover-group, SVM, NFS, volume, export, or datastore writes",
            "controller reboot, takeover, giveback, wipe, or upgrade",
        ],
        "artifacts": {
            "report": _rel(ADDRESS_PLAN_REPORT),
            "json": _rel(ADDRESS_PLAN_JSON),
            "console_login_state": _rel(CONSOLE_LOGIN_STATE_JSON),
        },
        "next_safe_action": _next_safe_action(blockers, comparisons),
    }
    sanitized = _sanitize(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        ADDRESS_PLAN_JSON.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        ADDRESS_PLAN_REPORT.write_text(_address_plan_markdown(sanitized), encoding="utf-8")
    return sanitized


def build_netapp_address_remediation_preview(*, write_report: bool = True) -> dict[str, Any]:
    plan = build_netapp_address_remediation_plan(write_report=False)
    address_scan = scan_planned_netapp_addresses(enabled=True)
    command_plan = _address_command_plan(plan)
    blockers = _address_preview_blockers(plan, address_scan, command_plan)
    payload = {
        **plan,
        "action": "address-remediation-preview",
        "checked_at": _now(),
        "status": "blocked" if blockers else "preview_only",
        "message": "NetApp address remediation preview generated. No ONTAP network command was sent.",
        "apply_enabled": False,
        "method": _selected_readdress_method(plan),
        "address_conflict_scan": address_scan,
        "command_plan": command_plan,
        "required_flags": _address_required_flags(command_plan),
        "pre_apply_requirements": [
            "Refresh console login/read-only state immediately before apply.",
            "Validate target 192.168.1.x addresses are free immediately before apply.",
            "Use the selected console method while REST/SSH are unreachable.",
            "Acknowledge the current HA/node warning if it is still present.",
            "Use exact confirmation flags; do not run from mock or local-readonly mode.",
        ],
        "blockers": blockers,
        "warnings": _unique(
            list(plan.get("warnings") or [])
            + [
                "Preview only. No ONTAP LIF, route, SVM, NFS, export, reboot, wipe, takeover, giveback, or upgrade command was sent.",
                "Existing LIF modifies and missing LIF creates are separated so the operator can see the blast radius before apply.",
            ]
        ),
        "not_attempted": [
            "ONTAP network interface modify",
            "ONTAP network interface create",
            "route create or modify",
            "SVM, NFS service, volume, export, or datastore writes",
            "controller reboot, takeover, giveback, wipe, or upgrade",
        ],
        "artifacts": {
            "report": _rel(ADDRESS_PREVIEW_REPORT),
            "json": _rel(ADDRESS_PREVIEW_JSON),
            "plan_report": _rel(ADDRESS_PLAN_REPORT),
            "console_login_state": _rel(CONSOLE_LOGIN_STATE_JSON),
        },
        "next_safe_action": (
            "Resolve preview blockers, then run the guarded address apply only from an attended real-lab session."
            if blockers
            else "Review the command plan, then run guarded address apply with explicit flags."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(ADDRESS_PREVIEW_JSON, ADDRESS_PREVIEW_REPORT, sanitized, _address_preview_markdown)
    return sanitized


def apply_netapp_address_remediation(*, write_report: bool = True) -> dict[str, Any]:
    preview = build_netapp_address_remediation_preview(write_report=True)
    gates = _address_apply_gates(preview)
    blocked = bool(gates["blockers"])
    command_plan = preview.get("command_plan") if isinstance(preview.get("command_plan"), dict) else {}
    commands = _enabled_commands(command_plan)
    apply_result: dict[str, Any] = {
        "console_writes_attempted": False,
        "commands_attempted": [],
        "readback_attempted": False,
        "status": "not_started",
        "message": "Apply gates blocked before any ONTAP network command was sent.",
    }
    status = "blocked"
    if not blocked:
        console_context = _console_context()
        readback_commands = list(command_plan.get("readback_commands") or [])
        console_result = _run_console_commands(
            port=str(console_context.get("selected_port") or ""),
            baud=int(console_context.get("selected_baud") or settings.netapp_console_baud),
            username=str(console_context.get("username") or ""),
            password=str(console_context.get("password") or ""),
            commands=commands + readback_commands,
            command_seconds=8.0,
        )
        output = str(console_result.get("output_excerpt") or "")
        failed = (not console_result.get("ok")) or bool(re.search(r"\n(?:Error|Warning):", output))
        status = "failed" if failed else "applied"
        apply_result = {
            "console_writes_attempted": True,
            "commands_attempted": _redacted_commands(commands),
            "readback_attempted": bool(readback_commands),
            "readback_commands": _redacted_commands(readback_commands),
            "status": status,
            "message": str(console_result.get("error") or ("ONTAP console returned an error or warning." if failed else "ONTAP address commands completed.")),
            "console_result": {
                "ok": bool(console_result.get("ok")),
                "error": console_result.get("error"),
                "output_excerpt": console_result.get("output_excerpt"),
                "checked_at": console_result.get("checked_at"),
            },
        }
    payload = {
        **preview,
        "action": "address-remediation-apply",
        "checked_at": _now(),
        "status": status,
        "message": apply_result["message"],
        "apply_enabled": not blocked,
        "flag_state": gates["flag_state"],
        "required_flags": _address_required_flags(command_plan),
        "apply": apply_result,
        "blockers": gates["blockers"],
        "warnings": _unique(
            [
                "No secrets are written to this report.",
                "Run address validation after any applied console readdress.",
            ]
            + list(preview.get("warnings") or [])
        ),
        "artifacts": {
            "report": _rel(ADDRESS_APPLY_REPORT),
            "json": _rel(ADDRESS_APPLY_JSON),
            "preview_report": _rel(ADDRESS_PREVIEW_REPORT),
        },
        "next_safe_action": (
            "Resolve apply blockers and rerun preview before any address apply attempt."
            if blocked
            else "Run `make provider-lab-netapp-address-validate` and then refresh live status."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(ADDRESS_APPLY_JSON, ADDRESS_APPLY_REPORT, sanitized, _address_apply_markdown)
    return sanitized


def validate_netapp_address_remediation(*, write_report: bool = True) -> dict[str, Any]:
    console_state = run_netapp_console_login_state()
    plan = build_netapp_address_remediation_plan(write_report=True)
    comparisons = list(plan.get("address_comparisons") or [])
    target_checks = _target_validation_checks(plan)
    blockers = []
    for item in comparisons:
        if item.get("status") != "match":
            blockers.append(f"{item.get('label')} is `{item.get('status')}`: current `{item.get('current') or 'unknown'}` expected `{item.get('planned') or 'not planned'}`.")
    for check in target_checks:
        if check.get("expected_reachable") and not check.get("reachable"):
            blockers.append(f"{check.get('label')} `{check.get('address')}` is not reachable on expected ports.")
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "address-remediation-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp address remediation validation completed from fresh console and reachability evidence.",
        "mode": settings.provider_mode,
        "source_type": "live_probe",
        "freshness": "live",
        "apply_enabled": False,
        "console_state": {
            "status": console_state.get("status"),
            "identified_state": console_state.get("identified_state"),
            "checked_at": console_state.get("checked_at"),
        },
        "address_comparisons": comparisons,
        "target_checks": target_checks,
        "blockers": _unique(blockers),
        "warnings": list(plan.get("warnings") or []),
        "artifacts": {
            "report": _rel(ADDRESS_VALIDATION_REPORT),
            "json": _rel(ADDRESS_VALIDATION_JSON),
            "plan_report": _rel(ADDRESS_PLAN_REPORT),
            "console_login_state": _rel(CONSOLE_LOGIN_STATE_JSON),
        },
        "next_safe_action": (
            "Rerun address preview/apply or choose the factory-reset/setup path if address validation remains blocked."
            if blockers
            else "Proceed to NetApp NFS setup and ESXi datastore validation."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(ADDRESS_VALIDATION_JSON, ADDRESS_VALIDATION_REPORT, sanitized, _address_validation_markdown)
    return sanitized


def diagnose_netapp_ha_node_warning(*, write_report: bool = True) -> dict[str, Any]:
    plan = build_netapp_address_remediation_plan(write_report=True)
    console_context = _console_context()
    diagnostic_commands = [
        "cluster show",
        "cluster ha show",
        "storage failover show",
        "system health alert show",
        "network interface show -fields vserver,lif,address,role,home-node,home-port,status-admin,status-oper",
        "network port show",
    ]
    console_result = _run_console_commands(
        port=str(console_context.get("selected_port") or ""),
        baud=int(console_context.get("selected_baud") or settings.netapp_console_baud),
        username=str(console_context.get("username") or ""),
        password=str(console_context.get("password") or ""),
        commands=diagnostic_commands,
        command_seconds=8.0,
    )
    facts = plan.get("console_facts") if isinstance(plan.get("console_facts"), dict) else {}
    health = facts.get("node_health") if isinstance(facts.get("node_health"), dict) else {}
    unhealthy_nodes = list(health.get("unhealthy_nodes") or [])
    blocks_address = any(item.get("id") == "node_a_mgmt" and item.get("status") != "match" for item in plan.get("address_comparisons") or [])
    blockers = []
    if unhealthy_nodes:
        blockers.append(f"NetApp node health is not clean: {', '.join(unhealthy_nodes)}.")
    if facts.get("cluster_ha_warning"):
        blockers.append("Cluster HA warning is present in fresh console output.")
    if blocks_address:
        blockers.append("Node A management readdress remains blocked by the X20-01/vifmgr health issue.")
    if not console_result.get("ok"):
        blockers.append(f"HA diagnostic console command run failed: {console_result.get('error') or 'unknown error'}.")
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "ha-node-remediation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp HA/node diagnostic completed with read-only console commands.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "node_health": health,
        "cluster_ha_warning": bool(facts.get("cluster_ha_warning")),
        "blocks_address_remediation": blocks_address,
        "blocks_nfs_setup": bool(facts.get("cluster_ha_warning") or unhealthy_nodes),
        "diagnostic_commands": diagnostic_commands,
        "diagnostic_result": {
            "ok": bool(console_result.get("ok")),
            "error": console_result.get("error"),
            "output_excerpt": console_result.get("output_excerpt"),
            "checked_at": console_result.get("checked_at"),
        },
        "safe_app_remediation": {
            "available": False,
            "reason": (
                "Cluster HA is already configured true and X20-01 is unhealthy; the app should not run takeover/giveback, reboot, wipe, or node repair automatically."
                if blockers
                else "No HA/node remediation is currently required."
            ),
        },
        "operator_action": {
            "problem": "X20-01 is unhealthy and ONTAP cannot reach vifmgr on X20-01 cluster LIF 169.254.203.198.",
            "where_to_fix": "NetApp console or physical controller/interconnect path for X20-01.",
            "recommended_action": "Restore X20-01 node and cluster-interconnect health, then rerun NetApp address apply for X20-01_mgmt1 and address validation.",
            "copyable_command": "make provider-lab-netapp-ha-node-diagnose",
            "recheck_command": "make provider-lab-netapp-address-validate",
        },
        "blockers": _unique(blockers),
        "warnings": [
            "Read-only diagnostic only. No takeover, giveback, reboot, wipe, HA modify, network modify, storage, or upgrade command was sent.",
            "The app exposes this as a specific HA/node issue so Lab Validation and NetApp Control Center do not collapse it into generic NetApp failure.",
        ],
        "artifacts": {
            "report": _rel(HA_NODE_REPORT),
            "json": _rel(HA_NODE_JSON),
            "address_validation": _rel(ADDRESS_VALIDATION_REPORT),
        },
        "next_safe_action": "Repair X20-01 health or cluster interconnect/vifmgr reachability, then rerun guarded address apply and validation.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(HA_NODE_JSON, HA_NODE_REPORT, sanitized, _ha_node_markdown)
    return sanitized


def latest_console_network_facts() -> dict[str, Any]:
    try:
        payload = json.loads(CONSOLE_LOGIN_STATE_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return _empty_console_facts("NetApp console login/read-only state has not run yet.")
    if not isinstance(payload, dict):
        return _empty_console_facts("NetApp console login/read-only state payload is invalid.")

    network_text = _command_excerpt(payload, "network_interface_summary")
    cluster_text = _command_excerpt(payload, "cluster_status")
    node_text = _command_excerpt(payload, "node_identity")
    current = _parse_network_interface_summary(network_text)
    node_health = _parse_node_health(cluster_text or node_text)
    ha_warning = "Cluster HA is not working correctly" in f"{cluster_text}\n{node_text}"
    blockers = []
    if not network_text:
        blockers.append("Console read-only network interface summary is missing.")
    if not current["cluster_mgmt"]:
        blockers.append("Current cluster management address was not found in console output.")
    return {
        "checked_at": payload.get("checked_at"),
        "identified_state": payload.get("identified_state"),
        "source": "console_read_only" if payload.get("checked_at") else "not_available",
        "command_ids": [
            item.get("id")
            for item in payload.get("command_results") or []
            if isinstance(item, dict) and item.get("id")
        ],
        "current_targets": current,
        "node_health": node_health,
        "cluster_ha_warning": ha_warning,
        "blockers": blockers,
    }


def _planned_targets() -> dict[str, Any]:
    return {
        "cluster_mgmt": settings.netapp_cluster_mgmt_ip,
        "node_a_mgmt": settings.netapp_node_a_mgmt_ip,
        "node_b_mgmt": settings.netapp_node_b_mgmt_ip,
        "svm_mgmt": settings.netapp_svm_mgmt_ip,
        "nfs_lifs": list(settings.netapp_nfs_lifs),
        "storage_protocol": settings.netapp_storage_protocol,
        "nfs_volume": settings.netapp_nfs_volume,
        "nfs_mount_path": settings.netapp_nfs_mount_path,
        "nfs_export_policy": settings.netapp_nfs_export_policy,
        "nfs_client_match": settings.netapp_nfs_client_match,
    }


def _parse_network_interface_summary(text: str) -> dict[str, Any]:
    rows = _interface_rows(text)
    cluster_mgmt = None
    node_mgmt: dict[str, str] = {}
    node_mgmt_lifs_by_node: dict[str, str] = {}
    data_lifs: list[dict[str, str]] = []
    cluster_lifs: list[dict[str, str]] = []
    for row in rows:
        role = row["role"]
        if role == "cluster-mgmt":
            cluster_mgmt = row["address"]
        elif role == "node-mgmt":
            node_mgmt[row["home_node"]] = row["address"]
            node_mgmt_lifs_by_node[row["home_node"]] = row["lif"]
        elif role == "data":
            data_lifs.append(row)
        elif role == "cluster":
            cluster_lifs.append(row)
    node_keys = sorted(node_mgmt)
    svm_mgmt_lif = _svm_mgmt_lif(data_lifs)
    nfs_data_lifs = [
        row
        for row in data_lifs
        if row is not svm_mgmt_lif and "mgmt" not in str(row.get("lif") or "").lower()
    ]
    return {
        "cluster_mgmt": cluster_mgmt,
        "node_a_mgmt": node_mgmt.get(node_keys[0]) if node_keys else None,
        "node_b_mgmt": node_mgmt.get(node_keys[1]) if len(node_keys) > 1 else None,
        "node_mgmt_by_node": node_mgmt,
        "node_mgmt_lifs_by_node": node_mgmt_lifs_by_node,
        "svm_mgmt": svm_mgmt_lif.get("address") if svm_mgmt_lif else None,
        "svm_mgmt_lif": svm_mgmt_lif,
        "data_lifs": nfs_data_lifs,
        "nfs_lifs": [row["address"] for row in nfs_data_lifs],
        "cluster_lifs": cluster_lifs,
        "source": "console_read_only" if text else "not_available",
    }


def _interface_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pending_prefix = ""
    pending_lif = ""
    pending_role = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith(("network interface show", "vserver ", "-------", "Press ")):
            continue
        ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line)
        if not ip_match:
            parts = line.split()
            if len(parts) >= 3 and parts[0] not in {"X20::>", "Warning:"}:
                pending_prefix = parts[0]
                pending_lif = parts[1]
                pending_role = parts[2]
            elif len(parts) == 1 and parts[0] not in {"X20::>", "Warning:"}:
                pending_prefix = parts[0]
                pending_lif = ""
                pending_role = ""
            elif len(parts) >= 2 and parts[0] not in {"X20::>", "Warning:"}:
                pending_prefix = parts[0]
                pending_lif = parts[1]
                pending_role = ""
            continue
        prefix = line[: ip_match.start()].split()
        suffix = line[ip_match.end() :].split()
        if len(prefix) >= 3:
            vserver, lif, role = prefix[0], prefix[1], prefix[2]
        elif pending_prefix and pending_lif and pending_role:
            vserver, lif, role = pending_prefix, pending_lif, pending_role
        elif pending_prefix and not pending_lif and len(prefix) >= 2:
            vserver, lif, role = pending_prefix, prefix[0], prefix[1]
        elif pending_prefix and pending_lif and prefix:
            vserver, lif, role = pending_prefix, pending_lif, prefix[0]
        else:
            continue
        rows.append(
            {
                "vserver": vserver,
                "lif": lif,
                "role": role,
                "address": ip_match.group(0),
                "home_node": suffix[0] if len(suffix) > 0 else "",
                "home_port": suffix[1] if len(suffix) > 1 else "",
                "status_oper": suffix[2] if len(suffix) > 2 else "",
            }
        )
        pending_prefix = ""
        pending_lif = ""
        pending_role = ""
    return rows


def _svm_mgmt_lif(data_lifs: list[dict[str, str]]) -> dict[str, str] | None:
    for row in data_lifs:
        lif = str(row.get("lif") or "").lower()
        if "mgmt" in lif or row.get("address") == settings.netapp_svm_mgmt_ip:
            return row
    return None


def _parse_node_health(text: str) -> dict[str, Any]:
    nodes: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s+(true|false)\s+(?:true|false)\s*$", line)
        if match:
            nodes[match.group(1)] = match.group(2)
    unhealthy = [node for node, health in nodes.items() if health != "true"]
    return {
        "nodes": nodes,
        "unhealthy_nodes": unhealthy,
        "all_healthy": bool(nodes) and not unhealthy,
    }


def _address_comparisons(current: dict[str, Any], planned: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        _comparison("cluster_mgmt", "Cluster management", current.get("cluster_mgmt"), planned.get("cluster_mgmt")),
        _comparison("node_a_mgmt", "Node A management", current.get("node_a_mgmt"), planned.get("node_a_mgmt")),
        _comparison("node_b_mgmt", "Node B management", current.get("node_b_mgmt"), planned.get("node_b_mgmt")),
        _comparison("svm_mgmt", "SVM management", current.get("svm_mgmt"), planned.get("svm_mgmt")),
    ]
    current_lifs = list(current.get("nfs_lifs") or [])
    planned_lifs = list(planned.get("nfs_lifs") or [])
    max_lifs = max(len(current_lifs), len(planned_lifs))
    rows.extend(
        _comparison(
            f"nfs_lif_{index + 1}",
            f"NFS LIF {index + 1}",
            current_lifs[index] if index < len(current_lifs) else None,
            planned_lifs[index] if index < len(planned_lifs) else None,
        )
        for index in range(max_lifs)
    )
    return rows


def _comparison(item_id: str, label: str, current: Any, planned: Any) -> dict[str, Any]:
    status = "match" if current and planned and str(current) == str(planned) else "missing_current" if not current else "missing_planned" if not planned else "mismatch"
    return {
        "id": item_id,
        "label": label,
        "current": current,
        "planned": planned,
        "status": status,
        "recommended_action": (
            "No address change needed."
            if status == "match"
            else "Choose readdress or lab-profile update before any storage apply."
        ),
    }


def _reachability_snapshot(current: dict[str, Any], planned: dict[str, Any]) -> dict[str, Any]:
    enabled = settings.provider_mode in REAL_CONTACT_MODES
    targets = [
        ("current_cluster_mgmt", current.get("cluster_mgmt")),
        ("planned_cluster_mgmt", planned.get("cluster_mgmt")),
    ]
    return {
        "enabled": enabled,
        "checks": [
            {
                "id": item_id,
                "address": address,
                "tcp_443": _tcp(address, 443, enabled),
                "tcp_22": _tcp(address, 22, enabled),
            }
            for item_id, address in targets
            if address
        ],
    }


def _blockers(
    console_facts: dict[str, Any],
    comparisons: list[dict[str, Any]],
    reachability: dict[str, Any],
) -> list[str]:
    blockers = list(console_facts.get("blockers") or [])
    if console_facts.get("identified_state") != "ontap_shell":
        blockers.append("NetApp console is not at an ONTAP shell; rerun guarded console login/read-only state.")
    if any(item["status"] == "mismatch" for item in comparisons):
        blockers.append("Discovered NetApp management/NFS addresses do not match the active lab profile.")
    if any(item["status"] == "missing_current" for item in comparisons if item["id"] != "svm_mgmt"):
        blockers.append("One or more current NetApp management/NFS addresses could not be read from console output.")
    health = console_facts.get("node_health") if isinstance(console_facts.get("node_health"), dict) else {}
    if health.get("unhealthy_nodes"):
        blockers.append(f"NetApp node health is not clean: {', '.join(health['unhealthy_nodes'])}.")
    if console_facts.get("cluster_ha_warning"):
        blockers.append("NetApp cluster HA warning is present in console output.")
    reachable_cluster = any(
        check.get("id") == "current_cluster_mgmt" and (check.get("tcp_443") is True or check.get("tcp_22") is True)
        for check in reachability.get("checks") or []
    )
    if not reachable_cluster:
        blockers.append("Current NetApp cluster management is not reachable from this host on TCP 443 or 22.")
    return _unique(blockers)


def _operator_paths(comparisons: list[dict[str, Any]], console_facts: dict[str, Any]) -> list[dict[str, Any]]:
    mismatch_count = len([item for item in comparisons if item["status"] in {"mismatch", "missing_current"}])
    return [
        {
            "id": "update_lab_profile_to_existing_netapp",
            "label": "Use discovered ONTAP network",
            "status": "blocked_until_host_routing" if mismatch_count else "not_needed",
            "summary": "Update the app/lab profile to the current ONTAP addresses only if this host can route to that network.",
            "next_action": "Make current cluster management reachable, then update local ignored config or lab profile intentionally.",
        },
        {
            "id": "readdress_existing_cluster_to_lab_profile",
            "label": "Move ONTAP to lab profile",
            "status": "blocked",
            "summary": "Plan an attended ONTAP readdress workflow for cluster, node, SVM, and NFS LIFs.",
            "next_action": (
                "Resolve node health/HA and prove REST or SSH access before building a guarded readdress apply lane."
                if console_facts.get("cluster_ha_warning")
                else "Build a guarded readdress apply lane after management access is reachable."
            ),
        },
    ]


def _selected_readdress_method(plan: dict[str, Any]) -> dict[str, Any]:
    reachability = plan.get("reachability") if isinstance(plan.get("reachability"), dict) else {}
    checks = reachability.get("checks") if isinstance(reachability.get("checks"), list) else []
    current_cluster = next((item for item in checks if item.get("id") == "current_cluster_mgmt"), {})
    rest_or_ssh = current_cluster.get("tcp_443") is True or current_cluster.get("tcp_22") is True
    console = plan.get("console_facts") if isinstance(plan.get("console_facts"), dict) else {}
    console_ready = console.get("identified_state") == "ontap_shell"
    if rest_or_ssh:
        return {
            "id": "ontap_rest_or_ssh",
            "label": "ONTAP REST/SSH",
            "status": "available",
            "reason": "Current cluster management is reachable from this host.",
        }
    if console_ready:
        return {
            "id": "console_cli",
            "label": "Console CLI",
            "status": "selected",
            "reason": "REST/SSH are unreachable, but the serial console is at an ONTAP shell.",
        }
    return {
        "id": "none",
        "label": "No safe method",
        "status": "blocked",
        "reason": "Neither management REST/SSH nor ONTAP console shell access is currently available.",
    }


def _address_command_plan(plan: dict[str, Any]) -> dict[str, Any]:
    console = plan.get("console_facts") if isinstance(plan.get("console_facts"), dict) else {}
    current = plan.get("current_targets") if isinstance(plan.get("current_targets"), dict) else {}
    planned = plan.get("planned_targets") if isinstance(plan.get("planned_targets"), dict) else {}
    netmask = os.getenv("NETAPP_ADDRESS_NETMASK") or ADDRESS_DEFAULT_NETMASK
    cluster_name = _cluster_name_from_console()
    svm_name = _svm_name_from_current(current)
    node_lifs = current.get("node_mgmt_lifs_by_node") if isinstance(current.get("node_mgmt_lifs_by_node"), dict) else {}
    node_ips = current.get("node_mgmt_by_node") if isinstance(current.get("node_mgmt_by_node"), dict) else {}
    node_names = list(sorted(node_ips))
    data_lifs = [item for item in list(current.get("data_lifs") or []) if isinstance(item, dict)]
    commands: list[dict[str, Any]] = []

    if current.get("cluster_mgmt") and planned.get("cluster_mgmt") and current.get("cluster_mgmt") != planned.get("cluster_mgmt"):
        commands.append(
            _command_item(
                "cluster_mgmt",
                "Modify cluster management LIF",
                f"network interface modify -vserver {cluster_name or '<cluster>'} -lif cluster_mgmt -address {planned.get('cluster_mgmt')} -netmask {netmask}",
                current.get("cluster_mgmt"),
                planned.get("cluster_mgmt"),
                enabled=bool(cluster_name),
                requires_create=False,
            )
        )

    node_targets = [
        ("node_a_mgmt", 0, planned.get("node_a_mgmt")),
        ("node_b_mgmt", 1, planned.get("node_b_mgmt")),
    ]
    for item_id, index, target in node_targets:
        if index >= len(node_names) or not target:
            continue
        node = node_names[index]
        if node_ips.get(node) == target:
            continue
        lif = node_lifs.get(node) or f"{node}_mgmt1"
        commands.append(
            _command_item(
                item_id,
                f"Modify node management LIF for {node}",
                f"network interface modify -vserver {cluster_name or '<cluster>'} -lif {lif} -address {target} -netmask {netmask}",
                node_ips.get(node),
                target,
                enabled=bool(cluster_name),
                requires_create=False,
            )
        )

    planned_lifs = list(planned.get("nfs_lifs") or [])
    for index, target in enumerate(planned_lifs):
        existing = data_lifs[index] if index < len(data_lifs) else None
        if existing:
            if existing.get("address") == target:
                continue
            commands.append(
                _command_item(
                    f"nfs_lif_{index + 1}",
                    f"Modify NFS data LIF {existing.get('lif')}",
                    f"network interface modify -vserver {existing.get('vserver')} -lif {existing.get('lif')} -address {target} -netmask {netmask}",
                    existing.get("address"),
                    target,
                    enabled=True,
                    requires_create=False,
                )
            )
        elif target:
            home_node = node_names[min(index, len(node_names) - 1)] if node_names else "<node>"
            home_port = data_lifs[0].get("home_port") if data_lifs else "e0b"
            commands.append(
                _command_item(
                    f"nfs_lif_{index + 1}",
                    f"Create missing NFS data LIF {index + 1}",
                    f"network interface create -vserver {svm_name or '<svm>'} -lif nfs_lif_{index + 1:02d} -service-policy default-data-files -home-node {home_node} -home-port {home_port} -address {target} -netmask {netmask} -status-admin up",
                    None,
                    target,
                    enabled=bool(svm_name and node_names),
                    requires_create=True,
                )
            )

    if planned.get("svm_mgmt") and current.get("svm_mgmt") != planned.get("svm_mgmt"):
        home_node = node_names[-1] if node_names else "<node>"
        existing_svm = current.get("svm_mgmt_lif") if isinstance(current.get("svm_mgmt_lif"), dict) else {}
        if existing_svm:
            commands.append(
                _command_item(
                    "svm_mgmt",
                    "Modify SVM management LIF",
                    f"network interface modify -vserver {existing_svm.get('vserver')} -lif {existing_svm.get('lif')} -address {planned.get('svm_mgmt')} -netmask {netmask}",
                    current.get("svm_mgmt"),
                    planned.get("svm_mgmt"),
                    enabled=True,
                    requires_create=False,
                )
            )
        else:
            commands.append(
                _command_item(
                    "svm_mgmt",
                    "Create missing SVM management LIF",
                    f"network interface create -vserver {svm_name or '<svm>'} -lif svm_mgmt -service-policy default-management -home-node {home_node} -home-port e0M -address {planned.get('svm_mgmt')} -netmask {netmask} -status-admin up",
                    None,
                    planned.get("svm_mgmt"),
                    enabled=bool(svm_name and node_names),
                    requires_create=True,
                )
            )

    readback = [
        "set -rows 0",
        "network interface show -fields vserver,lif,address,role,home-node,home-port,status-admin,status-oper",
        "cluster show",
        "cluster ha show",
    ]
    return {
        "method": _selected_readdress_method(plan),
        "netmask": netmask,
        "cluster_name": cluster_name,
        "svm_name": svm_name,
        "commands": commands,
        "enabled_commands": [item for item in commands if item.get("enabled")],
        "requires_lif_create": any(item.get("requires_create") for item in commands),
        "disabled_reasons": _command_plan_disabled_reasons(commands, console),
        "readback_commands": readback,
    }


def _command_item(
    item_id: str,
    label: str,
    command: str,
    current: Any,
    planned: Any,
    *,
    enabled: bool,
    requires_create: bool,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "label": label,
        "command": command,
        "current": current,
        "planned": planned,
        "enabled": enabled,
        "requires_create": requires_create,
        "write_type": "create" if requires_create else "modify",
    }


def _command_plan_disabled_reasons(commands: list[dict[str, Any]], console: dict[str, Any]) -> list[str]:
    reasons = []
    if console.get("identified_state") != "ontap_shell":
        reasons.append("Console is not currently at an ONTAP shell.")
    for item in commands:
        if not item.get("enabled"):
            reasons.append(f"{item.get('label')} cannot be generated from current console facts.")
    return _unique(reasons)


def _address_preview_blockers(
    plan: dict[str, Any],
    address_scan: dict[str, Any],
    command_plan: dict[str, Any],
) -> list[str]:
    console = plan.get("console_facts") if isinstance(plan.get("console_facts"), dict) else {}
    blockers = []
    if console.get("identified_state") != "ontap_shell":
        blockers.append("NetApp console is not at an ONTAP shell.")
    if address_scan.get("status") == "blocked":
        conflicts = _blocking_target_conflicts(address_scan, plan)
        if conflicts:
            blockers.append("Target address conflict scan found at least one in-use planned address not already owned by NetApp.")
    if command_plan.get("disabled_reasons"):
        blockers.extend(command_plan["disabled_reasons"])
    if not _enabled_commands(command_plan):
        blockers.append("No enabled NetApp address remediation commands could be generated.")
    return _unique(blockers)


def _blocking_target_conflicts(address_scan: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    current = plan.get("current_targets") if isinstance(plan.get("current_targets"), dict) else {}
    owned = {
        str(value)
        for value in [
            current.get("cluster_mgmt"),
            current.get("node_a_mgmt"),
            current.get("node_b_mgmt"),
            current.get("svm_mgmt"),
            *(current.get("nfs_lifs") or []),
        ]
        if value
    }
    return [
        item
        for item in address_scan.get("conflicts") or []
        if str(item.get("address") or "") not in owned
    ]


def _address_apply_gates(preview: dict[str, Any]) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    command_plan = preview.get("command_plan") if isinstance(preview.get("command_plan"), dict) else {}
    facts = preview.get("console_facts") if isinstance(preview.get("console_facts"), dict) else {}
    address_scan = preview.get("address_conflict_scan") if isinstance(preview.get("address_conflict_scan"), dict) else {}
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "netapp_address_apply": os.getenv("NETAPP_ADDRESS_APPLY") == "true",
        "netapp_address_confirm": os.getenv("NETAPP_ADDRESS_CONFIRM") == ADDRESS_CONFIRM_PHRASE,
        "netapp_address_allow_console_writes": os.getenv("NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES") == "true",
        "netapp_address_allow_lif_create": os.getenv("NETAPP_ADDRESS_ALLOW_LIF_CREATE") == "true",
        "netapp_address_accept_ha_warning": os.getenv("NETAPP_ADDRESS_ACCEPT_HA_WARNING") == "true",
    }
    blockers = []
    blockers.extend(policy.action_blockers("netapp.address-remediation", ActionCategory.NETWORK_CONFIG))
    if facts.get("identified_state") != "ontap_shell":
        blockers.append("NetApp console is not at an ONTAP shell.")
    if address_scan.get("free") is not True and _blocking_target_conflicts(address_scan, preview):
        blockers.append("Fresh pre-apply address conflict scan did not prove planned NetApp addresses are free.")
    if not _console_context().get("usable"):
        blockers.append("NetApp console/API credential pair is not configured for the guarded console executor.")
    if not _enabled_commands(command_plan):
        blockers.append("No enabled address remediation commands are available to apply.")
    if command_plan.get("requires_lif_create") and not flag_state["netapp_address_allow_lif_create"]:
        blockers.append("NETAPP_ADDRESS_ALLOW_LIF_CREATE=true is required because one or more target LIFs are missing.")
    if facts.get("cluster_ha_warning") and not flag_state["netapp_address_accept_ha_warning"]:
        blockers.append("NETAPP_ADDRESS_ACCEPT_HA_WARNING=true is required because the current cluster HA warning is still present.")
    if not flag_state["netapp_address_apply"]:
        blockers.append("NETAPP_ADDRESS_APPLY=true is required.")
    if not flag_state["netapp_address_confirm"]:
        blockers.append(f'NETAPP_ADDRESS_CONFIRM="{ADDRESS_CONFIRM_PHRASE}" is required.')
    if not flag_state["netapp_address_allow_console_writes"]:
        blockers.append("NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES=true is required.")
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _address_required_flags(command_plan: dict[str, Any] | None = None) -> list[str]:
    flags = [
        "PROVIDER_MODE=local-lab-readwrite",
        "NETAPP_ADDRESS_APPLY=true",
        f'NETAPP_ADDRESS_CONFIRM="{ADDRESS_CONFIRM_PHRASE}"',
        "NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES=true",
        "NETAPP_ADDRESS_ACCEPT_HA_WARNING=true",
    ]
    if command_plan and command_plan.get("requires_lif_create"):
        flags.append("NETAPP_ADDRESS_ALLOW_LIF_CREATE=true")
    return flags


def _enabled_commands(command_plan: dict[str, Any]) -> list[str]:
    return [str(item.get("command")) for item in command_plan.get("commands") or [] if item.get("enabled") and item.get("command")]


def _redacted_commands(commands: list[str]) -> list[str]:
    return [redact_sensitive(command) for command in commands]


def _console_context() -> dict[str, Any]:
    try:
        payload = json.loads(CONSOLE_LOGIN_STATE_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        payload = {}
    username = os.getenv("NETAPP_CONSOLE_USERNAME") or settings.netapp_api_username or os.getenv("NETAPP_USERNAME")
    password = os.getenv("NETAPP_CONSOLE_PASSWORD") or settings.netapp_api_password or os.getenv("NETAPP_PASSWORD")
    return {
        "selected_port": payload.get("selected_port") or settings.netapp_console_port,
        "selected_baud": payload.get("selected_baud") or settings.netapp_console_baud,
        "username": username,
        "password": password,
        "usable": bool(username and password),
    }


def _cluster_name_from_console() -> str:
    try:
        payload = json.loads(CONSOLE_LOGIN_STATE_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return settings.netapp_cluster_name or ""
    text = "\n".join(
        str(item.get("output_excerpt") or "")
        for item in payload.get("command_results") or []
        if isinstance(item, dict)
    )
    prompt_match = re.search(r"\n([A-Za-z0-9_.-]+)::>", text)
    if prompt_match:
        return prompt_match.group(1)
    return settings.netapp_cluster_name or ""


def _svm_name_from_current(current: dict[str, Any]) -> str:
    data_lifs = [item for item in list(current.get("data_lifs") or []) if isinstance(item, dict)]
    if data_lifs and data_lifs[0].get("vserver"):
        return str(data_lifs[0]["vserver"])
    return settings.netapp_svm_name or "esxi_svm"


def _target_validation_checks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    planned = plan.get("planned_targets") if isinstance(plan.get("planned_targets"), dict) else {}
    targets = [
        ("cluster_mgmt", "Cluster management", planned.get("cluster_mgmt"), (443, 22)),
        ("node_a_mgmt", "Node A management", planned.get("node_a_mgmt"), (443, 22)),
        ("node_b_mgmt", "Node B management", planned.get("node_b_mgmt"), (443, 22)),
        ("svm_mgmt", "SVM management", planned.get("svm_mgmt"), (443, 22)),
    ]
    targets.extend(
        (f"nfs_lif_{index + 1}", f"NFS LIF {index + 1}", address, (2049,))
        for index, address in enumerate(planned.get("nfs_lifs") or [])
    )
    checks = []
    for item_id, label, address, ports in targets:
        if not address:
            continue
        port_results = {str(port): _tcp(address, port, True) for port in ports}
        checks.append(
            {
                "id": item_id,
                "label": label,
                "address": address,
                "ports": port_results,
                "reachable": any(value is True for value in port_results.values()),
                "expected_reachable": item_id in {"cluster_mgmt", "nfs_lif_1", "nfs_lif_2"},
            }
        )
    return checks


def _run_console_commands(
    *,
    port: str,
    baud: int,
    username: str,
    password: str,
    commands: list[str],
    command_seconds: float = 5.0,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "port": port,
        "baud": baud,
        "commands": _redacted_commands(commands),
        "output_excerpt": "",
        "error": "",
        "checked_at": _now(),
    }
    if not port:
        result["error"] = "Console port is not selected."
        return result
    if not username or not password:
        result["error"] = "NetApp console credentials are not configured."
        return result
    try:
        import serial  # type: ignore
    except ImportError:
        result["error"] = "pyserial is not installed; real NetApp console workflow cannot open serial."
        return result
    transcript = ""
    try:
        with serial.Serial(port=port, baudrate=int(baud), timeout=0.35, write_timeout=0.5) as conn:
            conn.write(b"\r\n")
            conn.flush()
            transcript += _read_serial_quiet(conn, max_seconds=1.5)
            if "login" in transcript.lower():
                conn.write((username + "\r").encode())
                conn.flush()
                transcript += _read_serial_quiet(conn, max_seconds=2.0)
            if "password" in transcript.lower():
                conn.write((password + "\r").encode())
                conn.flush()
                transcript += _read_serial_quiet(conn, max_seconds=3.0)
            if "::>" not in transcript and "*>" not in transcript:
                conn.write(b"\r\n")
                conn.flush()
                transcript += _read_serial_quiet(conn, max_seconds=2.0)
            if "::>" not in transcript and "*>" not in transcript:
                result["error"] = "Console login did not reach an ONTAP cluster-shell prompt."
                result["output_excerpt"] = _redact_output(transcript[-6000:], password)
                return result
            for command in ["set -rows 0"] + commands:
                conn.write((command + "\r").encode())
                conn.flush()
                transcript += _read_serial_quiet(conn, max_seconds=command_seconds)
        result["ok"] = True
        result["output_excerpt"] = _redact_output(transcript[-12000:], password)
    except Exception as exc:  # pragma: no cover - hardware exception details vary
        result["error"] = str(exc).splitlines()[0]
        result["output_excerpt"] = _redact_output(transcript[-6000:], password)
    return result


def _read_serial_quiet(conn: Any, *, max_seconds: float = 3.0, quiet_seconds: float = 0.8) -> str:
    chunks: list[bytes] = []
    deadline = time.monotonic() + max_seconds
    quiet_deadline = time.monotonic() + quiet_seconds
    while time.monotonic() < deadline and time.monotonic() < quiet_deadline:
        waiting = int(getattr(conn, "in_waiting", 0) or 0)
        chunk = conn.read(waiting or 512)
        if chunk:
            chunks.append(chunk)
            quiet_deadline = time.monotonic() + quiet_seconds
        else:
            time.sleep(0.05)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _redact_output(output: str, password: str) -> str:
    text = str(output or "")
    if password:
        text = text.replace(password, "<redacted>")
    return redact_sensitive(text)


def _next_safe_action(blockers: list[str], comparisons: list[dict[str, Any]]) -> str:
    if blockers:
        return blockers[0]
    if any(item["status"] == "mismatch" for item in comparisons):
        return "Choose whether to update the lab profile to current ONTAP addresses or readdress ONTAP in an attended workflow."
    return "Run NetApp setup/NFS validation again; address plan has no current mismatch."


def _command_excerpt(payload: dict[str, Any], command_id: str) -> str:
    for item in payload.get("command_results") or []:
        if isinstance(item, dict) and item.get("id") == command_id:
            return str(item.get("output_excerpt") or "")
    return ""


def _empty_console_facts(reason: str) -> dict[str, Any]:
    return {
        "checked_at": None,
        "identified_state": "not_checked",
        "source": "not_available",
        "command_ids": [],
        "current_targets": _empty_current_targets(),
        "node_health": {"nodes": {}, "unhealthy_nodes": [], "all_healthy": False},
        "cluster_ha_warning": False,
        "blockers": [reason],
    }


def _empty_current_targets() -> dict[str, Any]:
    return {
        "cluster_mgmt": None,
        "node_a_mgmt": None,
        "node_b_mgmt": None,
        "node_mgmt_by_node": {},
        "node_mgmt_lifs_by_node": {},
        "svm_mgmt": None,
        "svm_mgmt_lif": None,
        "data_lifs": [],
        "nfs_lifs": [],
        "cluster_lifs": [],
        "source": "not_available",
    }


def _tcp(address: Any, port: int, enabled: bool) -> bool | None:
    if not enabled or not address:
        return None
    try:
        with socket.create_connection((str(address), port), timeout=2.0):
            return True
    except OSError:
        return False


def _address_plan_markdown(payload: dict[str, Any]) -> str:
    facts = payload.get("console_facts") if isinstance(payload.get("console_facts"), dict) else {}
    health = facts.get("node_health") if isinstance(facts.get("node_health"), dict) else {}
    lines = [
        "# NetApp Address Remediation Plan",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Console source: `{facts.get('source')}` checked_at=`{facts.get('checked_at')}`",
        f"- Node health clean: `{health.get('all_healthy')}`",
        f"- Cluster HA warning: `{facts.get('cluster_ha_warning')}`",
        "",
        "## Address Comparison",
        "",
        "| Item | Current | Planned | Status |",
        "| --- | --- | --- | --- |",
    ]
    for item in payload.get("address_comparisons") or []:
        lines.append(
            f"| {item.get('label')} | `{item.get('current') or 'unknown'}` | `{item.get('planned') or 'not planned'}` | `{item.get('status')}` |"
        )
    lines.extend(["", "## Operator Paths"])
    for path in payload.get("operator_paths") or []:
        lines.append(f"- {path.get('label')}: `{path.get('status')}` - {path.get('next_action')}")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Recheck", "", "- `make provider-lab-netapp-console-login-state`", "- `make provider-lab-netapp-address-plan`", "- `make provider-lab-live-status`"])
    lines.extend(["", "## Safety", "- No secrets are written to this report.", "- No ONTAP write, setup, storage, upgrade, reboot, wipe, takeover, or giveback command was run."])
    return "\n".join(lines) + "\n"


def _address_preview_markdown(payload: dict[str, Any]) -> str:
    method = payload.get("method") if isinstance(payload.get("method"), dict) else {}
    scan = payload.get("address_conflict_scan") if isinstance(payload.get("address_conflict_scan"), dict) else {}
    command_plan = payload.get("command_plan") if isinstance(payload.get("command_plan"), dict) else {}
    lines = [
        "# NetApp Address Remediation Preview",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Method: `{method.get('label')}` status=`{method.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Target Address Scan",
        "",
        f"- Status: `{scan.get('status')}` free=`{scan.get('free')}`",
    ]
    for result in scan.get("results") or []:
        lines.append(f"- `{result.get('label')}` `{result.get('address')}`: `{result.get('classification')}`")
    lines.extend(["", "## Command Plan"])
    for item in command_plan.get("commands") or []:
        state = "enabled" if item.get("enabled") else "disabled"
        create = " create" if item.get("requires_create") else " modify"
        lines.append(f"- `{state}` `{item.get('id')}`{create}: `{item.get('command')}`")
    if not command_plan.get("commands"):
        lines.append("- No commands generated.")
    lines.extend(["", "## Required Flags"])
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(
        [
            "",
            "## Safety",
            "- Preview only; no ONTAP network, setup, storage, reboot, wipe, or upgrade command was sent.",
            "- Secrets are represented only as configured/missing/redacted state.",
        ]
    )
    return "\n".join(lines) + "\n"


def _address_apply_markdown(payload: dict[str, Any]) -> str:
    apply_section = payload.get("apply") if isinstance(payload.get("apply"), dict) else {}
    lines = [
        "# NetApp Address Remediation Apply",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Console writes attempted: `{apply_section.get('console_writes_attempted')}`",
        "",
        "## Required Flags",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Commands Attempted"])
    lines.extend(f"- `{item}`" for item in apply_section.get("commands_attempted") or ["None"])
    lines.extend(["", "## Readback"])
    lines.extend(f"- `{item}`" for item in apply_section.get("readback_commands") or ["None"])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Result"])
    lines.append(f"- {apply_section.get('message') or payload.get('message')}")
    console = apply_section.get("console_result") if isinstance(apply_section.get("console_result"), dict) else {}
    if console.get("error"):
        lines.append(f"- Console error: `{console.get('error')}`")
    lines.extend(["", "## Safety", "- No secrets are written to this report."])
    return "\n".join(lines) + "\n"


def _address_validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp Address Remediation Validation",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        "",
        "## Address Comparison",
        "",
        "| Item | Current | Planned | Status |",
        "| --- | --- | --- | --- |",
    ]
    for item in payload.get("address_comparisons") or []:
        lines.append(
            f"| {item.get('label')} | `{item.get('current') or 'unknown'}` | `{item.get('planned') or 'not planned'}` | `{item.get('status')}` |"
        )
    lines.extend(["", "## Target Checks"])
    for check in payload.get("target_checks") or []:
        lines.append(f"- {check.get('label')} `{check.get('address')}` reachable=`{check.get('reachable')}` ports=`{check.get('ports')}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- Validation is read-only and does not run ONTAP write commands."])
    return "\n".join(lines) + "\n"


def _ha_node_markdown(payload: dict[str, Any]) -> str:
    operator = payload.get("operator_action") if isinstance(payload.get("operator_action"), dict) else {}
    safe = payload.get("safe_app_remediation") if isinstance(payload.get("safe_app_remediation"), dict) else {}
    health = payload.get("node_health") if isinstance(payload.get("node_health"), dict) else {}
    lines = [
        "# NetApp HA / Node Remediation Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Cluster HA warning: `{payload.get('cluster_ha_warning')}`",
        f"- Blocks address remediation: `{payload.get('blocks_address_remediation')}`",
        f"- Blocks NFS setup: `{payload.get('blocks_nfs_setup')}`",
        "",
        "## Node Health",
    ]
    nodes = health.get("nodes") if isinstance(health.get("nodes"), dict) else {}
    for node, state in nodes.items():
        lines.append(f"- `{node}`: `{state}`")
    if not nodes:
        lines.append("- No node health rows parsed.")
    lines.extend(
        [
            "",
            "## Safe App Remediation",
            f"- Available: `{safe.get('available')}`",
            f"- Reason: {safe.get('reason')}",
            "",
            "## Operator Action",
            f"- Problem: {operator.get('problem')}",
            f"- Where to fix: {operator.get('where_to_fix')}",
            f"- Recommended action: {operator.get('recommended_action')}",
            f"- Recheck: `{operator.get('recheck_command')}`",
            "",
            "## Blockers",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Diagnostic Commands"])
    lines.extend(f"- `{item}`" for item in payload.get("diagnostic_commands") or [])
    lines.extend(["", "## Safety", "- Read-only diagnostic; no NetApp HA, reboot, wipe, storage, or network write command was sent."])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown_builder(payload), encoding="utf-8")


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
