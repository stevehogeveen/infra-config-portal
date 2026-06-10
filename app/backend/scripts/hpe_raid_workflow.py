from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.database import SessionLocal
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.ilo_redfish import ilo_redfish_redaction_values
from app.providers.redaction import redact_sensitive
from app.schemas import HpeRaidApplyCreate, HpeRaidIntentWrite, HpeRaidVolumeIntent
from app.services.hpe_raid import (
    AFTER_RESET_VALIDATION_REPORT,
    APPLY_REPORT,
    PENDING_REPORT,
    RESET_REPORT,
    apply_hpe_raid_plan,
    build_hpe_raid_apply_plan,
    get_hpe_raid_intent,
    get_hpe_raid_plan_preview,
    get_hpe_storage_discovery,
    reset_server_for_raid,
    save_hpe_raid_intent,
    validate_hpe_raid_after_reset,
    write_hpe_raid_pending_report,
    write_hpe_raid_redfish_debug,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
DISCOVERY_REPORT = CODEX_RUN_DIR / "hpe-raid-discovery-report.md"
PLAN_REPORT = CODEX_RUN_DIR / "hpe-raid-plan-report.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="HPE RAID real-lab workflow")
    parser.add_argument(
        "mode",
        choices=("discovery", "plan", "apply", "debug", "pending", "reset", "validate-after-reset"),
    )
    parser.add_argument(
        "--default-esxi-intent",
        action="store_true",
        help="Save a default ESXi RAID1 + RAID6 intent when no RAID intent exists.",
    )
    args = parser.parse_args()

    if args.mode == "discovery":
        return _run_discovery()
    if args.mode == "plan":
        return _run_plan(default_esxi_intent=args.default_esxi_intent)
    if args.mode == "debug":
        return _run_debug()
    if args.mode == "pending":
        return _run_pending()
    if args.mode == "reset":
        return _run_reset()
    if args.mode == "validate-after-reset":
        return _run_validate_after_reset()
    return _run_apply()


def _run_discovery() -> int:
    result = IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
    discovery = get_hpe_storage_discovery()
    report = _sanitize(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "provider_mode": "local-lab-readwrite",
            "probe_status": result.get("status"),
            "probe_message": result.get("message"),
            "discovery": discovery.model_dump(),
            "not_attempted": result.get("not_attempted") or [],
        }
    )
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    DISCOVERY_REPORT.write_text(_discovery_markdown(report), encoding="utf-8")
    print(json.dumps(_discovery_summary(report), indent=2))
    print(f"discovery_report={DISCOVERY_REPORT.relative_to(REPO_ROOT)}")
    return 0 if result.get("status") == "ok" else 1


def _run_plan(*, default_esxi_intent: bool) -> int:
    IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
    with SessionLocal() as session:
        if default_esxi_intent:
            intent = get_hpe_raid_intent(session)
            discovery = get_hpe_storage_discovery()
            if not intent.volumes:
                save_hpe_raid_intent(session, _default_esxi_intent(discovery.model_dump()))
        preview = get_hpe_raid_plan_preview(session)
        apply_plan = build_hpe_raid_apply_plan(session)
    report = _sanitize(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "provider_mode": "local-lab-readwrite",
            "preview": preview.model_dump(),
            "apply_plan": apply_plan,
        }
    )
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_REPORT.write_text(_plan_markdown(report), encoding="utf-8")
    print(json.dumps(_plan_summary(report), indent=2))
    print(f"plan_report={PLAN_REPORT.relative_to(REPO_ROOT)}")
    return 0 if preview.status != "blocked" else 1


def _run_apply() -> int:
    confirmation = os.getenv("HPE_RAID_APPLY_CONFIRM", "")
    with SessionLocal() as session:
        result = apply_hpe_raid_plan(
            session,
            HpeRaidApplyCreate(confirmation_phrase=confirmation),
        )
    print(json.dumps(_sanitize(result), indent=2))
    print(f"apply_report={APPLY_REPORT.relative_to(REPO_ROOT)}")
    if result.get("status") == "succeeded":
        return 0
    return 2


def _run_debug() -> int:
    with SessionLocal() as session:
        report = write_hpe_raid_redfish_debug(session)
    print(json.dumps(_sanitize(_debug_summary(report)), indent=2))
    return 0


def _run_pending() -> int:
    with SessionLocal() as session:
        report = write_hpe_raid_pending_report(session)
    print(json.dumps(_sanitize(_pending_summary(report)), indent=2))
    print(f"pending_report={PENDING_REPORT.relative_to(REPO_ROOT)}")
    return 0


