from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import HpeRaidIntent
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.ilo_redfish import PROVIDER_ID
from app.providers.ilo_redfish import IloRedfishAdapter, _base_url
from app.providers.probe_cache import get_probe_result
from app.providers.redaction import redact_sensitive
from app.schemas import (
    HpeRaidApplyCreate,
    HpeRaidIntentRead,
    HpeRaidIntentWrite,
    HpeRaidPlanPreviewRead,
    HpeStorageDiscoveryRead,
)

CONFIRMATION_PHRASE = "APPLY HPE RAID PLAN"
RESET_CONFIRMATION_PHRASE = "RESET SERVER FOR HPE RAID APPLY"
APPLY_ACTION_ID = "ilo-redfish.hpe-raid-apply"
RESET_ACTION_ID = "ilo-redfish.hpe-raid-reset"
VALIDATE_AFTER_RESET_ACTION_ID = "ilo-redfish.hpe-raid-validate-after-reset"
SYSTEM_PATH = "/redfish/v1/systems/1/"
SMART_STORAGE_CONFIG_PATH = "/redfish/v1/systems/1/smartstorageconfig/"
SMART_STORAGE_SETTINGS_PATH = "/redfish/v1/systems/1/smartstorageconfig/settings/"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
APPLY_REPORT = CODEX_RUN_DIR / "hpe-raid-apply-report.md"
APPLY_STATE = CODEX_RUN_DIR / "hpe-raid-apply-state.json"
REDFISH_DEBUG_REPORT = CODEX_RUN_DIR / "hpe-raid-redfish-debug-report.md"
APPLY_PAYLOAD_REDACTED = CODEX_RUN_DIR / "hpe-raid-apply-payload-redacted.json"
SMARTSTORAGE_CURRENT = CODEX_RUN_DIR / "hpe-smartstorage-current.json"
SMARTSTORAGE_SETTINGS = CODEX_RUN_DIR / "hpe-smartstorage-settings.json"
PENDING_REPORT = CODEX_RUN_DIR / "hpe-raid-pending-report.md"
RESET_REPORT = CODEX_RUN_DIR / "hpe-raid-reset-report.md"
AFTER_RESET_VALIDATION_REPORT = CODEX_RUN_DIR / "hpe-raid-after-reset-validation-report.md"

DISABLED_RAID_ACTIONS = [
    "drive wipe",
    "logical drive delete",
    "array/controller initialize",
    "RAID logical drive create",
    "boot volume selection",
    "storage controller write",
]


def get_hpe_storage_discovery() -> HpeStorageDiscoveryRead:
    probe, probe_time = get_probe_result(PROVIDER_ID)
    if not isinstance(probe, dict):
        return HpeStorageDiscoveryRead(
            provider_id=PROVIDER_ID,
            source="cached iLO Redfish probe",
            last_probe_time=None,
            next_safe_action="Run the HPE iLO GET-only probe before planning RAID layout.",
            blockers=["No cached iLO Redfish probe result is available."],
        )

    storage = probe.get("storage") if isinstance(probe.get("storage"), dict) else {}
    controllers = _list(storage.get("controllers"))
    physical_drives = [_drive_for_ui(drive) for drive in _list(storage.get("physical_drives"))]
    logical_drives = [_logical_for_ui(drive) for drive in _list(storage.get("logical_drives"))]
    systems = _list(probe.get("systems"))
    warnings = [*_string_list(storage.get("warnings")), *_string_list(probe.get("warnings"))]
    blockers = _string_list(probe.get("blockers"))
    inventory_available = bool(controllers or physical_drives or logical_drives)

    if not inventory_available:
        blockers.append("Cached iLO probe does not include HPE storage inventory.")

    return HpeStorageDiscoveryRead(
        provider_id=PROVIDER_ID,
        source="cached iLO Redfish probe",
        last_probe_time=probe_time,
        storage_inventory_available=inventory_available,
        server=_server_summary(systems),
        controllers=controllers,
        physical_drives=physical_drives,
        logical_drives=logical_drives,
        warnings=_unique(warnings),
        blockers=_unique(blockers),
        next_safe_action=(
            "Review discovered drives and save a plan-only RAID intent."
            if inventory_available
            else "Run the HPE iLO GET-only probe and confirm Smart Array storage inventory is returned."
        ),
    )


def get_hpe_raid_intent(session: Session) -> HpeRaidIntentRead:
    record = session.get(HpeRaidIntent, PROVIDER_ID)
    if record is None:
        return _intent_read(HpeRaidIntentWrite())
    try:
        payload = HpeRaidIntentWrite.model_validate(record.intent_json)
    except ValueError:
        return _intent_read(HpeRaidIntentWrite())
    return _intent_read(payload, created_at=record.created_at, updated_at=record.updated_at)


