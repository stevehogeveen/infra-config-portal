from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.netapp_address_plan import (
    ADDRESS_VALIDATION_REPORT,
    CODEX_RUN_DIR,
    PROVIDER_ID,
    REPO_ROOT,
    build_netapp_address_remediation_plan,
)

FACTORY_RESET_PLAN_REPORT = CODEX_RUN_DIR / "netapp-factory-reset-plan-report.md"
FACTORY_RESET_PLAN_JSON = CODEX_RUN_DIR / "netapp-factory-reset-plan-redacted.json"
FACTORY_RESET_APPLY_REPORT = CODEX_RUN_DIR / "netapp-factory-reset-apply-report.md"
FACTORY_RESET_APPLY_JSON = CODEX_RUN_DIR / "netapp-factory-reset-apply-redacted.json"
FACTORY_RESET_VALIDATION_REPORT = CODEX_RUN_DIR / "netapp-factory-reset-validation-report.md"
FACTORY_RESET_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-factory-reset-validation-redacted.json"

FACTORY_RESET_CONFIRM_PHRASE = "FACTORY RESET NETAPP"


def build_netapp_factory_reset_preview(*, write_report: bool = True) -> dict[str, Any]:
    address_plan = build_netapp_address_remediation_plan(write_report=False)
    current = address_plan.get("current_targets") if isinstance(address_plan.get("current_targets"), dict) else {}
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "factory-reset-preview",
        "checked_at": _now(),
        "status": "preview_only",
        "message": "NetApp factory reset preview generated. No destructive command was sent.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "destructive": True,
        "confirmation_phrase": FACTORY_RESET_CONFIRM_PHRASE,
        "current_state": {
            "cluster_mgmt": current.get("cluster_mgmt"),
            "node_a_mgmt": current.get("node_a_mgmt"),
            "node_b_mgmt": current.get("node_b_mgmt"),
            "svm_mgmt": current.get("svm_mgmt"),
            "nfs_lifs": current.get("nfs_lifs") or [],
            "node_health": (address_plan.get("console_facts") or {}).get("node_health"),
            "cluster_ha_warning": (address_plan.get("console_facts") or {}).get("cluster_ha_warning"),
        },
        "target_lab_setup_after_reset": address_plan.get("planned_targets"),
        "what_it_resets": [
            "ONTAP cluster configuration",
            "SVMs, LIFs, NFS services, volumes, and export policies",
            "Cluster/node management configuration",
            "Existing data and storage presentation configuration",
        ],
        "guardrails": _required_flags(),
        "practicality": {
            "recommended_now": False,
            "reason": "The ONTAP shell is reachable and most planned addresses were remediated; the remaining blocker is X20-01 node health, not a setup-wizard absence.",
        },
        "blockers": [],
        "warnings": [
            "Preview only. No boot menu, wipeconfig, reset, reboot, takeover, giveback, network, storage, or upgrade command was sent.",
            "Factory reset remains a last-resort recovery path, not a casual button.",
        ],
        "artifacts": {
            "report": _rel(FACTORY_RESET_PLAN_REPORT),
            "json": _rel(FACTORY_RESET_PLAN_JSON),
            "address_validation": _rel(ADDRESS_VALIDATION_REPORT),
        },
        "next_safe_action": "Use HA/node remediation first; factory reset should be considered only if node repair and readdress cannot recover the lab.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(FACTORY_RESET_PLAN_JSON, FACTORY_RESET_PLAN_REPORT, sanitized, _preview_markdown)
    return sanitized


