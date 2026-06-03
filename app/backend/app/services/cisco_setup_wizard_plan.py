from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.cisco_console import PROVIDER_ID as CISCO_CONSOLE_PROVIDER_ID
from app.providers.probe_cache import get_probe_result

PROVIDER_ID = "cisco-setup-wizard-plan"
UNKNOWN_PROMPT_STATE = "unknown"
NEXT_SAFE_ACTION = (
    "Review the setup wizard plan preview and define the future guarded bootstrap requirements."
)
WHY_BLOCKED = [
    "The setup wizard can change device configuration.",
    "This workflow is preview-only.",
    (
        "A future guarded bootstrap workflow must require explicit operator approval "
        "before sending any answers."
    ),
]
FUTURE_GUARDED_PLAN_PREVIEW = [
    "Confirm the selected console path.",
    "Confirm the intended management IP is 10.10.8.112.",
    (
        "Confirm management gateway, subnet, VLAN/default interface strategy, username policy, "
        "SSH/SCP policy, and save behavior."
    ),
    "Show exact commands or wizard answers before execution.",
    "Require explicit approval before sending any answer or entering configuration mode.",
    "Save logs, redacted prompt samples, plan summary, and operator approval record.",
]
NOT_ATTEMPTED = [
    "answer setup wizard yes/no prompt",
    "configure terminal",
    "write memory",
    "reload",
    "copy or erase",
    "VLAN, interface, user, password, SSH, or SCP changes",
    "running-config backup",
    "real config apply",
]
DISABLED_ACTIONS = [
    "answer setup wizard",
    "conf t",
    "write memory",
    "reload",
    "erase/copy",
    "VLAN/interface/user/password changes",
    "enable SSH/SCP",
    "running-config backup",
    "real config apply",
]


def get_cisco_setup_wizard_plan() -> dict[str, Any]:
    latest_prompt_result, _checked_at = get_probe_result(CISCO_CONSOLE_PROVIDER_ID)
    prompt_result = (
        latest_prompt_result
        if _is_prompt_readiness_result(latest_prompt_result)
        else None
    )
    return build_cisco_setup_wizard_plan(prompt_result)


def build_cisco_setup_wizard_plan(prompt_result: dict[str, Any] | None = None) -> dict[str, Any]:
    detected_prompt_state = _prompt_state(prompt_result)
    setup_wizard_detected = detected_prompt_state == "setup-wizard"
    return {
        "provider_id": PROVIDER_ID,
        "status": "preview",
        "apply_enabled": False,
        "planned_management_ip": settings.cisco_target_ip,
        "detected_prompt_state": detected_prompt_state,
        "setup_wizard_detected": setup_wizard_detected,
        "message": _message(setup_wizard_detected),
        "why_blocked": WHY_BLOCKED,
        "future_guarded_plan_preview": FUTURE_GUARDED_PLAN_PREVIEW,
        "not_attempted": NOT_ATTEMPTED,
        "disabled_actions": DISABLED_ACTIONS,
        "blockers": [
            "Setup wizard handling is preview-only; no answers will be sent by this workflow."
        ],
        "warnings": [],
        "next_safe_action": NEXT_SAFE_ACTION,
    }


def _is_prompt_readiness_result(result: dict[str, Any] | None) -> bool:
    return isinstance(result, dict) and result.get("action") == "prompt-readiness"


def _prompt_state(prompt_result: dict[str, Any] | None) -> str:
    if not prompt_result:
        return UNKNOWN_PROMPT_STATE
    value = prompt_result.get("prompt_state")
    return value if isinstance(value, str) and value else UNKNOWN_PROMPT_STATE


def _message(setup_wizard_detected: bool) -> str:
    if setup_wizard_detected:
        return (
            "Cisco console appears to be at the initial setup wizard prompt. "
            "No answers or commands were sent."
        )
    return (
        "Setup wizard planning preview is available. No answers or commands were sent."
    )
