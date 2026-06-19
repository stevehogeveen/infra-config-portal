from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.firmware_compliance import get_firmware_compliance

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

UPGRADE_PLAN_REPORT = CODEX_RUN_DIR / "hpe-firmware-upgrade-plan-report.md"
UPGRADE_PLAN_JSON = CODEX_RUN_DIR / "hpe-firmware-upgrade-plan-redacted.json"
UPGRADE_APPLY_REPORT = CODEX_RUN_DIR / "hpe-firmware-upgrade-apply-report.md"
UPGRADE_APPLY_JSON = CODEX_RUN_DIR / "hpe-firmware-upgrade-apply-redacted.json"

UPGRADE_CONFIRM_PHRASE = "run"
HPE_COMPONENTS = {
    "hpe_ilo_firmware": "iLO firmware",
    "hpe_bios_version": "HPE BIOS",
    "hpe_smart_array_firmware": "Smart Array firmware",
}
HPE_UPGRADE_ORDER = (
    "hpe_ilo_firmware",
    "hpe_smart_array_firmware",
    "hpe_bios_version",
)
SPP_PACKAGE_HINTS = {
    "hpe_ilo_firmware": "ilo5_319.fwpkg",
    "hpe_smart_array_firmware": "HPE_SR_Gen10_8.00_A.fwpkg",
    "hpe_bios_version": "U46_2.64_04_01_2026.fwpkg",
}


def build_hpe_firmware_upgrade_plan(
    *,
    refresh_live: bool = False,
    write_report: bool = True,
    component_id: str | None = None,
) -> dict[str, Any]:
    compliance = get_firmware_compliance(refresh_live=refresh_live, scope="hpe")
    selected_component_ids, selection_blockers = _selected_component_ids(component_id)
    components = {
        str(component.get("id")): component
        for component in compliance.get("components", [])
        if str(component.get("id")) in HPE_COMPONENTS
    }
    paths = {
        str(path.get("component_id")): path
        for path in compliance.get("upgrade_paths", [])
        if str(path.get("component_id")) in HPE_COMPONENTS
    }
    steps = [
        _step_for_component(selected_id, components.get(selected_id), paths.get(selected_id))
        for selected_id in selected_component_ids
    ]
    upgrade_steps = [step for step in steps if step["action"] == "upgrade"]
    blockers = _unique([*selection_blockers, *_plan_blockers(compliance, steps)])
    selected_component_label = _selected_component_label(component_id)
    warnings = [
        "Plan only: no firmware package upload, host reset, iLO reset, BIOS change, or controller write was executed.",
        "SPP metadata is used for package selection; the app keeps explicit component order for targeted apply.",
        "Controller firmware is planned before BIOS so the BIOS reboot remains the final disruptive step.",
    ]
    payload = {
        "provider_id": "hpe-firmware-upgrade",
        "action": "hpe-firmware-upgrade-plan",
        "checked_at": _now(),
        "status": "blocked" if blockers else "current" if not upgrade_steps else "ready",
        "message": (
            "HPE firmware is already at the selected baseline. No firmware update is needed."
            if not blockers and not upgrade_steps
            else "HPE firmware upgrade plan generated. No firmware update was executed."
        ),
        "mode": settings.provider_mode,
        "selected_component_id": component_id,
        "selected_component_label": selected_component_label,
        "available_components": [
            {"component_id": key, "label": label}
            for key, label in HPE_COMPONENTS.items()
        ],
        "source_compliance_status": compliance.get("status"),
        "source_compliance_blockers": [str(item) for item in compliance.get("blockers") or [] if item],
        "inventory_source": compliance.get("source_type"),
        "freshness": compliance.get("freshness"),
        "ordered_steps": steps,
        "upgrade_steps": upgrade_steps,
        "blockers": blockers,
        "warnings": warnings,
        "apply_enabled": False,
        "required_confirmations": [UPGRADE_CONFIRM_PHRASE],
        "required_environment": [
            "PROVIDER_MODE=local-lab-readwrite",
            "LAB_ENVIRONMENT=isolated-real-lab",
            "LAB_ACKNOWLEDGE_REAL_HARDWARE=true",
            "LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true",
            "LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true",
            "LAB_ACKNOWLEDGE_LAB_ONLY=true",
            "LAB_ALLOW_FIRMWARE_UPDATES=true",
            "HPE_FIRMWARE_APPLY=true",
            f"HPE_FIRMWARE_CONFIRM={UPGRADE_CONFIRM_PHRASE}",
        ],
        "apply_command": _apply_command(component_id),
        "not_attempted": _not_attempted(),
        "artifacts": {"report": _rel(UPGRADE_PLAN_REPORT), "json": _rel(UPGRADE_PLAN_JSON)},
        "next_safe_action": (
            "Resolve plan blockers, rerun live HPE inventory, then use the guarded apply button or command with explicit firmware flags."
            if blockers or upgrade_steps
            else "No HPE firmware upgrade is required; rerun inventory before future apply work."
        ),
    }
    return _finalize(payload, UPGRADE_PLAN_JSON, UPGRADE_PLAN_REPORT, _plan_markdown, write_report=write_report)