def save_hpe_raid_intent(
    session: Session,
    payload: HpeRaidIntentWrite,
) -> HpeRaidIntentRead:
    record = session.get(HpeRaidIntent, PROVIDER_ID)
    if record is None:
        record = HpeRaidIntent(provider_id=PROVIDER_ID, intent_json=payload.model_dump())
        session.add(record)
    else:
        record.intent_json = payload.model_dump()

    session.commit()
    session.refresh(record)
    return _intent_read(
        HpeRaidIntentWrite.model_validate(record.intent_json),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_hpe_raid_plan_preview(session: Session) -> HpeRaidPlanPreviewRead:
    discovery = get_hpe_storage_discovery()
    intent = get_hpe_raid_intent(session)
    validation = _validate_intent(intent, discovery)
    destructive_requested = bool(intent.wipe_existing_logical_drives or intent.volumes)
    current_logical_count = len(discovery.logical_drives)
    planned_volumes = [_planned_volume(volume, discovery) for volume in intent.volumes]
    blockers = [*discovery.blockers, *validation["blockers"]]
    warnings = [*discovery.warnings, *validation["warnings"]]

    if not intent.volumes:
        warnings.append("No RAID volumes are saved in desired intent.")
    if intent.volumes and current_logical_count and not intent.wipe_existing_logical_drives:
        warnings.append(
            "Existing logical drives are present; creating a replacement layout would require explicit wipe/delete intent."
        )
    if intent.wipe_existing_logical_drives:
        warnings.append("Saved intent requests destructive wipe/delete planning. Execution remains disabled.")

    status = "blocked" if blockers else ("warning" if warnings else "planned")

    return HpeRaidPlanPreviewRead(
        provider_id=PROVIDER_ID,
        status=status,
        apply_enabled=False,
        destructive_actions_requested=destructive_requested,
        destructive_actions_enabled=False,
        current_layout=discovery,
        desired_intent=intent,
        planned_layout={
            "controller_ref": intent.controller_ref,
            "volume_count": len(planned_volumes),
            "volumes": planned_volumes,
            "summary": _plan_summary(intent, discovery, planned_volumes),
        },
        impact={
            "existing_logical_drive_count": current_logical_count,
            "logical_drives_to_delete": current_logical_count if intent.wipe_existing_logical_drives else 0,
            "physical_drives_selected": sorted(_selected_bays(intent)),
            "physical_drives_not_selected": _unselected_bays(intent, discovery),
            "wipe_required_for_replacement_layout": bool(intent.volumes and current_logical_count),
            "no_storage_write_will_run": True,
        },
        blockers=_unique(blockers),
        warnings=_unique(warnings),
        disabled_actions=DISABLED_RAID_ACTIONS,
        next_safe_action=(
            "Resolve blockers, then review the plan with a second operator before any future guarded apply lane."
            if blockers
            else "Review current layout versus desired layout. Apply remains disabled."
        ),
    )


def build_hpe_raid_apply_plan(session: Session) -> dict[str, Any]:
    preview = get_hpe_raid_plan_preview(session)
    payload = _redfish_settings_payload(preview.desired_intent)
    blockers = _apply_blockers(preview, confirmation_phrase=CONFIRMATION_PHRASE)
    last_apply = _last_apply_state()
    return {
        "provider_id": PROVIDER_ID,
        "status": "ready" if not blockers else "blocked",
        "message": (
            "HPE RAID apply is available through Redfish SmartStorageConfig settings."
            if not blockers
            else "HPE RAID apply is blocked until all destructive gates are satisfied."
        ),
        "apply_enabled": not blockers,
        "apply_mechanism": "redfish-smartstorageconfig-settings",
        "settings_path": SMART_STORAGE_SETTINGS_PATH,
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "planned_payload": payload,
        "payload_redacted": True,
        "last_apply": last_apply,
        "blockers": blockers,
        "warnings": preview.warnings,
        "disabled_actions": [] if not blockers else DISABLED_RAID_ACTIONS,
        "next_safe_action": (
            f"Run `HPE_RAID_ALLOW_DESTRUCTIVE=true HPE_RAID_APPLY_CONFIRM=\"{CONFIRMATION_PHRASE}\" make provider-lab-hpe-raid-apply` from the repo root."
            if not blockers
            else "Save a valid RAID intent, enable the destructive env gate, and use the exact confirmation phrase from a terminal."
        ),
    }


def apply_hpe_raid_plan(
    session: Session,
    payload: HpeRaidApplyCreate,
) -> dict[str, Any]:
    IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
    preview = get_hpe_raid_plan_preview(session)
    blockers = _apply_blockers(preview, confirmation_phrase=payload.confirmation_phrase)
    started_at = datetime.now(UTC).isoformat()
    if blockers:
        result = {
            "provider_id": PROVIDER_ID,
            "status": "blocked",
            "message": "HPE RAID apply did not run.",
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "apply_enabled": False,
            "blockers": blockers,
            "warnings": preview.warnings,
            "before": _layout_summary(preview.current_layout),
            "after": None,
            "redfish_result": None,
            "not_attempted": DISABLED_RAID_ACTIONS,
        }
        _write_apply_artifacts(result)
        return result

    before = get_hpe_storage_discovery()
    redfish_payload = _redfish_settings_payload(preview.desired_intent)
    redfish_result: dict[str, Any] = {}
    status = "failed"
    message = "HPE RAID apply failed."
    try:
        response_payload = _patch_smartstorage_settings(redfish_payload)
        redfish_result = response_payload
        probe = IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
        after = get_hpe_storage_discovery()
        if 200 <= int(response_payload.get("status_code", 0)) < 300:
            status = "succeeded"
            message = "HPE RAID apply request was accepted by Redfish SmartStorageConfig settings."
        else:
            after = get_hpe_storage_discovery()
    except Exception as exc:  # pragma: no cover - defensive real-lab path
        after = get_hpe_storage_discovery()
        redfish_result = {"error_class": type(exc).__name__, "error": str(exc)}
        probe = None

    result = {
        "provider_id": PROVIDER_ID,
        "status": status,
        "message": message,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "apply_enabled": False,
        "blockers": [],
        "warnings": [
            "RAID apply is destructive; verify iLO SmartStorage pending settings and reboot requirements manually.",
        ],
        "before": _layout_summary(before),
        "after": _layout_summary(after),
        "redfish_payload": redfish_payload,
        "redfish_result": redfish_result,
        "post_apply_probe_status": probe.get("status") if isinstance(probe, dict) else None,
        "not_attempted": [],
    }
    _write_apply_artifacts(result)
    return result


def write_hpe_raid_redfish_debug(session: Session) -> dict[str, Any]:
    preview = get_hpe_raid_plan_preview(session)
    redfish_payload = _redfish_settings_payload(preview.desired_intent)
    current = _get_smartstorage_resource(SMART_STORAGE_CONFIG_PATH)
    settings_response = _get_smartstorage_resource(SMART_STORAGE_SETTINGS_PATH)
    last_apply = _last_apply_full_state()

    sanitized_payload = _sanitize_artifact(redfish_payload)
    sanitized_current = _sanitize_artifact(_resource_body_or_error(current))
    sanitized_settings = _sanitize_artifact(_resource_body_or_error(settings_response))
    sanitized_last_apply = _sanitize_artifact(last_apply)
    error_details = _redfish_error_details(
        sanitized_last_apply.get("redfish_result")
        if isinstance(sanitized_last_apply.get("redfish_result"), dict)
        else {}
    )
    comparison = _redfish_debug_comparison(
        sanitized_payload,
        sanitized_current,
        sanitized_settings,
        error_details,
    )

    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_id": PROVIDER_ID,
        "provider_mode": settings.provider_mode,
        "patch_not_run": True,
        "current_get": _response_summary(current),
        "settings_get": _response_summary(settings_response),
        "last_apply": sanitized_last_apply,
        "redfish_error": error_details,
        "comparison": comparison,
        "artifacts": {
            "debug_report": str(REDFISH_DEBUG_REPORT.relative_to(REPO_ROOT)),
            "payload": str(APPLY_PAYLOAD_REDACTED.relative_to(REPO_ROOT)),
            "current": str(SMARTSTORAGE_CURRENT.relative_to(REPO_ROOT)),
            "settings": str(SMARTSTORAGE_SETTINGS.relative_to(REPO_ROOT)),
        },
    }

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    APPLY_PAYLOAD_REDACTED.write_text(json.dumps(sanitized_payload, indent=2), encoding="utf-8")
    SMARTSTORAGE_CURRENT.write_text(json.dumps(sanitized_current, indent=2), encoding="utf-8")
    SMARTSTORAGE_SETTINGS.write_text(json.dumps(sanitized_settings, indent=2), encoding="utf-8")
    REDFISH_DEBUG_REPORT.write_text(_redfish_debug_markdown(report), encoding="utf-8")
    return report