def _run_reset() -> int:
    result = reset_server_for_raid()
    print(json.dumps(_sanitize(_reset_summary(result)), indent=2))
    print(f"reset_report={RESET_REPORT.relative_to(REPO_ROOT)}")
    return 0 if result.get("status") == "reset-requested" else 2


def _run_validate_after_reset() -> int:
    with SessionLocal() as session:
        result = validate_hpe_raid_after_reset(session)
    print(json.dumps(_sanitize(_validation_summary(result)), indent=2))
    print(f"after_reset_validation_report={AFTER_RESET_VALIDATION_REPORT.relative_to(REPO_ROOT)}")
    return 0 if result.get("status") == "succeeded" else 1


def _default_esxi_intent(discovery: dict[str, Any]) -> HpeRaidIntentWrite:
    drives = discovery.get("physical_drives") if isinstance(discovery.get("physical_drives"), list) else []
    bays = [str(drive.get("bay_id") or drive.get("Location") or "") for drive in drives]
    bays = [bay for bay in bays if bay]
    volumes = []
    if len(bays) >= 2:
        volumes.append(
            HpeRaidVolumeIntent(
                name="ESXi-OS",
                purpose="ESXi install",
                raid_level="RAID1",
                drive_bays=bays[:2],
                size_policy="max",
                bootable=True,
            )
        )
    if len(bays) >= 6:
        datastore_bays = bays[2:]
        data_bays = datastore_bays[:5] if len(datastore_bays) > 5 else datastore_bays
        spare_bays = datastore_bays[5:] if len(datastore_bays) > 5 else []
        volumes.append(
            HpeRaidVolumeIntent(
                name="VM-Datastore",
                purpose="VM datastore",
                raid_level="RAID6",
                drive_bays=data_bays,
                spare_bays=spare_bays,
                spare_rebuild_mode="Dedicated" if spare_bays else None,
                size_policy="max",
                bootable=False,
            )
        )
    return HpeRaidIntentWrite(
        controller_ref=None,
        wipe_existing_logical_drives=True,
        volumes=volumes,
        notes="Default ESXi layout generated by provider-lab-hpe-raid-plan.",
    )


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(
        payload,
        ilo_redfish_redaction_values(),
    )


def _discovery_summary(report: dict[str, Any]) -> dict[str, Any]:
    discovery = report["discovery"]
    return {
        "checked_at": report["checked_at"],
        "provider_mode": report["provider_mode"],
        "status": "completed" if report.get("probe_status") == "ok" else "blocked",
        "blockers": [] if report.get("probe_status") == "ok" else [report.get("probe_message") or "HPE RAID discovery failed."],
        "storage_inventory_available": discovery.get("storage_inventory_available"),
        "controller_count": len(discovery.get("controllers") or []),
        "physical_drive_count": len(discovery.get("physical_drives") or []),
        "logical_drive_count": len(discovery.get("logical_drives") or []),
        "report": str(DISCOVERY_REPORT.relative_to(REPO_ROOT)),
    }


def _plan_summary(report: dict[str, Any]) -> dict[str, Any]:
    preview = report["preview"]
    apply_plan = report["apply_plan"]
    return {
        "checked_at": report["checked_at"],
        "provider_mode": report["provider_mode"],
        "status": preview.get("status"),
        "planned_volume_count": (preview.get("planned_layout") or {}).get("volume_count"),
        "destructive_actions_requested": preview.get("destructive_actions_requested"),
        "raid_apply_available": apply_plan.get("apply_enabled"),
        "confirmation_phrase": apply_plan.get("confirmation_phrase"),
        "report": str(PLAN_REPORT.relative_to(REPO_ROOT)),
    }


def _debug_summary(report: dict[str, Any]) -> dict[str, Any]:
    comparison = report.get("comparison") or {}
    error = report.get("redfish_error") or {}
    return {
        "checked_at": report.get("checked_at"),
        "patch_run": False,
        "current_get_status": (report.get("current_get") or {}).get("status_code"),
        "settings_get_status": (report.get("settings_get") or {}).get("status_code"),
        "last_apply_http_status": error.get("status_code"),
        "last_apply_error_code": error.get("code"),
        "diagnosis": comparison.get("diagnosis"),
        "artifacts": report.get("artifacts"),
    }


def _pending_summary(report: dict[str, Any]) -> dict[str, Any]:
    pending = report.get("pending") or {}
    return {
        "checked_at": report.get("checked_at"),
        "current_get_status": (report.get("current_get") or {}).get("status_code"),
        "settings_get_status": (report.get("settings_get") or {}).get("status_code"),
        "pending_config_exists": pending.get("pending_config_exists"),
        "pending_matches_expected": pending.get("pending_matches_expected"),
        "live_matches_expected": pending.get("live_matches_expected"),
        "reset_required": pending.get("reset_required"),
        "next_safe_action": report.get("next_safe_action"),
    }


