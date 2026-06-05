from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ProviderStatus
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.services.cisco_setup_wizard_plan import build_cisco_setup_wizard_plan

PROVIDER_ID = "cisco-setup"
NEXT_SAFE_ACTION = "Select a console candidate and run prompt readiness check."
DISABLED_ACTIONS = [
    "conf t",
    "write memory",
    "reload",
    "erase/copy",
    "VLAN/interface/user/password changes",
    "enable SSH/SCP",
    "real config apply",
    "running-config backup",
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
    target_ip = planned_management_ip if planned_management_ip is not None else settings.cisco_target_ip
    mgmt_configured = (
        management_configured
        if management_configured is not None
        else settings.cisco_mgmt_configured
    )
    console = console_status or CiscoConsoleAdapter(mode).health()
    ansible = ansible_status or CiscoAnsibleAdapter(mode).health()
    console_discovery = console.discovery or {}
    candidate_counts = _dict(console_discovery.get("candidate_counts"))
    last_prompt_readiness = _prompt_readiness_summary(console.last_probe_result)
    console_summary = {
        "status": console.status,
        "effective_path": console_discovery.get("effective_path"),
        "recommended_path": console_discovery.get("recommended_path"),
        "selected_path": console_discovery.get("effective_path"),
        "selection_source": console_discovery.get("selection_source"),
        "baud": console.configuration.get("baud"),
        "read_timing": _read_timing(console.configuration, last_prompt_readiness),
        "candidate_count": int(candidate_counts.get("existing", 0) or 0),
        "stable_candidate_count": int(candidate_counts.get("stable_existing", 0) or 0),
        "fallback_candidate_count": int(candidate_counts.get("fallback_existing", 0) or 0),
        "safe_next_action": NEXT_SAFE_ACTION,
        "last_prompt_readiness": last_prompt_readiness,
    }
    warnings = list(dict.fromkeys([*console.warnings, *ansible.warnings]))
    blockers = list(dict.fromkeys([*console.blockers, *ansible.blockers]))
    setup_wizard_plan = build_cisco_setup_wizard_plan(console.last_probe_result)
    setup_wizard_detected = bool(setup_wizard_plan["setup_wizard_detected"])
    next_safe_action = (
        "Review setup wizard plan preview."
        if setup_wizard_detected
        else NEXT_SAFE_ACTION
    )

    phase = "ssh-management-ready" if mgmt_configured else "console-bootstrap-required"
    ansible_reason = (
        "CISCO_MGMT_CONFIGURED is true; use explicit read-only Ansible checks before any future workflow."
        if mgmt_configured
        else "CISCO_MGMT_CONFIGURED is false; use console bootstrap before Ansible SSH."
    )

    return {
        "provider_id": PROVIDER_ID,
        "phase": phase,
        "planned_management_ip": target_ip,
        "management_configured": mgmt_configured,
        "state_boundaries": {
            "discovered_current_device_state": {
                "summary": "Console adapter discovery and latest prompt readiness only.",
                "console_status": console.status,
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
        "ethernet_readiness": {
            "management_configured": mgmt_configured,
            "planned_management_ip": target_ip,
            "planned_prefix": settings.cisco_management_prefix,
            "planned_gateway": bool(settings.cisco_management_gateway),
            "management_vlan": settings.cisco_management_vlan,
            "management_interface": settings.cisco_management_interface,
            "management_strategy": settings.cisco_management_strategy,
            "ssh_probe_status": "skipped" if not mgmt_configured else ansible.status,
            "ssh_probe_reason": ansible_reason,
            "bootstrap_required": not mgmt_configured,
            "ready": bool(mgmt_configured and ansible.status == "ready"),
            "next_safe_action": (
                "Use console bootstrap to establish management VLAN/IP/SSH/SCP readiness."
                if not mgmt_configured
                else "Run explicit read-only SSH/Ansible probe before any configuration workflow."
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
        "ansible": {
            "status": ansible.status if mgmt_configured else "awaiting-bootstrap",
            "enabled": False,
            "reason": ansible_reason,
        },
        "backup_report": {
            "backup_enabled": False,
            "report_placeholder_enabled": True,
            "summary": (
                "Backup/report placeholders are visible only. Running-config backup is "
                "disabled until SSH management exists and a future guarded workflow approves it."
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
