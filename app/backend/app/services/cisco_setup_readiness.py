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
    console_summary = {
        "status": console.status,
        "effective_path": console_discovery.get("effective_path"),
        "recommended_path": console_discovery.get("recommended_path"),
        "candidate_count": int(candidate_counts.get("existing", 0) or 0),
        "stable_candidate_count": int(candidate_counts.get("stable_existing", 0) or 0),
        "fallback_candidate_count": int(candidate_counts.get("fallback_existing", 0) or 0),
        "safe_next_action": NEXT_SAFE_ACTION,
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
        "console": console_summary,
        "bootstrap_preview": {
            "apply_enabled": False,
            "commands_redacted": True,
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
        return f"Management IP is planned for {target_ip}."
    return "Management IP is not configured in local settings."
