from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import LAB_CISCO_MANAGEMENT_IP, settings
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive
from app.services.cisco_bootstrap_requirements import get_cisco_bootstrap_requirements
from app.services.firmware_compliance import firmware_gate_blockers

PROVIDER_ID = "cisco-console-bootstrap"
TARGET_IP = LAB_CISCO_MANAGEMENT_IP
TARGET_PREFIX = "/24"
TARGET_NETMASK = "255.255.255.0"
CONFIRMATION_PHRASE = f"APPLY CISCO CONSOLE BOOTSTRAP {TARGET_IP}"
MAX_PROMPT_AGE_MINUTES = 15
DISABLED_DESTRUCTIVE_ACTIONS = [
    "write erase",
    "erase startup-config",
    "delete flash:*config*",
    "reload",
    "copy",
    "wipe running-config",
]


def build_cisco_console_bootstrap_plan() -> dict[str, Any]:
    requirements = get_cisco_bootstrap_requirements()
    prompt_result, prompt_checked_at = get_probe_result("cisco-console")
    prompt_state = _prompt_state(prompt_result)
    prompt_detail = _prompt_detail(prompt_result, prompt_state)
    flow = _flow(prompt_state, prompt_detail)
    blockers = _plan_blockers(requirements, prompt_state, prompt_detail)
    command_preview = _command_preview(requirements)
    return {
        "provider_id": PROVIDER_ID,
        "status": "blocked" if blockers else "preview",
        "target": {
            "ip": _requirement_value(requirements, "planned_management_ip"),
            "required_ip": TARGET_IP,
            "prefix": _requirement_value(requirements, "subnet_prefix"),
            "required_prefix": TARGET_PREFIX,
            "netmask": TARGET_NETMASK,
        },
        "apply_enabled": False,
        "execution_supported": False,
        "serial_writes_attempted": False,
        "flow": flow,
        "prompt_state": prompt_state,
        "prompt_detail": prompt_detail,
        "prompt_checked_at": prompt_checked_at,
        "summary": [
            f"Target for this run is {TARGET_IP}{TARGET_PREFIX}.",
            "This API plan is preview-only; no console answers or commands are sent by this endpoint.",
            "The guarded real-lab executor is app/backend/scripts/cisco_real_lab_workflow.py --apply.",
            "Real apply requires local-lab-readwrite gates, recent prompt readiness, complete requirements, and local credentials.",
            "Destructive wipe/reset is separate and disabled.",
        ],
        "intended_steps": _intended_steps(flow),
        "command_preview": command_preview,
        "redacted_command_summary": _redacted_command_summary(flow),
        "commands_redacted": True,
        "blocker_summary": _blocker_summary(blockers),
        "artifact_preview": {
            "redacted": True,
            "raw_console_log_saved": False,
            "post_apply_report": "placeholder",
            "last_action_metadata": "Blocked previews record status, blockers, prompt state, and checked time only.",
            "missing_artifacts_message": "No apply artifacts exist because serial writes are not implemented.",
        },
        "destructive_actions_disabled": DISABLED_DESTRUCTIVE_ACTIONS,
        "blockers": blockers,
        "warnings": [
            "The API endpoint is a planning/stub surface; use the guarded Cisco real-lab workflow for serial writes.",
            "No reload, erase, raw config backup, firmware install, or destructive operation is included.",
        ],
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "guarded_executor": "python app/backend/scripts/cisco_real_lab_workflow.py --apply",
        "next_safe_action": "Review the preview, run prompt readiness, and keep apply disabled unless all gates pass.",
    }