def apply_hpe_firmware_upgrade(*, write_report: bool = True, component_id: str | None = None) -> dict[str, Any]:
    plan = build_hpe_firmware_upgrade_plan(refresh_live=True, write_report=True, component_id=component_id)
    blockers = _apply_blockers(plan)
    current = not blockers and plan.get("status") == "current"
    payload = {
        "provider_id": "hpe-firmware-upgrade",
        "action": "hpe-firmware-upgrade-apply",
        "checked_at": _now(),
        "status": "blocked" if blockers else "current" if current else "ready_for_operator_executor",
        "message": (
            "HPE firmware apply is blocked by missing gates or plan evidence. No firmware update was executed."
            if blockers
            else "Selected HPE firmware is already current. No firmware write is needed."
            if current
            else "All app gates passed. Hand off to the approved HPE SPP/SUM or Redfish package executor before enabling writes."
        ),
        "mode": settings.provider_mode,
        "selected_component_id": plan.get("selected_component_id"),
        "selected_component_label": plan.get("selected_component_label"),
        "plan_status": plan.get("status"),
        "ordered_steps": plan.get("ordered_steps") or [],
        "upgrade_steps": plan.get("upgrade_steps") or [],
        "blockers": blockers,
        "warnings": [
            "No firmware package upload, host reset, iLO reset, BIOS change, or controller write was executed by this command."
            if current
            else "The backend gates are open, but a package executor must report upgrade_writes_attempted=true before the workflow runner can treat an upgrade as successful.",
        ],
        "apply_enabled": not blockers,
        "upgrade_writes_attempted": False,
        "required_confirmations": [UPGRADE_CONFIRM_PHRASE],
        "artifacts": {"report": _rel(UPGRADE_APPLY_REPORT), "json": _rel(UPGRADE_APPLY_JSON)},
        "plan_artifacts": plan.get("artifacts") or {},
        "not_attempted": _not_attempted(),
        "next_safe_action": (
            "Set the listed real-lab and firmware apply gates only during the maintenance window, then attach the approved HPE executor."
            if blockers
            else "No HPE firmware upgrade is required; rerun inventory before future apply work."
            if current
            else "Run the approved HPE executor for the ordered package list, then rerun HPE firmware inventory and compliance."
        ),
    }
    return _finalize(payload, UPGRADE_APPLY_JSON, UPGRADE_APPLY_REPORT, _apply_markdown, write_report=write_report)


def _selected_component_ids(component_id: str | None) -> tuple[tuple[str, ...], list[str]]:
    selected = str(component_id or "").strip()
    if not selected:
        return HPE_UPGRADE_ORDER, []
    if selected not in HPE_COMPONENTS:
        return (), [f"Unsupported HPE firmware component selected: {selected}."]
    return (selected,), []


def _selected_component_label(component_id: str | None) -> str:
    selected = str(component_id or "").strip()
    if not selected:
        return "All HPE firmware components"
    return HPE_COMPONENTS.get(selected, selected)


def _step_for_component(component_id: str, component: dict[str, Any] | None, path: dict[str, Any] | None) -> dict[str, Any]:
    current = _known(path, "current_version") or _known(component, "current_version")
    target = _known(path, "target_version") or _approved_target(component)
    component_status = str((component or {}).get("status") or "unknown")
    path_status = str((path or {}).get("path_status") or "unknown")
    package_available = bool((path or {}).get("package_available"))
    package_name = _known(path, "package_name")
    if component_status == "passed" or path_status == "current":
        action = "skip"
        reason = "Already at the approved baseline."
    elif current and target and package_available:
        action = "upgrade"
        reason = "Current version is below the approved baseline and a matching local package was found."
    else:
        action = "blocked"
        reason = (path or component or {}).get("disabled_reason") or (component or {}).get("reason") or "Missing current, target, or package evidence."
    return {
        "component_id": component_id,
        "label": HPE_COMPONENTS[component_id],
        "action": action,
        "current_version": current,
        "target_version": target,
        "compliance_status": component_status,
        "path_status": path_status,
        "package_available": package_available,
        "package_name": package_name,
        "expected_spp_file": SPP_PACKAGE_HINTS.get(component_id),
        "selected_file_name": _known(path, "selected_file_name"),
        "selected_file_path": _known(path, "selected_file_path"),
        "reboot_required": bool((path or {}).get("reboot_required")),
        "order_note": _order_note(component_id),
        "reason": reason,
    }