def apply_netapp_factory_reset(*, write_report: bool = True) -> dict[str, Any]:
    preview = build_netapp_factory_reset_preview(write_report=True)
    gates = _apply_gates()
    blocked = bool(gates["blockers"])
    status = "blocked" if blocked else "not_implemented"
    payload = {
        **preview,
        "action": "factory-reset-apply",
        "checked_at": _now(),
        "status": status,
        "apply_enabled": not blocked,
        "message": (
            "NetApp factory reset apply was refused before any destructive command."
            if blocked
            else "Factory reset gates passed, but no guarded NetApp wipe/reset executor is implemented in this app."
        ),
        "flag_state": gates["flag_state"],
        "apply": {
            "destructive_commands_attempted": False,
            "console_writes_attempted": False,
            "reason": "No implemented factory-reset executor exists." if not blocked else "Apply gates blocked.",
        },
        "blockers": gates["blockers"],
        "artifacts": {
            "report": _rel(FACTORY_RESET_APPLY_REPORT),
            "json": _rel(FACTORY_RESET_APPLY_JSON),
            "preview_report": _rel(FACTORY_RESET_PLAN_REPORT),
        },
        "next_safe_action": "Repair X20-01 or use a manually attended NetApp recovery process outside the app if factory reset becomes necessary.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(FACTORY_RESET_APPLY_JSON, FACTORY_RESET_APPLY_REPORT, sanitized, _apply_markdown)
    return sanitized


def validate_netapp_factory_reset(*, write_report: bool = True) -> dict[str, Any]:
    address_plan = build_netapp_address_remediation_plan(write_report=False)
    console = address_plan.get("console_facts") if isinstance(address_plan.get("console_facts"), dict) else {}
    reset_state = console.get("identified_state") in {"cluster_setup_wizard", "node_setup_wizard"}
    blockers = [] if reset_state else ["NetApp is not in factory setup wizard state after reset."]
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "factory-reset-validation",
        "checked_at": _now(),
        "status": "ready" if reset_state else "blocked",
        "message": "NetApp factory reset validation completed from console state.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "identified_state": console.get("identified_state"),
        "blockers": blockers,
        "warnings": ["Validation is read-only; no factory reset command was sent."],
        "artifacts": {
            "report": _rel(FACTORY_RESET_VALIDATION_REPORT),
            "json": _rel(FACTORY_RESET_VALIDATION_JSON),
        },
        "next_safe_action": "Run NetApp setup preview/apply only after the console is in setup wizard state.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(FACTORY_RESET_VALIDATION_JSON, FACTORY_RESET_VALIDATION_REPORT, sanitized, _validation_markdown)
    return sanitized


def _apply_gates() -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "lab_allow_factory_reset": policy.allow_factory_reset,
        "netapp_factory_reset_apply": os.getenv("NETAPP_FACTORY_RESET_APPLY") == "true",
        "netapp_factory_reset_confirm": os.getenv("NETAPP_FACTORY_RESET_CONFIRM") == FACTORY_RESET_CONFIRM_PHRASE,
        "netapp_factory_reset_executor_enabled": os.getenv("NETAPP_FACTORY_RESET_EXECUTOR_ENABLED") == "true",
    }
    blockers = []
    blockers.extend(policy.action_blockers("netapp.factory-reset", ActionCategory.FACTORY_RESET))
    if not flag_state["netapp_factory_reset_apply"]:
        blockers.append("NETAPP_FACTORY_RESET_APPLY=true is required.")
    if not flag_state["netapp_factory_reset_confirm"]:
        blockers.append(f'NETAPP_FACTORY_RESET_CONFIRM="{FACTORY_RESET_CONFIRM_PHRASE}" is required.')
    if not flag_state["netapp_factory_reset_executor_enabled"]:
        blockers.append("NETAPP_FACTORY_RESET_EXECUTOR_ENABLED=true is required, but the executor is intentionally not implemented.")
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "LAB_ALLOW_FACTORY_RESET=true",
        "NETAPP_FACTORY_RESET_APPLY=true",
        f'NETAPP_FACTORY_RESET_CONFIRM="{FACTORY_RESET_CONFIRM_PHRASE}"',
        "NETAPP_FACTORY_RESET_EXECUTOR_ENABLED=true",
    ]


def _preview_markdown(payload: dict[str, Any]) -> str:
    return _markdown("NetApp Factory Reset Preview", payload)


def _apply_markdown(payload: dict[str, Any]) -> str:
    return _markdown("NetApp Factory Reset Apply", payload)


def _validation_markdown(payload: dict[str, Any]) -> str:
    return _markdown("NetApp Factory Reset Validation", payload)


def _markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Guardrails"])
    lines.extend(f"- `{item}`" for item in payload.get("guardrails") or _required_flags())
    lines.extend(["", "## Safety", "- No destructive NetApp factory-reset command was sent."])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown_builder(payload), encoding="utf-8")


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