def write_hpe_raid_pending_report(session: Session) -> dict[str, Any]:
    current = _get_smartstorage_resource(SMART_STORAGE_CONFIG_PATH)
    settings_response = _get_smartstorage_resource(SMART_STORAGE_SETTINGS_PATH)
    last_apply = _last_apply_full_state()
    expected_payload = _redfish_settings_payload(get_hpe_raid_intent(session))

    current_body = _sanitize_artifact(_resource_body_or_error(current))
    settings_body = _sanitize_artifact(_resource_body_or_error(settings_response))
    expected = _sanitize_artifact(expected_payload)
    pending = _pending_summary(current_body, settings_body, expected, last_apply)
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_id": PROVIDER_ID,
        "status": "pending-reset" if pending["reset_required"] else "ready",
        "message": (
            "Pending HPE RAID settings require a server reset."
            if pending["reset_required"]
            else "No reset-required pending RAID state was detected."
        ),
        "provider_mode": settings.provider_mode,
        "current_get": _response_summary(current),
        "settings_get": _response_summary(settings_response),
        "pending": pending,
        "blockers": [],
        "warnings": [],
        "last_apply": _sanitize_artifact(last_apply),
        "next_safe_action": (
            f"Run `HPE_RAID_ALLOW_RESET=true HPE_RAID_RESET_CONFIRM=\"{RESET_CONFIRMATION_PHRASE}\" "
            "LAB_ALLOW_POWER_ACTIONS=true make -C app provider-lab-server-reset-for-raid` when ready."
            if pending["reset_required"]
            else "No reset-required pending RAID state was detected."
        ),
    }
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    SMARTSTORAGE_CURRENT.write_text(json.dumps(current_body, indent=2), encoding="utf-8")
    SMARTSTORAGE_SETTINGS.write_text(json.dumps(settings_body, indent=2), encoding="utf-8")
    APPLY_PAYLOAD_REDACTED.write_text(json.dumps(expected, indent=2), encoding="utf-8")
    PENDING_REPORT.write_text(_pending_markdown(report), encoding="utf-8")
    return report


def build_hpe_raid_reset_plan() -> dict[str, Any]:
    blockers = _reset_blockers()
    return {
        "provider_id": PROVIDER_ID,
        "status": "ready" if not blockers else "blocked",
        "message": (
            "Server reset for pending HPE RAID settings is available through iLO Redfish."
            if not blockers
            else "Server reset for pending HPE RAID settings is gated."
        ),
        "apply_enabled": not blockers,
        "reset_type": "GracefulRestart",
        "confirmation_phrase": RESET_CONFIRMATION_PHRASE,
        "command": (
            f'HPE_RAID_ALLOW_RESET=true LAB_ALLOW_POWER_ACTIONS=true '
            f'HPE_RAID_RESET_CONFIRM="{RESET_CONFIRMATION_PHRASE}" '
            "make -C app provider-lab-server-reset-for-raid"
        ),
        "blockers": blockers,
        "warnings": [
            "Server reset interrupts the lab host and is only for the isolated DL360 Gen10 workflow.",
        ],
        "report": str(RESET_REPORT.relative_to(REPO_ROOT)),
        "next_safe_action": (
            "Run the reset command from a terminal only if pending settings still require reset."
            if not blockers
            else "Review pending RAID state and set the reset gates only when a reset is still required."
        ),
    }


def reset_server_for_raid() -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    before = _server_reset_observation()
    blockers = _reset_blockers()
    if blockers:
        result = {
            "provider_id": PROVIDER_ID,
            "status": "blocked",
            "message": "Server reset for RAID pending settings did not run.",
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "before": before,
            "reset": None,
            "after": None,
            "blockers": blockers,
            "next_safe_action": "Set the reset gates and exact confirmation phrase from a terminal.",
        }
        _write_reset_report(result)
        return result

    reset_result = _post_system_reset("GracefulRestart")
    time.sleep(10)
    after = _server_reset_observation(allow_errors=True)
    result = {
        "provider_id": PROVIDER_ID,
        "status": "reset-requested" if 200 <= int(reset_result.get("status_code") or 0) < 300 else "failed",
        "message": "Server reset was requested through iLO Redfish." if 200 <= int(reset_result.get("status_code") or 0) < 300 else "Server reset request failed.",
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "before": before,
        "reset": reset_result,
        "after": after,
        "blockers": [],
        "next_safe_action": "Run provider-lab-hpe-raid-validate-after-reset after iLO and the server settle.",
    }
    _write_reset_report(result)
    return result


def validate_hpe_raid_after_reset(session: Session) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    wait_seconds = _int_env("HPE_RAID_VALIDATE_WAIT_SECONDS", 900)
    interval_seconds = _int_env("HPE_RAID_VALIDATE_POLL_SECONDS", 20)
    wait = _wait_for_ilo(wait_seconds=wait_seconds, interval_seconds=interval_seconds)
    probe = IloRedfishAdapter(provider_mode="local-lab-readwrite").probe() if wait["reachable"] else None
    discovery = get_hpe_storage_discovery()
    current = _get_smartstorage_resource(SMART_STORAGE_CONFIG_PATH) if wait["reachable"] else {}
    settings_response = _get_smartstorage_resource(SMART_STORAGE_SETTINGS_PATH) if wait["reachable"] else {}
    expected = _redfish_settings_payload(get_hpe_raid_intent(session))
    validation = _validate_live_layout(
        _resource_body_or_error(current) if current else {},
        expected,
    )
    status = "succeeded" if wait["reachable"] and validation["matches"] else "failed"
    result = {
        "provider_id": PROVIDER_ID,
        "status": status,
        "message": (
            "Live SmartStorage layout matches the saved RAID intent."
            if status == "succeeded"
            else "Live SmartStorage layout does not yet match the saved RAID intent."
        ),
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "wait": wait,
        "probe_status": probe.get("status") if isinstance(probe, dict) else None,
        "discovery": _layout_summary(discovery),
        "current_get": _response_summary(current) if current else None,
        "settings_get": _response_summary(settings_response) if settings_response else None,
        "validation": validation,
        "next_safe_action": (
            "Continue with ESXi install preparation."
            if status == "succeeded"
            else "Wait longer for POST/reset processing, then rerun provider-lab-hpe-raid-validate-after-reset."
        ),
    }
    _write_after_reset_validation_report(result)
    return result


def _apply_blockers(
    preview: HpeRaidPlanPreviewRead,
    *,
    confirmation_phrase: str,
) -> list[str]:
    blockers = []
    policy = current_lab_action_policy(settings.provider_mode)
    blockers.extend(policy.action_blockers(APPLY_ACTION_ID, ActionCategory.STORAGE_CONFIG))
    if confirmation_phrase != CONFIRMATION_PHRASE:
        blockers.append(f"Exact confirmation phrase is required: {CONFIRMATION_PHRASE}")
    if os.getenv("HPE_RAID_ALLOW_DESTRUCTIVE", "").lower() != "true":
        blockers.append("HPE_RAID_ALLOW_DESTRUCTIVE=true is required for destructive RAID apply.")
    if preview.blockers:
        blockers.extend(preview.blockers)
    if not preview.desired_intent.volumes:
        blockers.append("Saved RAID intent must include at least one logical drive.")
    if preview.current_layout.logical_drives and not preview.desired_intent.wipe_existing_logical_drives:
        blockers.append(
            "Existing logical drives are present; saved RAID intent must explicitly request wipe/delete planning."
        )
    return _unique(blockers)


