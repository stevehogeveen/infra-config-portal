from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.providers.base import ProviderStatus
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.services.hpe_raid import REPO_ROOT
from app.services.cisco_setup_wizard_plan import build_cisco_setup_wizard_plan
from app.services.lab_profiles import active_lab_profile_context

PROVIDER_ID = "cisco-setup"
REAL_LAB_DETAILS = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-4h-lab-run-details-redacted.json"
NEXT_SAFE_ACTION = "Select a console candidate and run prompt readiness check."
DISABLED_ACTIONS = [
    "conf t",
    "write memory",
    "reload",
    "erase/copy",
    "VLAN/interface/user/password changes",
    "enable SSH/SCP",
    "real config apply",
    "raw running-config backup",
]


def get_cisco_setup_readiness(
    *,
    provider_mode: str | None = None,
    planned_management_ip: str | None = None,
    management_configured: bool | None = None,
    console_status: ProviderStatus | None = None,
    ansible_status: ProviderStatus | None = None,
) -> dict[str, Any]:
    mode = provider_mode or settings.provider_mode
    profile_context = _profile_context(mode)
    target_ip = (
        planned_management_ip
        if planned_management_ip is not None
        else _profile_cisco_management_ip(profile_context)
        or settings.cisco_target_ip
    )
    mgmt_configured = (
        management_configured
        if management_configured is not None
        else settings.cisco_mgmt_configured
    )
    console = console_status or CiscoConsoleAdapter(mode).health()
    ansible = ansible_status or CiscoAnsibleAdapter(mode).health()
    control_host_network = profile_context.get("control_host_network") or {}
    control_host_blocked = _control_host_network_blocked(control_host_network)
    control_host_blocker = _control_host_blocker(control_host_network)
    console_discovery = console.discovery or {}
    candidate_counts = _dict(console_discovery.get("candidate_counts"))
    last_prompt_readiness = _prompt_readiness_summary(console.last_probe_result)
    console_summary = {
        "status": "blocked" if control_host_blocked else console.status,
        "serial_candidate_status": console.status,
        "effective_path": console_discovery.get("effective_path"),
        "recommended_path": console_discovery.get("recommended_path"),
        "selected_path": console_discovery.get("effective_path"),
        "selection_source": console_discovery.get("selection_source"),
        "baud": console.configuration.get("baud"),
        "read_timing": _read_timing(console.configuration, last_prompt_readiness),
        "candidate_count": int(candidate_counts.get("existing", 0) or 0),
        "stable_candidate_count": int(candidate_counts.get("stable_existing", 0) or 0),
        "fallback_candidate_count": int(candidate_counts.get("fallback_existing", 0) or 0),
        "safe_next_action": control_host_network.get("next_action")
        if control_host_blocked
        else NEXT_SAFE_ACTION,
        "last_prompt_readiness": last_prompt_readiness,
    }
    warnings = list(dict.fromkeys([*console.warnings, *ansible.warnings]))
    blockers = list(dict.fromkeys([*console.blockers, *ansible.blockers]))
    if control_host_blocked:
        blockers = list(dict.fromkeys([control_host_blocker, *blockers]))
    setup_wizard_plan = build_cisco_setup_wizard_plan(console.last_probe_result)
    setup_wizard_detected = bool(setup_wizard_plan["setup_wizard_detected"])
    real_lab_run = _real_lab_run_summary()
    real_lab_recovery_available = mode in {"local-readonly", "local-lab-readwrite"}
    next_safe_action = (
        str(control_host_network.get("next_action") or control_host_blocker)
        if control_host_blocked
        else (
            "Review setup wizard plan preview."
            if setup_wizard_detected
            else "Recover Cisco password from console."
            if real_lab_recovery_available and _needs_password_recovery_action(real_lab_run)
            else NEXT_SAFE_ACTION
        )
    )

    phase = (
        "blocked"
        if control_host_blocked
        else "ssh-management-ready"
        if mgmt_configured
        else "console-bootstrap-required"
    )
    ansible_reason = (
        control_host_blocker
        if control_host_blocked
        else (
            "CISCO_MGMT_CONFIGURED is true; use explicit read-only Ansible checks before any future workflow."
            if mgmt_configured
            else "CISCO_MGMT_CONFIGURED is false; use console bootstrap before Ansible SSH."
        )
    )

    return {
        "provider_id": PROVIDER_ID,
        "status": "blocked" if control_host_blocked else "not_checked",
        "source_type": "not_checked" if control_host_blocked else "operator_config",
        "freshness": "not_checked",
        "checked_at": control_host_network.get("checked_at") if control_host_blocked else None,
        "phase": phase,
        "planned_management_ip": target_ip,
        "management_configured": mgmt_configured,
        "control_host_network": control_host_network,
        "state_boundaries": {
            "discovered_current_device_state": {
                "summary": "Current Cisco network access is blocked by the control-host subnet check."
                if control_host_blocked
                else "Console adapter discovery and latest prompt readiness only.",
                "console_status": "blocked" if control_host_blocked else console.status,
                "serial_candidate_status": console.status,
                "selected_path": console_summary["selected_path"],
                "baud": console_summary["baud"],
                "prompt_state": last_prompt_readiness.get("prompt_state"),
                "prompt_captured": last_prompt_readiness.get("captured"),
                "prompt_classification": last_prompt_readiness.get("prompt_classification"),
            },
            "saved_kit_config_values": {
                "summary": "Non-secret local planning values; not confirmed reachable.",
                "planned_management_ip": target_ip,
                "planned_prefix": settings.cisco_management_prefix,
                "management_configured": mgmt_configured,
            },
            "values_ready_to_apply": {
                "summary": "Apply remains disabled until all explicit gates pass.",
                "ready": False,
                "reason": "Console bootstrap apply scaffold is blocked by default.",
            },
            "last_action_logs_artifacts": {
                "summary": "Only redacted prompt-readiness summaries are exposed here.",
                "last_action_present": bool(last_prompt_readiness.get("available")),
                "checked_at": last_prompt_readiness.get("checked_at"),
                "last_prompt_readiness": last_prompt_readiness,
                "redacted_summary": last_prompt_readiness.get("message"),
                "raw_console_log_saved": False,
            },
        },
        "console": console_summary,
        "password_recovery": {
            "needed": _needs_password_recovery_action(real_lab_run),
            "enable_command_sent": real_lab_run.get("enable_command_sent"),
            "password_prompt_seen": real_lab_run.get("password_prompt_seen"),
            "enable_rejected": real_lab_run.get("enable_rejected"),
            "final_prompt_state": real_lab_run.get("privilege_final_prompt_state") or real_lab_run.get("prompt_state"),
            "next_action": real_lab_run.get("privilege_next_action") or next_safe_action,
            "runbook": [
                "Connect console and confirm selected serial port/baud.",
                "Interrupt boot if the platform password recovery procedure requires it.",
                "Ignore startup configuration only when supported by the platform procedure.",
                "Boot, set new local admin and enable credentials, and save manually.",
                "Update .env.local.real-lab locally with the new credential values.",
            ],
        },
        "ethernet_readiness": {
            "management_configured": mgmt_configured,
            "planned_management_ip": target_ip,
            "planned_prefix": settings.cisco_management_prefix,
            "planned_gateway": bool(settings.cisco_management_gateway),
            "management_vlan": settings.cisco_management_vlan,
            "management_interface": settings.cisco_management_interface,
            "management_strategy": settings.cisco_management_strategy,
            "ssh_probe_status": "blocked"
            if control_host_blocked
            else "skipped"
            if not mgmt_configured
            else ansible.status,
            "ssh_probe_reason": ansible_reason,
            "bootstrap_required": not mgmt_configured,
            "ready": bool(
                not control_host_blocked and mgmt_configured and ansible.status == "ready"
            ),
            "next_safe_action": (
                str(control_host_network.get("next_action") or control_host_blocker)
                if control_host_blocked
                else (
                "Use console bootstrap to establish management VLAN/IP/SSH/SCP readiness."
                if not mgmt_configured
                else "Run explicit read-only SSH/Ansible probe before any configuration workflow."
                )
            ),
        },
        "bootstrap_preview": {
            "apply_enabled": False,
            "commands_redacted": True,
            "serial_writes_attempted": False,
            "missing_requirements": _bootstrap_missing_requirements(target_ip),
            "redacted_command_summary": [
                "Future command preview stays plan-only and redacted in readiness.",
                "Console bootstrap plan endpoint provides the separate guarded preview.",
                "No setup wizard answers or configuration commands are sent.",
            ],
            "summary": [
                _management_ip_summary(target_ip),
                "SSH/SCP readiness is planned only and will not be enabled.",
                (
                    "No VLAN, interface, user, password, write memory, reload, "
                    "erase, or copy action is allowed."
                ),
            ],
        },
        "ssh_scp_readiness": {
            "planned_only": True,
            "apply_enabled": False,
            "summary": (
                "SSH/SCP readiness can be planned after console bootstrap design, "
                "but will not be enabled by this task."
            ),
        },
        "real_lab_run": real_lab_run,
        "ansible": {
            "status": "blocked"
            if control_host_blocked
            else ansible.status
            if mgmt_configured
            else "awaiting-bootstrap",
            "enabled": False,
            "reason": ansible_reason,
        },
        "backup_report": {
            "backup_enabled": True,
            "report_placeholder_enabled": False,
            "summary": (
                "Backup/export writes redacted console identity, VLAN, management, SSH/SCP, "
                "and selected configuration proof. Raw running-config is not persisted."
            ),
        },
        "setup_wizard_plan": {
            "available": True,
            "detected": setup_wizard_detected,
            "detected_prompt_state": setup_wizard_plan["detected_prompt_state"],
            "apply_enabled": False,
            "next_safe_action": setup_wizard_plan["next_safe_action"],
            "summary": setup_wizard_plan["message"],
        },
        "blockers": blockers,
        "warnings": warnings,
        "disabled_actions": DISABLED_ACTIONS,
        "next_safe_action": next_safe_action,
    }