def apply_cisco_console_bootstrap(payload: dict[str, Any]) -> dict[str, Any]:
    confirmation_phrase = payload.get("confirmation_phrase")
    plan = build_cisco_console_bootstrap_plan()
    gate_blockers = _apply_gate_blockers(plan, confirmation_phrase, payload)
    status = "blocked"
    message = "Cisco console bootstrap apply was blocked; no console commands were sent."
    if not gate_blockers:
        gate_blockers.append(
            "Serial write execution is not implemented in this scaffold; no console commands were sent."
        )
    result = {
        "provider_id": PROVIDER_ID,
        "status": status,
        "message": message,
        "target": plan["target"],
        "flow": plan["flow"],
        "prompt_state": plan["prompt_state"],
        "serial_writes_attempted": False,
        "commands_sent": [],
        "artifacts": {
            "redacted": True,
            "raw_console_log_saved": False,
            "post_apply_report": "placeholder",
        },
        "warnings": plan["warnings"],
        "blockers": gate_blockers,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    return record_probe_result(PROVIDER_ID, redact_sensitive(result))


def _apply_gate_blockers(
    plan: dict[str, Any],
    confirmation_phrase: object,
    payload: dict[str, Any] | None = None,
) -> list[str]:
    blockers = list(plan["blockers"])
    payload = payload or {}
    requested_actions = payload.get("requested_actions")
    destructive_requested = bool(payload.get("destructive_action_requested"))
    if destructive_requested or _requests_destructive_action(requested_actions):
        blockers.append(
            "Destructive reset/wipe/copy/reload actions are not allowed by console bootstrap."
        )
    blockers.extend(firmware_gate_blockers("Cisco bootstrap apply"))
    if settings.provider_mode != "local-readonly":
        blockers.append("PROVIDER_MODE=local-readonly is required for guarded console apply.")
    if not settings.cisco_console_apply_enabled:
        blockers.append("CISCO_CONSOLE_APPLY_ENABLED=true is required for guarded console apply.")
    if settings.lab_apply_ack != "YES":
        blockers.append("LAB_APPLY_ACK=YES is required for guarded console apply.")
    if settings.lab_target_ack != TARGET_IP:
        blockers.append(f"LAB_TARGET_ACK={TARGET_IP} is required for guarded console apply.")
    if confirmation_phrase != CONFIRMATION_PHRASE:
        blockers.append(f"Exact confirmation phrase is required: {CONFIRMATION_PHRASE}")
    return list(dict.fromkeys(blockers))


def _plan_blockers(
    requirements: dict[str, Any],
    prompt_state: str,
    prompt_detail: str,
) -> list[str]:
    blockers = [
        blocker for blocker in requirements["blockers"]
        if not blocker.startswith("Bootstrap requirements are preview-only")
    ]
    target_ip = _requirement_value(requirements, "planned_management_ip")
    target_prefix = _requirement_value(requirements, "subnet_prefix")
    if target_ip != TARGET_IP:
        blockers.append(f"Planned target IP must be {TARGET_IP}.")
    if target_prefix != TARGET_PREFIX:
        blockers.append(f"Planned target prefix must be {TARGET_PREFIX}.")
    console = CiscoConsoleAdapter().health()
    discovery = console.discovery or {}
    if console.status != "ready" or not discovery.get("effective_path"):
        blockers.append("One selected ready console path is required.")
    if not _prompt_recent():
        blockers.append(f"Prompt readiness must be recent, within {MAX_PROMPT_AGE_MINUTES} minutes.")
    if prompt_state not in {"exec", "setup-wizard"}:
        if prompt_detail == "unknown-no-output":
            blockers.append("Console port opened but no prompt text was captured; bootstrap apply is blocked.")
        elif prompt_state == "login-required":
            blockers.append("Login-required prompt is not supported by console bootstrap planning.")
        elif prompt_state == "config-mode":
            blockers.append("Configuration-mode prompt is not supported by console bootstrap planning.")
        else:
            blockers.append("Prompt state must be exec or setup-wizard for bootstrap planning.")
    return list(dict.fromkeys(blockers))


def _prompt_recent() -> bool:
    prompt_result, checked_at = get_probe_result("cisco-console")
    if not isinstance(prompt_result, dict) or prompt_result.get("action") != "prompt-readiness":
        return False
    if not checked_at:
        return False
    try:
        checked = datetime.fromisoformat(checked_at)
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    return datetime.now(UTC) - checked <= timedelta(minutes=MAX_PROMPT_AGE_MINUTES)


def _flow(prompt_state: str, prompt_detail: str) -> str:
    if prompt_state == "setup-wizard":
        return "setup-wizard-answer-flow"
    if prompt_state == "exec":
        return "direct-exec-config-mode-flow"
    if prompt_state == "login-required":
        return "login-required-blocked-flow"
    if prompt_state == "config-mode":
        return "config-mode-blocked-flow"
    if prompt_detail == "unknown-no-output":
        return "unknown-no-output-blocked-flow"
    return "unsupported-unknown-prompt-flow"


def _prompt_state(prompt_result: dict[str, Any] | None) -> str:
    if not isinstance(prompt_result, dict) or prompt_result.get("action") != "prompt-readiness":
        return "unknown"
    value = prompt_result.get("prompt_state")
    return value if isinstance(value, str) and value else "unknown"


def _prompt_detail(prompt_result: dict[str, Any] | None, prompt_state: str) -> str:
    if prompt_state != "unknown" or not isinstance(prompt_result, dict):
        return prompt_state
    prompt_sample = prompt_result.get("prompt_sample")
    if isinstance(prompt_sample, dict) and prompt_sample.get("captured") is False:
        return "unknown-no-output"
    return "unknown-unrecognized-output"


def _intended_steps(flow: str) -> list[str]:
    steps = [
        f"Confirm the selected console path and target {TARGET_IP}{TARGET_PREFIX}.",
        "Confirm requirements are complete and non-secret.",
    ]
    if flow == "setup-wizard-answer-flow":
        steps.append("Plan setup wizard response path; do not answer unless apply gates pass.")
    elif flow == "direct-exec-config-mode-flow":
        steps.append("Plan entry from exec prompt into the minimal management configuration flow.")
    elif flow == "login-required-blocked-flow":
        steps.append("Block because credential entry is not part of this read-only planning flow.")
    elif flow == "config-mode-blocked-flow":
        steps.append(
            "Block because the console is already in configuration mode and this workflow "
            "does not continue from config mode."
        )
    elif flow == "unknown-no-output-blocked-flow":
        steps.append("Block because the serial port opened but no prompt text was captured.")
    else:
        steps.append("Block because prompt state is unsupported or unknown.")
    steps.extend(
        [
            "Configure the planned management interface/IP shape only after approval.",
            "Leave SSH/SCP and save behavior disabled unless requirements and a future approval explicitly enable them.",
            "Write a redacted post-apply status/report placeholder.",
        ]
    )
    return steps


def _redacted_command_summary(flow: str) -> list[str]:
    if flow == "setup-wizard-answer-flow":
        return [
            "Setup wizard answer path would be previewed separately before any future apply.",
            "No wizard answers are included in this scaffold response.",
        ]
    if flow == "direct-exec-config-mode-flow":
        return [
            "Future guarded flow would enter the minimal management configuration path.",
            "Preview content is plan-only and requires separate exact confirmation before execution.",
        ]
    return [
        "No command preview is actionable for this prompt state.",
        "Resolve blockers before any future guarded preview can be considered.",
    ]


def _blocker_summary(blockers: list[str]) -> dict[str, Any]:
    return {
        "count": len(blockers),
        "has_prompt_blocker": any("Prompt" in blocker or "prompt" in blocker for blocker in blockers),
        "has_target_blocker": any("target" in blocker or "prefix" in blocker for blocker in blockers),
        "has_requirement_blocker": any("required" in blocker.lower() for blocker in blockers),
        "has_apply_gate_blocker": False,
    }


def _command_preview(requirements: dict[str, Any]) -> list[str]:
    management = _object_requirement(requirements, "management_vlan_interface_strategy")
    hostname = _requirement_value(requirements, "hostname") or "<hostname>"
    management_interface = management.get("interface") or "<management-interface>"
    return [
        "! preview only - not executed",
        f"! target {TARGET_IP}{TARGET_PREFIX} netmask {TARGET_NETMASK}",
        "terminal length 0",
        "configure terminal",
        f"hostname {hostname}",
        f"interface {management_interface}",
        f" ip address {TARGET_IP} {TARGET_NETMASK}",
        " no shutdown",
        "end",
        "! configuration save is disabled unless a separate future approval enables it",
    ]


def _requirement_value(requirements: dict[str, Any], key: str) -> str | None:
    item = _object_requirement(requirements, key)
    value = item.get("value")
    return value if isinstance(value, str) else None


def _object_requirement(requirements: dict[str, Any], key: str) -> dict[str, Any]:
    items = requirements.get("requirements")
    if not isinstance(items, dict):
        return {}
    item = items.get(key)
    return item if isinstance(item, dict) else {}


def _requests_destructive_action(value: object) -> bool:
    if not isinstance(value, list):
        return False
    destructive_terms = ("erase", "reload", "delete", "copy", "wipe", "write erase")
    for item in value:
        if isinstance(item, str) and any(term in item.lower() for term in destructive_terms):
            return True
    return False