def _reset_blockers() -> list[str]:
    blockers = []
    policy = current_lab_action_policy(settings.provider_mode)
    blockers.extend(policy.action_blockers(RESET_ACTION_ID, ActionCategory.POWER_ACTION))
    if os.getenv("HPE_RAID_ALLOW_RESET", "").lower() != "true":
        blockers.append("HPE_RAID_ALLOW_RESET=true is required for server reset.")
    if os.getenv("HPE_RAID_RESET_CONFIRM", "") != RESET_CONFIRMATION_PHRASE:
        blockers.append(f"Exact confirmation phrase is required: {RESET_CONFIRMATION_PHRASE}")
    return _unique(blockers)


def _pending_summary(
    current: dict[str, Any],
    settings_response: dict[str, Any],
    expected: dict[str, Any],
    last_apply: dict[str, Any],
) -> dict[str, Any]:
    current_drives = _logical_drive_debug(current)
    settings_drives = _logical_drive_debug(settings_response)
    expected_drives = _planned_logical_drive_debug(expected)
    reset_required = _last_apply_has_message(last_apply, "iLO.2.25.SystemResetRequired")
    pending_matches_expected = _drive_debug_equivalent(settings_drives, expected_drives)
    live_matches_expected = _drive_debug_equivalent(current_drives, expected_drives)
    pending_differs_from_live = not _drive_debug_equivalent(current_drives, settings_drives)
    reset_required = not live_matches_expected and (
        reset_required or (pending_matches_expected and not live_matches_expected)
    )
    return {
        "pending_config_exists": pending_matches_expected and not live_matches_expected,
        "pending_matches_expected": pending_matches_expected,
        "live_matches_expected": live_matches_expected,
        "pending_differs_from_live": pending_differs_from_live,
        "reset_required": reset_required,
        "last_apply_system_reset_required": _last_apply_has_message(last_apply, "iLO.2.25.SystemResetRequired"),
        "current_logical_drives": current_drives,
        "settings_logical_drives": settings_drives,
        "expected_logical_drives": expected_drives,
    }


def _last_apply_has_message(last_apply: dict[str, Any], message_id: str) -> bool:
    result = last_apply.get("redfish_result")
    if not isinstance(result, dict):
        return False
    details = _redfish_error_details(result)
    for item in details.get("extended_info") or []:
        if isinstance(item, dict) and item.get("MessageId") == message_id:
            return True
    return False


