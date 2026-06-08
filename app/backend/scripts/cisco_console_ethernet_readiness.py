from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.redaction import redact_sensitive
from app.core.config import settings
from app.services.cisco_console_bootstrap import build_cisco_console_bootstrap_plan
from app.services.cisco_setup_readiness import get_cisco_setup_readiness
from app.services.hpe_raid import REPO_ROOT

REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-console-ethernet-readiness-report.md"
DETAILS = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-console-ethernet-readiness-redacted.json"


def main() -> int:
    console_adapter = CiscoConsoleAdapter(settings.provider_mode)
    ansible_adapter = CiscoAnsibleAdapter(settings.provider_mode)
    console_status = console_adapter.health()
    prompt_result = None
    if console_status.status == "ready":
        prompt_result = console_adapter.prompt_readiness()
    readiness = get_cisco_setup_readiness(
        console_status=console_adapter.health(),
        ansible_status=ansible_adapter.health(),
    )
    bootstrap_plan = build_cisco_console_bootstrap_plan()
    payload = _sanitize(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "status": _overall_status(readiness, prompt_result),
            "console_prompt_readiness": prompt_result,
            "setup_readiness": readiness,
            "console_bootstrap_plan": bootstrap_plan,
            "blockers": _blockers(readiness, prompt_result),
            "warnings": readiness.get("warnings") or [],
            "not_attempted": [
                "configuration mode",
                "write memory",
                "reload",
                "copy or erase",
                "VLAN/interface/user/password changes",
                "SSH/SCP enablement",
                "running-config backup",
            ],
        }
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    DETAILS.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(_summary(payload), indent=2))
    return 0 if payload["status"] in {"ready", "blocked"} else 1


def _overall_status(readiness: dict[str, Any], prompt_result: dict[str, Any] | None) -> str:
    console = readiness.get("console") or {}
    if console.get("status") != "ready":
        return "blocked"
    if not prompt_result or prompt_result.get("prompt_state") != "exec":
        return "blocked"
    ethernet = readiness.get("ethernet_readiness") or {}
    return "ready" if ethernet.get("ready") else "blocked"


def _blockers(readiness: dict[str, Any], prompt_result: dict[str, Any] | None) -> list[str]:
    blockers = list(readiness.get("blockers") or [])
    if not prompt_result:
        blockers.append("Console prompt readiness did not run.")
    elif prompt_result.get("prompt_state") != "exec":
        blockers.extend(prompt_result.get("blockers") or ["Console prompt was not identified as an exec prompt."])
    ethernet = readiness.get("ethernet_readiness") or {}
    if not ethernet.get("ready"):
        blockers.append("Cisco Ethernet management is not configured; SSH/SCP readiness requires console bootstrap.")
    return list(dict.fromkeys(blockers))


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("setup_readiness") or {}
    console = readiness.get("console") or {}
    ethernet = readiness.get("ethernet_readiness") or {}
    prompt = payload.get("console_prompt_readiness") or {}
    return {
        "checked_at": payload.get("checked_at"),
        "status": payload.get("status"),
        "console_status": console.get("status"),
        "selected_console": console.get("selected_path"),
        "prompt_state": prompt.get("prompt_state"),
        "prompt_captured": (prompt.get("prompt_sample") or {}).get("captured") if isinstance(prompt.get("prompt_sample"), dict) else None,
        "ethernet_ready": ethernet.get("ready"),
        "management_configured": ethernet.get("management_configured"),
        "blockers": payload.get("blockers") or [],
        "report": str(REPORT.relative_to(REPO_ROOT)),
        "details": str(DETAILS.relative_to(REPO_ROOT)),
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = _summary(payload)
    lines = [
        "# Cisco Console And Ethernet Readiness Report",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- {item}" for item in payload.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in payload.get("warnings") or []] or ["- none"])
    lines.extend(["", "## Not Attempted", ""])
    lines.extend([f"- {item}" for item in payload.get("not_attempted") or []])
    lines.extend(["", "## Redacted Details", "", f"- JSON: {DETAILS.relative_to(REPO_ROOT)}", ""])
    return "\n".join(lines)


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(
        payload,
        [
            settings.cisco_console_port,
            settings.cisco_target_ip,
            settings.cisco_test_username,
            settings.cisco_test_password,
            settings.cisco_enable_password,
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