def _dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _profile_context(mode: str) -> dict[str, Any]:
    if mode == "mock":
        return {}
    return active_lab_profile_context()


def _profile_cisco_management_ip(profile_context: dict[str, Any]) -> str | None:
    plan = profile_context.get("resolved_address_plan")
    if isinstance(plan, dict) and plan.get("cisco_management"):
        return str(plan.get("cisco_management"))
    profile = profile_context.get("active_profile")
    if isinstance(profile, dict):
        resolved = profile.get("resolved_address_plan")
        if isinstance(resolved, dict) and resolved.get("cisco_management"):
            return str(resolved.get("cisco_management"))
    return None


def _control_host_network_blocked(status: dict[str, Any]) -> bool:
    return bool(status) and status.get("status") != "ready"


def _control_host_blocker(status: dict[str, Any]) -> str:
    blockers = status.get("blockers")
    if isinstance(blockers, list):
        first = next((str(item) for item in blockers if str(item).strip()), "")
        if first:
            return first
    message = str(status.get("message") or "").strip()
    if message:
        return message
    subnet = status.get("active_subnet") or "the active lab subnet"
    return f"Control host is not on {subnet}; Cisco network access is not checked from this app host."


def _management_ip_summary(target_ip: str | None) -> str:
    if target_ip:
        return f"Management IP is planned for {target_ip}; reachability is not confirmed."
    return "Management IP is not configured in local settings."