def _drive_debug_equivalent(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    return _normalized_drive_debug(left) == _normalized_drive_debug(right)


def _normalized_drive_debug(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for drive in value:
        normalized.append(
            {
                "raid": _redfish_raid(str(drive.get("raid") or "")),
                "data_drives": sorted(str(item) for item in (drive.get("data_drives") or [])),
                "spare_drives": sorted(str(item) for item in (drive.get("spare_drives") or [])),
                "spare_rebuild_mode": drive.get("spare_rebuild_mode") or None,
            }
        )
    return sorted(normalized, key=lambda item: (item["raid"], ",".join(item["data_drives"])))


def _validate_live_layout(current: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    current_drives = _logical_drive_debug(current)
    expected_drives = _planned_logical_drive_debug(expected)
    matches = _drive_debug_equivalent(current_drives, expected_drives)
    return {
        "matches": matches,
        "current_logical_drives": current_drives,
        "expected_logical_drives": expected_drives,
        "mismatches": [] if matches else _layout_mismatches(current_drives, expected_drives),
    }


def _layout_mismatches(current: list[dict[str, Any]], expected: list[dict[str, Any]]) -> list[str]:
    current_normalized = _normalized_drive_debug(current)
    expected_normalized = _normalized_drive_debug(expected)
    if len(current_normalized) != len(expected_normalized):
        return [
            f"Logical drive count differs: current={len(current_normalized)} expected={len(expected_normalized)}."
        ]
    mismatches = []
    for index, (current_drive, expected_drive) in enumerate(zip(current_normalized, expected_normalized, strict=False), start=1):
        if current_drive != expected_drive:
            mismatches.append(
                f"Logical drive {index} differs: current={current_drive} expected={expected_drive}."
            )
    return mismatches


def _redfish_settings_payload(intent: HpeRaidIntentRead) -> dict[str, Any]:
    return {
        "DataGuard": "Disabled" if intent.wipe_existing_logical_drives else "Permissive",
        "LogicalDrives": [_redfish_logical_drive(volume) for volume in intent.volumes],
    }


def _redfish_logical_drive(volume: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "LogicalDriveName": volume.name,
        "Raid": _redfish_raid(volume.raid_level),
        "DataDrives": volume.drive_bays,
        "DriveLocationFormat": "ControllerPort:Box:Bay",
    }
    if volume.bootable:
        payload["LegacyBootPriority"] = "Primary"
    if getattr(volume, "spare_bays", None):
        payload["SpareDrives"] = volume.spare_bays
        payload["SpareRebuildMode"] = volume.spare_rebuild_mode or "Dedicated"
    if volume.size_policy and volume.size_policy != "max":
        payload["CapacityGiB"] = volume.size_policy
    return payload


def _redfish_raid(value: str) -> str:
    normalized = value.upper().replace(" ", "")
    if normalized.startswith("RAID"):
        normalized = normalized.removeprefix("RAID")
    return f"Raid{normalized}"


def _patch_smartstorage_settings(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.ilo_test_host or not settings.ilo_test_username or not settings.ilo_test_password:
        raise RuntimeError("Complete iLO configuration is required for HPE RAID apply.")

    base_url = _base_url(settings.ilo_test_host)
    timeout = httpx.Timeout(settings.ilo_test_timeout_seconds)
    with httpx.Client(
        auth=(settings.ilo_test_username, settings.ilo_test_password),
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        verify=settings.ilo_test_verify_tls,
    ) as client:
        current = _get_with_retries(client, base_url + SMART_STORAGE_SETTINGS_PATH)
        etag = current.headers.get("etag") or current.headers.get("ETag") or "*"
        response = client.patch(
            base_url + SMART_STORAGE_SETTINGS_PATH,
            headers={"If-Match": etag},
            json=payload,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text[:1000]}
        return {
            "method": "PATCH",
            "path": SMART_STORAGE_SETTINGS_PATH,
            "status_code": response.status_code,
            "response": redact_sensitive(
                body,
                [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password],
            ),
        }


def _get_smartstorage_resource(path: str) -> dict[str, Any]:
    return _get_redfish_resource(path)


def _get_redfish_resource(path: str) -> dict[str, Any]:
    if not settings.ilo_test_host or not settings.ilo_test_username or not settings.ilo_test_password:
        raise RuntimeError("Complete iLO configuration is required for HPE Redfish access.")

    base_url = _base_url(settings.ilo_test_host)
    timeout = httpx.Timeout(settings.ilo_test_timeout_seconds)
    with httpx.Client(
        auth=(settings.ilo_test_username, settings.ilo_test_password),
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        verify=settings.ilo_test_verify_tls,
    ) as client:
        response = _get_with_retries(client, base_url + path)
        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text}
        return {
            "method": "GET",
            "path": path,
            "status_code": response.status_code,
            "etag": response.headers.get("etag") or response.headers.get("ETag"),
            "body": body if isinstance(body, dict) else {"value": body},
        }


def _post_system_reset(reset_type: str) -> dict[str, Any]:
    if not settings.ilo_test_host or not settings.ilo_test_username or not settings.ilo_test_password:
        raise RuntimeError("Complete iLO configuration is required for server reset.")

    system = _get_redfish_resource(SYSTEM_PATH)
    system_body = system.get("body") if isinstance(system.get("body"), dict) else {}
    target = _system_reset_target(system_body)
    base_url = _base_url(settings.ilo_test_host)
    timeout = httpx.Timeout(settings.ilo_test_timeout_seconds)
    with httpx.Client(
        auth=(settings.ilo_test_username, settings.ilo_test_password),
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        verify=settings.ilo_test_verify_tls,
    ) as client:
        response = client.post(base_url + target, json={"ResetType": reset_type})
        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text[:1000]}
        return _sanitize_artifact(
            {
                "method": "POST",
                "path": target,
                "status_code": response.status_code,
                "request": {"ResetType": reset_type},
                "response": body if isinstance(body, dict) else {"value": body},
            }
        )


def _system_reset_target(system_body: dict[str, Any]) -> str:
    actions = system_body.get("Actions")
    if isinstance(actions, dict):
        action = actions.get("#ComputerSystem.Reset") or actions.get("ComputerSystem.Reset")
        if isinstance(action, dict):
            target = action.get("target") or action.get("Target")
            if isinstance(target, str) and target:
                return target
    return "/redfish/v1/systems/1/Actions/ComputerSystem.Reset/"


def _server_reset_observation(*, allow_errors: bool = False) -> dict[str, Any]:
    try:
        system = _get_redfish_resource(SYSTEM_PATH)
        current = _get_smartstorage_resource(SMART_STORAGE_CONFIG_PATH)
        settings_response = _get_smartstorage_resource(SMART_STORAGE_SETTINGS_PATH)
    except Exception as exc:
        if not allow_errors:
            raise
        return {
            "reachable": False,
            "error_class": type(exc).__name__,
            "error": str(exc),
        }
    system_body = system.get("body") if isinstance(system.get("body"), dict) else {}
    return {
        "reachable": True,
        "system_get": _response_summary(system),
        "power_state": system_body.get("PowerState"),
        "health": _health(system_body),
        "current_get": _response_summary(current),
        "settings_get": _response_summary(settings_response),
        "current_logical_drives": _logical_drive_debug(_resource_body_or_error(current)),
        "settings_logical_drives": _logical_drive_debug(_resource_body_or_error(settings_response)),
    }


def _wait_for_ilo(*, wait_seconds: int, interval_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    attempts = 0
    last_error = None
    while time.monotonic() - started <= wait_seconds:
        attempts += 1
        try:
            system = _get_redfish_resource(SYSTEM_PATH)
            if int(system.get("status_code") or 0) == 200:
                body = system.get("body") if isinstance(system.get("body"), dict) else {}
                return {
                    "reachable": True,
                    "attempts": attempts,
                    "elapsed_seconds": int(time.monotonic() - started),
                    "power_state": body.get("PowerState"),
                    "health": _health(body),
                }
        except Exception as exc:  # pragma: no cover - real lab timing path
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(max(interval_seconds, 1))
    return {
        "reachable": False,
        "attempts": attempts,
        "elapsed_seconds": int(time.monotonic() - started),
        "last_error": last_error,
    }


def _get_with_retries(client: httpx.Client, url: str) -> httpx.Response:
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            return client.get(url)
        except httpx.HTTPError as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("GET failed without exception.")


def _layout_summary(discovery: HpeStorageDiscoveryRead) -> dict[str, Any]:
    return {
        "last_probe_time": discovery.last_probe_time,
        "storage_inventory_available": discovery.storage_inventory_available,
        "server": discovery.server,
        "controller_count": len(discovery.controllers),
        "physical_drive_count": len(discovery.physical_drives),
        "logical_drive_count": len(discovery.logical_drives),
        "logical_drives": [
            {
                "name": drive.get("display_label"),
                "raid": drive.get("raid_level"),
                "capacity": drive.get("capacity_label"),
                "health": drive.get("health"),
            }
            for drive in discovery.logical_drives
        ],
    }


def _write_apply_artifacts(result: dict[str, Any]) -> None:
    sanitized = _sanitize_artifact(result)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    APPLY_STATE.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    redfish_payload = sanitized.get("redfish_payload")
    if isinstance(redfish_payload, dict):
        APPLY_PAYLOAD_REDACTED.write_text(json.dumps(redfish_payload, indent=2), encoding="utf-8")
    APPLY_REPORT.write_text(_apply_report_markdown(sanitized), encoding="utf-8")


def _write_reset_report(result: dict[str, Any]) -> None:
    sanitized = _sanitize_artifact(result)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    RESET_REPORT.write_text(_reset_markdown(sanitized), encoding="utf-8")


def _write_after_reset_validation_report(result: dict[str, Any]) -> None:
    sanitized = _sanitize_artifact(result)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    AFTER_RESET_VALIDATION_REPORT.write_text(_after_reset_validation_markdown(sanitized), encoding="utf-8")


def _sanitize_artifact(payload: Any) -> Any:
    return redact_sensitive(
        payload,
        [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password],
    )


def _last_apply_full_state() -> dict[str, Any]:
    if not APPLY_STATE.exists():
        return {"status": "never", "report": str(APPLY_REPORT.relative_to(REPO_ROOT))}
    try:
        payload = json.loads(APPLY_STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "failed", "message": "Apply state JSON could not be parsed."}
    return payload if isinstance(payload, dict) else {"status": "failed", "message": "Apply state was not an object."}


def _last_apply_state() -> dict[str, Any]:
    if not APPLY_STATE.exists():
        return {"status": "never", "report": str(APPLY_REPORT.relative_to(REPO_ROOT))}
    try:
        payload = json.loads(APPLY_STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "failed", "report": str(APPLY_REPORT.relative_to(REPO_ROOT))}
    return {
        "status": payload.get("status") or "unknown",
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "message": payload.get("message"),
        "report": str(APPLY_REPORT.relative_to(REPO_ROOT)),
    }


def _apply_report_markdown(result: dict[str, Any]) -> str:
    redfish_result = result.get("redfish_result") or {}
    redfish_error = _redfish_error_details(redfish_result if isinstance(redfish_result, dict) else {})
    lines = [
        "# HPE RAID Apply Report",
        "",
        f"Started: {result.get('started_at') or 'unknown'}",
        f"Finished: {result.get('finished_at') or 'unknown'}",
        f"Status: {result.get('status') or 'unknown'}",
        f"Message: {result.get('message') or 'unknown'}",
        "",
        "## Before",
        "",
        *_layout_lines(result.get("before")),
        "",
        "## After",
        "",
        *_layout_lines(result.get("after")),
        "",
        "## Redfish Result",
        "",
        f"- Method/path: {(result.get('redfish_result') or {}).get('method', 'not-run')} {(result.get('redfish_result') or {}).get('path', '')}",
        f"- HTTP status: {(result.get('redfish_result') or {}).get('status_code', 'not-run')}",
        f"- Redfish error code: {redfish_error.get('code') or 'none'}",
        f"- Redfish message: {redfish_error.get('message') or 'none'}",
        f"- ExtendedInfo count: {len(redfish_error.get('extended_info') or [])}",
        "",
        "## Blockers",
        "",
    ]
    blockers = result.get("blockers") or []
    lines.extend([f"- {blocker}" for blocker in blockers] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    warnings = result.get("warnings") or []
    lines.extend([f"- {warning}" for warning in warnings] or ["- none"])
    lines.append("")
    return "\n".join(lines)


def _pending_markdown(report: dict[str, Any]) -> str:
    pending = report.get("pending") or {}
    lines = [
        "# HPE RAID Pending Report",
        "",
        f"Date: {report.get('checked_at')}",
        f"Mode: `{report.get('provider_mode')}`",
        "",
        "## SmartStorage GETs",
        "",
        f"- Current: HTTP {(report.get('current_get') or {}).get('status_code')}",
        f"- Settings: HTTP {(report.get('settings_get') or {}).get('status_code')}",
        "",
        "## Pending State",
        "",
        f"- Pending config exists: {pending.get('pending_config_exists')}",
        f"- Settings match saved intent: {pending.get('pending_matches_expected')}",
        f"- Live config matches saved intent: {pending.get('live_matches_expected')}",
        f"- Pending differs from live: {pending.get('pending_differs_from_live')}",
        f"- Reset required: {pending.get('reset_required')}",
        f"- Last apply reported SystemResetRequired: {pending.get('last_apply_system_reset_required')}",
        "",
        "## Expected Logical Drives",
        "",
    ]
    lines.extend(_debug_drive_lines(pending.get("expected_logical_drives")))
    lines.extend(["", "## Current Live Logical Drives", ""])
    lines.extend(_debug_drive_lines(pending.get("current_logical_drives")))
    lines.extend(["", "## Pending Settings Logical Drives", ""])
    lines.extend(_debug_drive_lines(pending.get("settings_logical_drives")))
    lines.extend(["", "## Next Safe Action", "", f"- {report.get('next_safe_action')}", ""])
    return "\n".join(lines)


def _reset_markdown(result: dict[str, Any]) -> str:
    reset = result.get("reset") or {}
    lines = [
        "# HPE RAID Server Reset Report",
        "",
        f"Started: {result.get('started_at')}",
        f"Finished: {result.get('finished_at')}",
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        "",
        "## Before",
        "",
        *_reset_observation_lines(result.get("before")),
        "",
        "## Reset Request",
        "",
        f"- Method/path: {reset.get('method', 'not-run')} {reset.get('path', '')}",
        f"- HTTP status: {reset.get('status_code', 'not-run')}",
        f"- ResetType: {(reset.get('request') or {}).get('ResetType', 'not-run')}",
        "",
        "## After",
        "",
        *_reset_observation_lines(result.get("after")),
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in result.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Next Safe Action", "", f"- {result.get('next_safe_action')}", ""])
    return "\n".join(lines)


def _after_reset_validation_markdown(result: dict[str, Any]) -> str:
    validation = result.get("validation") or {}
    lines = [
        "# HPE RAID After Reset Validation Report",
        "",
        f"Started: {result.get('started_at')}",
        f"Finished: {result.get('finished_at')}",
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        "",
        "## Wait",
        "",
        f"- Reachable: {(result.get('wait') or {}).get('reachable')}",
        f"- Attempts: {(result.get('wait') or {}).get('attempts')}",
        f"- Elapsed seconds: {(result.get('wait') or {}).get('elapsed_seconds')}",
        f"- Power state: {(result.get('wait') or {}).get('power_state')}",
        "",
        "## Validation",
        "",
        f"- Matches saved intent: {validation.get('matches')}",
        "",
        "### Expected Logical Drives",
        "",
    ]
    lines.extend(_debug_drive_lines(validation.get("expected_logical_drives")))
    lines.extend(["", "### Current Live Logical Drives", ""])
    lines.extend(_debug_drive_lines(validation.get("current_logical_drives")))
    lines.extend(["", "## Mismatches", ""])
    lines.extend([f"- {item}" for item in validation.get("mismatches") or []] or ["- none"])
    lines.extend(["", "## Next Safe Action", "", f"- {result.get('next_safe_action')}", ""])
    return "\n".join(lines)


def _reset_observation_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["- none"]
    if not value.get("reachable", True):
        return [
            "- Reachable: False",
            f"- Error: {value.get('error_class')} {value.get('error')}",
        ]
    lines = [
        f"- Reachable: {value.get('reachable')}",
        f"- Power state: {value.get('power_state')}",
        f"- Health: {value.get('health')}",
        f"- Current GET: HTTP {(value.get('current_get') or {}).get('status_code')}",
        f"- Settings GET: HTTP {(value.get('settings_get') or {}).get('status_code')}",
        "- Current logical drives:",
    ]
    lines.extend(f"  - {line.removeprefix('- ')}" for line in _debug_drive_lines(value.get("current_logical_drives")))
    lines.append("- Pending settings logical drives:")
    lines.extend(f"  - {line.removeprefix('- ')}" for line in _debug_drive_lines(value.get("settings_logical_drives")))
    return lines


def _redfish_error_details(redfish_result: dict[str, Any]) -> dict[str, Any]:
    response = redfish_result.get("response")
    if not isinstance(response, dict):
        return {}
    error = response.get("error")
    if not isinstance(error, dict):
        return {}
    extended = error.get("@Message.ExtendedInfo") or error.get("Message.ExtendedInfo") or []
    if not isinstance(extended, list):
        extended = []
    return {
        "status_code": redfish_result.get("status_code"),
        "code": error.get("code"),
        "message": error.get("message"),
        "extended_info": [
            item
            for item in extended
            if isinstance(item, dict)
        ],
    }


def _resource_body_or_error(response: dict[str, Any]) -> dict[str, Any]:
    if int(response.get("status_code") or 0) < 400:
        body = response.get("body")
        return body if isinstance(body, dict) else {"value": body}
    return {
        "_http_status": response.get("status_code"),
        "_path": response.get("path"),
        "body": response.get("body"),
    }


def _response_summary(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": response.get("method"),
        "path": response.get("path"),
        "status_code": response.get("status_code"),
        "etag_present": bool(response.get("etag")),
    }


def _redfish_debug_comparison(
    payload: dict[str, Any],
    current: dict[str, Any],
    settings_response: dict[str, Any],
    error_details: dict[str, Any],
) -> dict[str, Any]:
    planned = _planned_logical_drive_debug(payload)
    settings_drives = _logical_drive_debug(settings_response)
    current_drives = _logical_drive_debug(current)
    message_args = []
    for item in error_details.get("extended_info") or []:
        if isinstance(item, dict) and item.get("MessageId") == "iLO.2.25.ArrayPropertyOutOfBound":
            value = item.get("MessageArgs")
            if isinstance(value, list):
                message_args = [str(arg) for arg in value]
                break

    diagnosis = "No Redfish error body was available to diagnose."
    if len(message_args) == 4 and message_args[0] == "DataDrives":
        diagnosis = (
            f"iLO rejected DataDrives because the payload supplied {message_args[1]} entries; "
            f"the accepted range reported by iLO is {message_args[2]} to {message_args[3]}."
        )

    return {
        "diagnosis": diagnosis,
        "planned_logical_drives": planned,
        "current_logical_drives": current_drives,
        "settings_logical_drives": settings_drives,
        "array_property_out_of_bound_args": message_args,
    }


def _planned_logical_drive_debug(payload: dict[str, Any]) -> list[dict[str, Any]]:
    logical_drives = payload.get("LogicalDrives")
    if not isinstance(logical_drives, list):
        return []
    return [
        {
            "name": drive.get("LogicalDriveName"),
            "raid": drive.get("Raid"),
            "data_drive_count": len(drive.get("DataDrives") or []),
            "data_drives": drive.get("DataDrives") or [],
            "spare_drive_count": len(drive.get("SpareDrives") or []),
            "spare_drives": drive.get("SpareDrives") or [],
            "spare_rebuild_mode": drive.get("SpareRebuildMode"),
        }
        for drive in logical_drives
        if isinstance(drive, dict)
    ]


def _logical_drive_debug(resource: dict[str, Any]) -> list[dict[str, Any]]:
    logical_drives = resource.get("LogicalDrives")
    if not isinstance(logical_drives, list):
        return []
    return [
        {
            "name": drive.get("LogicalDriveName") or drive.get("Name"),
            "raid": drive.get("Raid") or drive.get("RAIDType"),
            "data_drive_count": len(drive.get("DataDrives") or []),
            "data_drives": drive.get("DataDrives") or [],
            "spare_drive_count": len(drive.get("SpareDrives") or []),
            "spare_drives": drive.get("SpareDrives") or [],
            "spare_rebuild_mode": drive.get("SpareRebuildMode"),
        }
        for drive in logical_drives
        if isinstance(drive, dict)
    ]


def _redfish_debug_markdown(report: dict[str, Any]) -> str:
    error = report.get("redfish_error") or {}
    comparison = report.get("comparison") or {}
    lines = [
        "# HPE RAID Redfish Debug Report",
        "",
        f"Date: {report.get('checked_at')}",
        f"Mode: `{report.get('provider_mode')}`",
        "PATCH run by this report: no",
        "",
        "## GET Captures",
        "",
        f"- {SMART_STORAGE_CONFIG_PATH}: HTTP {(report.get('current_get') or {}).get('status_code')}",
        f"- {SMART_STORAGE_SETTINGS_PATH}: HTTP {(report.get('settings_get') or {}).get('status_code')}",
        "",
        "## Last Apply Error",
        "",
        f"- HTTP status: {error.get('status_code') or 'unknown'}",
        f"- Error code: {error.get('code') or 'unknown'}",
        f"- Message: {error.get('message') or 'unknown'}",
    ]
    for item in error.get("extended_info") or []:
        lines.append(f"- ExtendedInfo: {item.get('MessageId')} args={item.get('MessageArgs')}")
    lines.extend(
        [
            "",
            "## Payload Comparison",
            "",
            f"- Diagnosis: {comparison.get('diagnosis') or 'unknown'}",
            "",
            "### Planned Logical Drives",
            "",
        ]
    )
    lines.extend(_debug_drive_lines(comparison.get("planned_logical_drives")))
    lines.extend(["", "### SmartStorage Settings Logical Drives", ""])
    lines.extend(_debug_drive_lines(comparison.get("settings_logical_drives")))
    lines.extend(["", "## Artifacts", ""])
    for label, path in (report.get("artifacts") or {}).items():
        lines.append(f"- {label}: `{path}`")
    lines.append("")
    return "\n".join(lines)


def _debug_drive_lines(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- none"]
    lines = []
    for drive in value:
        if not isinstance(drive, dict):
            continue
        lines.append(
            "- "
            f"{drive.get('name')}: raid={drive.get('raid')} "
            f"data_count={drive.get('data_drive_count')} data={', '.join(drive.get('data_drives') or []) or '-'} "
            f"spare_count={drive.get('spare_drive_count')} spare={', '.join(drive.get('spare_drives') or []) or '-'}"
        )
    return lines or ["- none"]


def _layout_lines(layout: Any) -> list[str]:
    if not isinstance(layout, dict):
        return ["- none"]
    lines = [
        f"- Storage inventory available: {layout.get('storage_inventory_available')}",
        f"- Controller count: {layout.get('controller_count')}",
        f"- Physical drive count: {layout.get('physical_drive_count')}",
        f"- Logical drive count: {layout.get('logical_drive_count')}",
    ]
    for drive in layout.get("logical_drives") or []:
        lines.append(
            f"- Logical drive: {drive.get('name')} raid={drive.get('raid')} capacity={drive.get('capacity')} health={drive.get('health')}"
        )
    return lines


def _intent_read(
    payload: HpeRaidIntentWrite,
    *,
    created_at: Any = None,
    updated_at: Any = None,
) -> HpeRaidIntentRead:
    return HpeRaidIntentRead(
        provider_id=PROVIDER_ID,
        apply_enabled=False,
        created_at=created_at,
        updated_at=updated_at,
        **payload.model_dump(),
    )


def _validate_intent(
    intent: HpeRaidIntentRead,
    discovery: HpeStorageDiscoveryRead,
) -> dict[str, list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    discovered_bays = {_bay_id(drive) for drive in discovery.physical_drives}
    discovered_bays.discard("")
    selected_bays: set[str] = set()

    for volume in intent.volumes:
        if not volume.drive_bays:
            blockers.append(f"{volume.name} has no physical drive bays selected.")
            continue
        spare_bays = list(getattr(volume, "spare_bays", []) or [])
        volume_bays = [*volume.drive_bays, *spare_bays]
        unknown_bays = sorted(set(volume_bays) - discovered_bays)
        if unknown_bays and discovered_bays:
            blockers.append(f"{volume.name} references unknown drive bays: {', '.join(unknown_bays)}.")

        duplicate_bays = sorted(selected_bays.intersection(volume_bays))
        if duplicate_bays:
            blockers.append(f"{volume.name} reuses drive bays already assigned: {', '.join(duplicate_bays)}.")
        internal_duplicates = sorted({bay for bay in volume.drive_bays if bay in spare_bays})
        if internal_duplicates:
            blockers.append(
                f"{volume.name} uses the same bays for data and spare: {', '.join(internal_duplicates)}."
            )
        selected_bays.update(volume_bays)

        minimum = _minimum_drives(volume.raid_level)
        if len(volume.drive_bays) < minimum:
            blockers.append(
                f"{volume.name} needs at least {minimum} drives for {volume.raid_level}; "
                f"{len(volume.drive_bays)} selected."
            )

        if volume.bootable and len([item for item in intent.volumes if item.bootable]) > 1:
            blockers.append("Only one planned RAID volume can be marked bootable.")

    if intent.volumes and not intent.controller_ref and len(discovery.controllers) > 1:
        blockers.append("Multiple storage controllers are discovered; select a controller for the plan.")
    if intent.volumes and not discovery.storage_inventory_available:
        blockers.append("Storage inventory is unavailable; RAID intent cannot be validated.")
    if len(intent.volumes) > 2:
        warnings.append("More than two logical drives are planned; confirm this matches the ESXi design.")

    return {"blockers": _unique(blockers), "warnings": _unique(warnings)}


def _planned_volume(volume: Any, discovery: HpeStorageDiscoveryRead) -> dict[str, Any]:
    selected = [_drive_for_bay(discovery.physical_drives, bay) for bay in volume.drive_bays]
    capacity_bytes = [_capacity_bytes(drive) for drive in selected if drive]
    return {
        "name": volume.name,
        "purpose": volume.purpose,
        "raid_level": volume.raid_level,
        "bootable": volume.bootable,
        "size_policy": volume.size_policy,
        "drive_bays": volume.drive_bays,
        "spare_bays": list(getattr(volume, "spare_bays", []) or []),
        "spare_rebuild_mode": getattr(volume, "spare_rebuild_mode", None),
        "drive_count": len(volume.drive_bays),
        "spare_count": len(getattr(volume, "spare_bays", []) or []),
        "selected_drive_capacity_bytes": capacity_bytes,
        "estimated_usable_capacity_bytes": _estimated_capacity(volume.raid_level, capacity_bytes),
        "media_types": sorted(
            {
                str(drive.get("MediaType") or drive.get("media_type"))
                for drive in selected
                if drive and (drive.get("MediaType") or drive.get("media_type"))
            }
        ),
        "health": "review" if any(_health(drive) != "OK" for drive in selected if drive) else "OK",
    }


def _plan_summary(
    intent: HpeRaidIntentRead,
    discovery: HpeStorageDiscoveryRead,
    planned_volumes: list[dict[str, Any]],
) -> str:
    if not discovery.storage_inventory_available:
        return "Storage inventory is not available through cached Redfish discovery."
    if not planned_volumes:
        return "No desired RAID layout has been saved yet."
    volume_parts = [
        f"{volume['name']} {volume['raid_level']} on bays {', '.join(volume['drive_bays'])}"
        for volume in planned_volumes
    ]
    wipe = "with existing logical drive wipe/delete requested" if intent.wipe_existing_logical_drives else "without wipe/delete approval"
    return f"Plan-only preview {wipe}: " + "; ".join(volume_parts) + "."


def _drive_for_ui(drive: dict[str, Any]) -> dict[str, Any]:
    bay = _bay_id(drive)
    capacity = _capacity_bytes(drive)
    return {
        **drive,
        "bay_id": bay,
        "display_label": f"Bay {bay}" if bay else str(drive.get("Name") or drive.get("Id") or "Drive"),
        "capacity_bytes": capacity,
        "capacity_label": _capacity_label(capacity),
        "media_type": drive.get("MediaType") or drive.get("InterfaceType") or drive.get("Protocol"),
        "health": _health(drive),
    }


def _logical_for_ui(drive: dict[str, Any]) -> dict[str, Any]:
    capacity = _capacity_bytes(drive)
    return {
        **drive,
        "display_label": drive.get("LogicalDriveName") or drive.get("Name") or drive.get("Id") or "Logical drive",
        "raid_level": drive.get("RAIDType") or drive.get("Raid") or drive.get("VolumeType"),
        "capacity_bytes": capacity,
        "capacity_label": _capacity_label(capacity),
        "health": _health(drive),
    }


def _server_summary(systems: list[dict[str, Any]]) -> dict[str, Any]:
    if not systems:
        return {}
    system = systems[0]
    return {
        "model": system.get("Model") or system.get("model"),
        "power_state": system.get("PowerState") or system.get("power_state"),
        "health": _health(system),
        "serial_number_present": bool(system.get("serial_number_present")),
    }


def _selected_bays(intent: HpeRaidIntentRead) -> set[str]:
    selected = set()
    for volume in intent.volumes:
        selected.update(volume.drive_bays)
        selected.update(getattr(volume, "spare_bays", []) or [])
    return selected


def _unselected_bays(intent: HpeRaidIntentRead, discovery: HpeStorageDiscoveryRead) -> list[str]:
    selected = _selected_bays(intent)
    return sorted(bay for bay in (_bay_id(drive) for drive in discovery.physical_drives) if bay and bay not in selected)


def _drive_for_bay(drives: list[dict[str, Any]], bay: str) -> dict[str, Any] | None:
    for drive in drives:
        if _bay_id(drive) == bay:
            return drive
    return None


def _bay_id(drive: dict[str, Any]) -> str:
    bay = drive.get("bay_id") or drive.get("Bay")
    if isinstance(bay, (str, int)):
        return str(bay)
    location = drive.get("Location")
    if isinstance(location, str):
        return location
    return str(drive.get("Id") or drive.get("Name") or "")


def _minimum_drives(raid_level: str) -> int:
    normalized = raid_level.upper().replace(" ", "")
    if normalized in {"RAID0", "0"}:
        return 1
    if normalized in {"RAID1", "1"}:
        return 2
    if normalized in {"RAID5", "5"}:
        return 3
    if normalized in {"RAID6", "6"}:
        return 4
    if normalized in {"RAID10", "1+0", "10"}:
        return 4
    return 1


def _estimated_capacity(raid_level: str, capacities: list[int]) -> int | None:
    if not capacities:
        return None
    smallest = min(capacities)
    count = len(capacities)
    normalized = raid_level.upper().replace(" ", "")
    if normalized in {"RAID0", "0"}:
        usable_count = count
    elif normalized in {"RAID1", "1"}:
        usable_count = 1
    elif normalized in {"RAID5", "5"}:
        usable_count = max(count - 1, 0)
    elif normalized in {"RAID6", "6"}:
        usable_count = max(count - 2, 0)
    elif normalized in {"RAID10", "1+0", "10"}:
        usable_count = count // 2
    else:
        return None
    return smallest * usable_count


def _capacity_bytes(item: dict[str, Any] | None) -> int:
    if not item:
        return 0
    for key, multiplier in (
        ("capacity_bytes", 1),
        ("CapacityBytes", 1),
        ("CapacityMiB", 1024 * 1024),
        ("CapacityGB", 1000 * 1000 * 1000),
    ):
        value = item.get(key)
        if isinstance(value, int):
            return value * multiplier
        if isinstance(value, float):
            return int(value * multiplier)
    return 0


def _capacity_label(value: int) -> str:
    if value <= 0:
        return "unknown"
    tib = value / (1024**4)
    if tib >= 1:
        return f"{tib:.2f} TiB"
    gib = value / (1024**3)
    return f"{gib:.1f} GiB"


def _health(item: dict[str, Any] | None) -> str:
    if not item:
        return "unknown"
    status = item.get("Status")
    if isinstance(status, dict):
        return str(status.get("Health") or status.get("State") or "unknown")
    return str(item.get("health") or item.get("Health") or "unknown")


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