def _reset_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "status": result.get("status"),
        "message": result.get("message"),
        "reset_status_code": (result.get("reset") or {}).get("status_code"),
        "blockers": result.get("blockers") or [],
        "next_safe_action": result.get("next_safe_action"),
    }


def _validation_summary(result: dict[str, Any]) -> dict[str, Any]:
    validation = result.get("validation") or {}
    return {
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "status": result.get("status"),
        "message": result.get("message"),
        "reachable": (result.get("wait") or {}).get("reachable"),
        "matches_saved_intent": validation.get("matches"),
        "mismatches": validation.get("mismatches") or [],
        "next_safe_action": result.get("next_safe_action"),
    }


def _discovery_markdown(report: dict[str, Any]) -> str:
    discovery = report["discovery"]
    lines = [
        "# HPE RAID Discovery Report",
        "",
        f"Date: {report['checked_at']}",
        f"Mode: `{report['provider_mode']}`",
        f"Probe status: {report.get('probe_status')}",
        f"Probe message: {report.get('probe_message')}",
        "",
        "## Summary",
        "",
        f"- Storage inventory available: {discovery.get('storage_inventory_available')}",
        f"- Controller count: {len(discovery.get('controllers') or [])}",
        f"- Physical drive count: {len(discovery.get('physical_drives') or [])}",
        f"- Logical drive count: {len(discovery.get('logical_drives') or [])}",
        "",
        "## Blockers",
        "",
    ]
    if report.get("probe_status") == "ok":
        lines.append("- none")
    else:
        lines.append(f"- {report.get('probe_message') or 'HPE RAID discovery failed.'}")
    lines.extend(
        [
            "",
        "## Current Layout",
        "",
        *_layout_lines(discovery),
        "",
        "## Not Attempted",
        "",
        ]
    )
    lines.extend([f"- {item}" for item in report.get("not_attempted", [])] or ["- storage writes"])
    lines.append("")
    return "\n".join(lines)


def _plan_markdown(report: dict[str, Any]) -> str:
    preview = report["preview"]
    apply_plan = report["apply_plan"]
    lines = [
        "# HPE RAID Plan Report",
        "",
        f"Date: {report['checked_at']}",
        f"Mode: `{report['provider_mode']}`",
        f"Status: {preview.get('status')}",
        "",
        "## Current Layout",
        "",
        *_layout_lines((preview.get("current_layout") or {})),
        "",
        "## Planned Layout",
        "",
    ]
    planned = preview.get("planned_layout") or {}
    lines.append(f"- Summary: {planned.get('summary') or 'none'}")
    for volume in planned.get("volumes") or []:
        lines.append(
            f"- {volume.get('name')}: raid={volume.get('raid_level')} bays={', '.join(volume.get('drive_bays') or [])} estimated_usable_bytes={volume.get('estimated_usable_capacity_bytes')}"
        )
    lines.extend(
        [
            "",
            "## Apply Gate",
            "",
            f"- Apply available: {apply_plan.get('apply_enabled')}",
            f"- Mechanism: {apply_plan.get('apply_mechanism')}",
            f"- Confirmation phrase: `{apply_plan.get('confirmation_phrase')}`",
            "",
            "## Blockers",
            "",
        ]
    )
    lines.extend([f"- {item}" for item in apply_plan.get("blockers", [])] or ["- none"])
    lines.append("")
    return "\n".join(lines)


def _layout_lines(discovery: dict[str, Any]) -> list[str]:
    lines = []
    for controller in discovery.get("controllers") or []:
        lines.append(
            f"- Controller: {controller.get('Model') or controller.get('Name')} location={controller.get('Location')} health={_health(controller)}"
        )
    for drive in discovery.get("physical_drives") or []:
        lines.append(
            f"- Physical drive: {drive.get('display_label') or drive.get('Location')} capacity={drive.get('capacity_label') or drive.get('CapacityGB')} media={drive.get('media_type') or drive.get('MediaType')} health={drive.get('health') or _health(drive)}"
        )
    for drive in discovery.get("logical_drives") or []:
        lines.append(
            f"- Logical drive: {drive.get('display_label') or drive.get('LogicalDriveName')} raid={drive.get('raid_level') or drive.get('RAIDType')} capacity={drive.get('capacity_label') or drive.get('CapacityMiB')} health={drive.get('health') or _health(drive)}"
        )
    return lines or ["- none"]


def _health(payload: dict[str, Any]) -> str:
    status = payload.get("Status")
    if isinstance(status, dict):
        return str(status.get("Health") or status.get("State") or "unknown")
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