def _prompt_readiness_summary(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("action") != "prompt-readiness":
        return {
            "available": False,
            "prompt_state": "unknown",
            "captured": None,
            "message": "Prompt readiness has not run in this backend process.",
            "safe_show_commands_allowed": False,
            "checked_at": None,
            "next_safe_action": "Run an explicit newline-only prompt readiness check when safe.",
            "future_show_command_check_eligible": False,
            "prompt_classification": {
                "state": "unknown",
                "label": "Unknown prompt",
                "summary": "No prompt-readiness result is cached.",
                "no_output_captured": False,
                "raw_text_redacted": True,
                "safe_show_commands_allowed": False,
                "next_safe_action": "Run an explicit newline-only prompt readiness check when safe.",
            },
            "troubleshooting_checklist": [],
        }
    prompt_sample = _dict(result.get("prompt_sample"))
    return {
        "available": True,
        "status": result.get("status"),
        "message": result.get("message"),
        "prompt_state": result.get("prompt_state"),
        "captured": prompt_sample.get("captured"),
        "line_count": prompt_sample.get("line_count"),
        "last_line": prompt_sample.get("last_line"),
        "safe_show_commands_allowed": bool(result.get("safe_show_commands_allowed")),
        "future_show_command_check_eligible": bool(result.get("future_show_command_check_eligible")),
        "checked_at": result.get("checked_at"),
        "read_timing": _dict(result.get("read_timing")),
        "next_safe_action": result.get("next_safe_action"),
        "prompt_classification": _dict(result.get("prompt_classification")),
        "troubleshooting_checklist": result.get("troubleshooting_checklist") or [],
    }


def _read_timing(
    configuration: dict[str, Any],
    last_prompt_readiness: dict[str, Any],
) -> dict[str, Any]:
    last_timing = _dict(last_prompt_readiness.get("read_timing"))
    if last_timing:
        return last_timing
    return {
        "settle_seconds": configuration.get("prompt_settle_seconds"),
        "read_window_seconds": configuration.get("prompt_read_window_seconds"),
        "max_bytes": configuration.get("prompt_max_bytes"),
    }


def _bootstrap_missing_requirements(target_ip: str | None) -> list[str]:
    missing = []
    if not target_ip:
        missing.append("planned management IP")
    if not settings.cisco_management_prefix:
        missing.append("management prefix")
    missing.extend(
        [
            "gateway",
            "management VLAN or interface strategy",
            "hostname and DNS/domain planning",
            "local admin username presence reference",
            "recent prompt-readiness evidence",
        ]
    )
    return missing


def _real_lab_run_summary() -> dict[str, Any]:
    if not REAL_LAB_DETAILS.exists():
        return {
            "available": False,
            "status": "not-run",
            "last_blocker": "No Cisco 4h real-lab run artifact has been recorded.",
        }
    try:
        payload = json.loads(REAL_LAB_DETAILS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "available": False,
            "status": "unreadable",
            "last_blocker": "Cisco 4h real-lab run artifact could not be read.",
        }
    stages = _dict(payload.get("stages"))
    adapter = _dict(stages.get("adapter_discovery"))
    prompt = _dict(stages.get("console_prompt_detection"))
    identity = _dict(stages.get("switch_identification"))
    plan = _dict(stages.get("bootstrap_plan"))
    apply = _dict(stages.get("apply"))
    ethernet = _dict(stages.get("ethernet_management_validation"))
    privilege = _dict(stages.get("privilege_escalation"))
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    last_blocker = next((item for item in blockers if isinstance(item, str)), None)
    if not last_blocker:
        privilege_blockers = privilege.get("blockers")
        if isinstance(privilege_blockers, list):
            last_blocker = next((item for item in privilege_blockers if isinstance(item, str)), None)
    return {
        "available": True,
        "checked_at": payload.get("checked_at"),
        "status": payload.get("status"),
        "console_adapter_detected": bool(adapter.get("effective_path")),
        "console_adapter": adapter.get("effective_path"),
        "prompt_detected": bool(prompt.get("prompt_detected")),
        "prompt_state": prompt.get("prompt_state"),
        "prompt_classification": prompt.get("classification"),
        "selected_baud": prompt.get("selected_baud"),
        "enable_command_sent": privilege.get("enable_command_sent"),
        "password_prompt_seen": privilege.get("password_prompt_seen"),
        "enable_rejected": _enable_rejected_label(privilege),
        "privilege_final_prompt_state": privilege.get("final_prompt_state"),
        "privilege_next_action": _privilege_next_action(privilege),
        "switch_identity_status": identity.get("status"),
        "switch_identity_privileged": identity.get("privileged"),
        "bootstrap_plan_status": plan.get("status"),
        "bootstrap_hostname": plan.get("hostname"),
        "bootstrap_management_interface": plan.get("management_interface"),
        "apply_status": apply.get("status"),
        "save_reload_status": _save_reload_status(apply),
        "ethernet_management_status": ethernet.get("status"),
        "ssh_status": _dict(ethernet.get("ssh")).get("reachable"),
        "scp_status": _dict(ethernet.get("scp")).get("status"),
        "last_blocker": last_blocker or "No blocker recorded.",
        "artifacts": payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {},
    }


def _save_reload_status(apply: dict[str, Any]) -> str:
    if not apply:
        return "not-attempted"
    reload_status = _dict(apply.get("reload"))
    if reload_status:
        return (
            f"save={apply.get('save_status') or 'unknown'}; "
            f"reload_attempted={bool(reload_status.get('attempted'))}"
        )
    return str(apply.get("save_status") or "not-attempted")


def _needs_password_recovery_action(real_lab_run: dict[str, Any]) -> bool:
    prompt_state = str(real_lab_run.get("prompt_state") or "")
    last_blocker = str(real_lab_run.get("last_blocker") or "").lower()
    if real_lab_run.get("status") == "blocked" and prompt_state in {
        "login-required",
        "rommon-bootloader",
        "password-recovery-ready",
    }:
        return True
    return (
        prompt_state in {"login-required", "exec", "rommon-bootloader", "password-recovery-ready"}
        and "privileged exec" in last_blocker
    ) or "password recovery" in last_blocker


def _enable_rejected_label(privilege: dict[str, Any]) -> str:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return "no"
    debug = privilege.get("debug") if isinstance(privilege.get("debug"), dict) else {}
    if debug.get("enable_command_sent") and debug.get("password_prompt_seen"):
        return "yes"
    if debug.get("enable_command_sent"):
        return "unknown"
    return "unknown"


def _privilege_next_action(privilege: dict[str, Any]) -> str:
    final_state = privilege.get("final_prompt_state")
    initial_state = privilege.get("initial_prompt_state")
    if final_state == "privileged-exec":
        return "Privilege is confirmed; continue Cisco management network validation."
    if final_state in {"password-recovery-ready", "rommon-bootloader"}:
        return "Use Cisco password recovery from the physical console before rerunning bootstrap."
    if _enable_rejected_label(privilege) == "yes":
        return "Try the correct enable secret; if none is available, perform Cisco password recovery."
    if initial_state in {"login-required", "password-required"}:
        return "Recover Cisco password from console or provide valid console login credentials."
    return "Confirm console cable and power if no prompt is visible, then rerun recovery."