def _plan_blockers(compliance: dict[str, Any], steps: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for step in steps:
        if step["action"] != "blocked":
            continue
        blockers.append(f"{step['label']}: {step['reason']}")
    return _unique(blockers)


def _apply_blockers(plan: dict[str, Any]) -> list[str]:
    blockers = []
    if settings.provider_mode != "local-lab-readwrite":
        blockers.append("PROVIDER_MODE=local-lab-readwrite is required for HPE firmware apply.")
    blockers.extend(current_lab_action_policy().action_blockers("ilo.firmware-update", ActionCategory.FIRMWARE_UPDATE))
    if str(os.environ.get("HPE_FIRMWARE_APPLY") or "").lower() != "true":
        blockers.append("HPE_FIRMWARE_APPLY=true is required before any HPE firmware apply.")
    if os.environ.get("HPE_FIRMWARE_CONFIRM") != UPGRADE_CONFIRM_PHRASE:
        blockers.append(f"HPE_FIRMWARE_CONFIRM={UPGRADE_CONFIRM_PHRASE} is required.")
    if plan.get("status") not in {"ready", "current"}:
        blockers.append("HPE firmware upgrade plan is not ready.")
    if not plan.get("upgrade_steps") and plan.get("status") != "current":
        blockers.append("No actionable HPE firmware upgrade steps are available.")
    return _unique(blockers)


def _approved_target(component: dict[str, Any] | None) -> str | None:
    approved = [str(value) for value in (component or {}).get("approved_versions") or [] if value]
    if approved:
        return approved[0]
    required = _known(component, "required_version")
    return required


def _known(payload: dict[str, Any] | None, key: str) -> str | None:
    value = (payload or {}).get(key)
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"unknown", "not reported", "none"}:
        return None
    return text


def _order_note(component_id: str) -> str:
    if component_id == "hpe_ilo_firmware":
        return "Management firmware first when needed; skip if already current."
    if component_id == "hpe_smart_array_firmware":
        return "Controller package before BIOS so storage firmware is staged before the final reboot step."
    return "BIOS last because it is the reboot-driving package for this inventory."


def _apply_command(component_id: str | None = None) -> str:
    component_part = f"HPE_FIRMWARE_COMPONENT_ID={component_id} " if component_id else ""
    return (
        'PROVIDER_MODE=local-lab-readwrite LAB_ALLOW_FIRMWARE_UPDATES=true '
        f'{component_part}HPE_FIRMWARE_APPLY=true HPE_FIRMWARE_CONFIRM="run" '
        "make provider-lab-hpe-firmware-upgrade-apply"
    )


def _not_attempted() -> list[str]:
    return [
        "Redfish firmware package upload",
        "HPE SPP/SUM apply",
        "iLO reset",
        "server reboot",
        "BIOS update",
        "Smart Array firmware update",
    ]


def _finalize(
    payload: dict[str, Any],
    json_path: Path,
    report_path: Path,
    markdown_builder: Any,
    *,
    write_report: bool,
) -> dict[str, Any]:
    sanitized = _sanitize(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
        report_path.write_text(markdown_builder(sanitized), encoding="utf-8")
    return sanitized


def _plan_markdown(payload: dict[str, Any]) -> str:
    return _markdown("HPE Firmware Upgrade Plan", payload)


def _apply_markdown(payload: dict[str, Any]) -> str:
    return _markdown("HPE Firmware Upgrade Apply Report", payload)


def _markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"Checked: {payload.get('checked_at')}",
        f"Status: {payload.get('status')}",
        f"Message: {payload.get('message')}",
        "",
        "## Ordered Steps",
        "",
    ]
    for step in payload.get("ordered_steps") or []:
        lines.extend(
            [
                f"### {step.get('label')}",
                "",
                f"- Action: {step.get('action')}",
                f"- Current: {step.get('current_version') or 'unknown'}",
                f"- Target: {step.get('target_version') or 'unknown'}",
                f"- Package: {step.get('package_name') or 'not selected'}",
                f"- Expected SPP file: {step.get('expected_spp_file') or 'not selected'}",
                f"- Reboot required: {step.get('reboot_required')}",
                f"- Order note: {step.get('order_note')}",
                f"- Reason: {step.get('reason')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Blockers",
            "",
            *[f"- {item}" for item in payload.get("blockers") or ["None"]],
            "",
            "## Warnings",
            "",
            *[f"- {item}" for item in payload.get("warnings") or ["None"]],
            "",
            "## Not Attempted",
            "",
            *[f"- {item}" for item in payload.get("not_attempted") or []],
            "",
        ]
    )
    return "\n".join(lines)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()
