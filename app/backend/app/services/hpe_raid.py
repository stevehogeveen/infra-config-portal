from __future__ import annotations

import hashlib
import json
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
from app.providers.ilo_redfish import (
    IloRedfishAdapter,
    IloRedfishConfig,
    _base_url,
    ilo_redfish_redaction_values,
    ilo_target_fingerprint,
)
from app.providers.probe_cache import get_probe_result
from app.providers.redaction import redact_sensitive
from app.services.env_utils import env_int as _env_int
from app.services.firmware_compliance import firmware_gate_blockers
from app.services.guarded_action_context import GuardedActionContext, guarded_confirmation, guarded_flag
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.ilo_write_target import (
    IloWriteTargetContext,
    compact_ilo_write_target,
    exact_ilo_write_config,
    refresh_ilo_write_target_context,
    requested_ilo_write_host,
    resolve_ilo_write_target_context,
)
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.path_utils import path_exists, repo_relative_path
from app.schemas import (
    HpeRaidApplyCreate,
    HpeRaidFactoryResetCreate,
    HpeRaidIntentRead,
    HpeRaidIntentWrite,
    HpeRaidPlanPreviewRead,
    HpeStorageDiscoveryRead,
)

CONFIRMATION_PHRASE = "APPLY HPE RAID PLAN"
FACTORY_RESET_CONFIRMATION_PHRASE = "FACTORY RESET HPE RAID"
RESET_CONFIRMATION_PHRASE = "RESET SERVER FOR HPE RAID APPLY"
APPLY_ACTION_ID = "ilo-redfish.hpe-raid-apply"
FACTORY_RESET_ACTION_ID = "ilo-redfish.hpe-raid-factory-reset"
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
FACTORY_RESET_PLAN_REPORT = CODEX_RUN_DIR / "hpe-raid-factory-reset-plan-report.md"
FACTORY_RESET_APPLY_REPORT = CODEX_RUN_DIR / "hpe-raid-factory-reset-apply-report.md"

DISABLED_RAID_ACTIONS = [
    "drive wipe",
    "logical drive delete",
    "array/controller initialize",
    "RAID logical drive create",
    "boot volume selection",
    "storage controller write",
]


def get_hpe_storage_discovery(
    *,
    probe: dict[str, Any] | None = None,
    probe_time: str | None = None,
) -> HpeStorageDiscoveryRead:
    if probe is None:
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
    controllers = _dedupe_by_identity(_list(storage.get("controllers")), _controller_identity)
    # Pairing needs the RAW drive list: deduping by hardware identity is
    # exactly what removes the duplicate-view entries whose resource paths
    # the volume links reference.
    raw_physical_drives = [_drive_for_ui(drive) for drive in _list(storage.get("physical_drives"))]
    all_physical_drives = _dedupe_by_identity(raw_physical_drives, _physical_drive_identity)
    physical_drives = _prefer_smartstorage_physical_drives(
        all_physical_drives
    )
    logical_drives = _dedupe_by_identity(
        [_logical_for_ui(drive) for drive in _list(storage.get("logical_drives"))],
        _logical_drive_identity,
    )
    logical_drives = _pair_logical_drive_links(logical_drives, raw_physical_drives)
    systems = _list(probe.get("systems"))
    warnings = [*_string_list(storage.get("warnings")), *_string_list(probe.get("warnings"))]
    blockers = _string_list(probe.get("blockers"))
    inventory_available = bool(controllers or physical_drives or logical_drives)
    opaque_drive_count = sum(not _bay_id(drive) for drive in physical_drives)

    if not inventory_available:
        blockers.append("Cached iLO probe does not include HPE storage inventory.")
    if opaque_drive_count:
        warnings.append(
            f"{opaque_drive_count} physical drive(s) have stable Redfish resource identities, "
            "but iLO did not report physical bay locations. They remain visible for read-only "
            "inventory; opaque resource IDs cannot be used as ControllerPort:Box:Bay RAID payload values."
        )

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
            (
                "Review the read-only drive inventory, then resolve SmartStorage physical bay "
                "locations before saving or applying a RAID plan."
            )
            if physical_drives and opaque_drive_count == len(physical_drives)
            else (
                "Review discovered drives and save a plan-only RAID intent."
                if inventory_available
                else "Run the HPE iLO GET-only probe and confirm Smart Array storage inventory is returned."
            )
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
    local_storage_readiness = _local_storage_readiness(discovery, intent, planned_volumes)
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
        local_storage_readiness=local_storage_readiness,
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


def build_hpe_raid_factory_reset_preview(session: Session) -> dict[str, Any]:
    preview = get_hpe_raid_plan_preview(session)
    intent = preview.desired_intent
    current_logical = preview.current_layout.logical_drives
    blockers = list(preview.blockers)
    warnings = list(preview.warnings)
    if not intent.wipe_existing_logical_drives:
        blockers.append("Saved RAID intent must request wipe_existing_logical_drives before factory reset preview.")
    if not current_logical:
        blockers.append("No current logical drives are available to delete; rerun iLO storage discovery.")
    if not intent.volumes:
        blockers.append("Saved RAID intent must include recreate volumes before factory reset preview.")

    deletion_plan = [_logical_delete_preview(drive) for drive in current_logical]
    recreate_payload = _redfish_settings_payload(intent)
    report = {
        "provider_id": PROVIDER_ID,
        "status": "blocked" if blockers else "ready",
        "message": (
            "HPE RAID factory reset preview is ready. No destructive command was sent."
            if not blockers
            else "HPE RAID factory reset preview is blocked."
        ),
        "checked_at": datetime.now(UTC).isoformat(),
        "apply_enabled": False,
        "confirmation_phrase": FACTORY_RESET_CONFIRMATION_PHRASE,
        "delete_existing_logical_drives": deletion_plan,
        "recreate_payload": recreate_payload,
        "delete_count": len(deletion_plan),
        "recreate_count": len(intent.volumes),
        "executor_available": False,
        "blockers": _unique(blockers),
        "warnings": _unique(
            [
                *warnings,
                "Preview only: the app does not yet have a proven HPE SmartStorage logical-drive delete executor.",
            ]
        ),
        "not_attempted": DISABLED_RAID_ACTIONS,
        "report": _rel(FACTORY_RESET_PLAN_REPORT),
        "next_safe_action": (
            "Prove delete/recreate manually or implement the explicit SmartStorage delete action before apply."
            if not blockers
            else "Resolve preview blockers before designing the factory-reset executor."
        ),
    }
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(FACTORY_RESET_PLAN_REPORT, _factory_reset_markdown(report))
    return report


def apply_hpe_raid_factory_reset(
    session: Session,
    payload: HpeRaidFactoryResetCreate,
    *,
    guarded_context: GuardedActionContext | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    preview = build_hpe_raid_factory_reset_preview(session)
    confirmation_phrase = (
        guarded_context.confirmation_phrase
        if guarded_context is not None and guarded_context.action_id == "raid.factory-reset-apply"
        else payload.confirmation_phrase
    )
    blockers = _factory_reset_blockers(
        preview,
        confirmation_phrase=confirmation_phrase or "",
        guarded_context=guarded_context,
    )
    if not preview.get("executor_available"):
        blockers.append(
            "No implemented HPE SmartStorage logical-drive delete/factory-reset executor exists yet."
        )
    result = {
        "provider_id": PROVIDER_ID,
        "status": "blocked",
        "message": "HPE RAID factory reset apply was refused before any destructive command.",
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "apply_enabled": False,
        "preview": _sanitize_artifact(preview),
        "blockers": _unique(blockers),
        "warnings": [
            "No drive wipe, logical-drive delete, controller initialize, or RAID create command was sent.",
        ],
        "not_attempted": DISABLED_RAID_ACTIONS,
        "report": _rel(FACTORY_RESET_APPLY_REPORT),
        "next_safe_action": "Implement and test the explicit HPE logical-drive delete/recreate executor, or perform the first round-trip manually in SSA/iLO.",
    }
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(FACTORY_RESET_APPLY_REPORT, _factory_reset_apply_markdown(result))
    return result


def apply_hpe_raid_plan(
    session: Session,
    payload: HpeRaidApplyCreate,
    *,
    guarded_context: GuardedActionContext | None = None,
) -> dict[str, Any]:
    requested_host = requested_ilo_write_host(payload.ilo_host)
    write_target, target_blockers = resolve_ilo_write_target_context(requested_host)
    config = exact_ilo_write_config(write_target) if write_target is not None else None
    preview = get_hpe_raid_plan_preview(session)
    confirmation_phrase = (
        guarded_context.confirmation_phrase
        if guarded_context is not None and guarded_context.action_id == "raid.apply"
        else payload.confirmation_phrase
    )
    blockers = _apply_blockers(
        preview,
        confirmation_phrase=confirmation_phrase or "",
        guarded_context=guarded_context,
    )
    blockers = _unique([*target_blockers, *blockers])
    if not blockers and write_target is not None:
        refreshed_target, refreshed_config, refresh_blockers = (
            refresh_ilo_write_target_context(write_target)
        )
        blockers = _unique([*blockers, *refresh_blockers])
        if refreshed_target is not None and refreshed_config is not None:
            write_target = refreshed_target
            config = refreshed_config
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
            "write_target": compact_ilo_write_target(write_target),
            "not_attempted": DISABLED_RAID_ACTIONS,
        }
        _write_apply_artifacts(result)
        return result

    assert config is not None
    before = get_hpe_storage_discovery()
    redfish_payload = _redfish_settings_payload(preview.desired_intent)
    redfish_result: dict[str, Any] = {}
    status = "failed"
    message = "HPE RAID apply failed."
    try:
        response_payload = _patch_smartstorage_settings(
            redfish_payload,
            config=config,
        )
        redfish_result = response_payload
        probe = IloRedfishAdapter(
            provider_mode="local-lab-readwrite",
            config=config,
        ).probe()
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
        "write_target": compact_ilo_write_target(write_target),
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
            "debug_report": _rel(REDFISH_DEBUG_REPORT),
            "payload": _rel(APPLY_PAYLOAD_REDACTED),
            "current": _rel(SMARTSTORAGE_CURRENT),
            "settings": _rel(SMARTSTORAGE_SETTINGS),
        },
    }

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(APPLY_PAYLOAD_REDACTED, sanitized_payload)
    write_json_object(SMARTSTORAGE_CURRENT, sanitized_current)
    write_json_object(SMARTSTORAGE_SETTINGS, sanitized_settings)
    write_text_value(REDFISH_DEBUG_REPORT, _redfish_debug_markdown(report))
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
    next_safe_action = _pending_next_safe_action(pending)
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_id": PROVIDER_ID,
        "status": _pending_report_status(pending),
        "message": _pending_report_message(pending),
        "provider_mode": settings.provider_mode,
        "current_get": _response_summary(current),
        "settings_get": _response_summary(settings_response),
        "pending": pending,
        "blockers": [],
        "warnings": [],
        "last_apply": _sanitize_artifact(last_apply),
        "next_safe_action": next_safe_action,
    }
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(SMARTSTORAGE_CURRENT, current_body)
    write_json_object(SMARTSTORAGE_SETTINGS, settings_body)
    write_json_object(APPLY_PAYLOAD_REDACTED, expected)
    write_text_value(PENDING_REPORT, _pending_markdown(report))
    return report


def build_hpe_raid_reset_plan() -> dict[str, Any]:
    blockers = _reset_blockers()
    observation = _server_reset_observation(allow_errors=True)
    power_state = observation.get("power_state") if observation.get("reachable") else None
    reset_type = _reset_type_for_power_state(power_state)
    if blockers:
        next_safe_action = "Review pending RAID state and set the reset gates only when a reset is still required."
    elif reset_type == "On":
        next_safe_action = "Power on the host through the guarded reset action only after pending settings have been re-read."
    else:
        next_safe_action = "Run the reset command from a terminal only if pending settings still require reset."
    return {
        "provider_id": PROVIDER_ID,
        "status": "ready" if not blockers else "blocked",
        "message": (
            "Server reset for pending HPE RAID settings is available through iLO Redfish."
            if not blockers
            else "Server reset for pending HPE RAID settings is gated."
        ),
        "apply_enabled": not blockers,
        "reset_type": reset_type,
        "power_state": power_state,
        "confirmation_phrase": RESET_CONFIRMATION_PHRASE,
        "command": (
            f'HPE_RAID_ALLOW_RESET=true LAB_ALLOW_POWER_ACTIONS=true '
            f'HPE_RAID_RESET_CONFIRM="{RESET_CONFIRMATION_PHRASE}" '
            "make -C app provider-lab-server-reset-for-raid"
        ),
        "blockers": blockers,
        "warnings": [
            (
                "Server is off; ResetType=On will power it on so POST can apply staged SmartStorage settings."
                if reset_type == "On"
                else "Server reset interrupts the lab host and is only for the isolated DL360 Gen10 workflow."
            ),
        ],
        "report": _rel(RESET_REPORT),
        "next_safe_action": next_safe_action,
    }


def reset_server_for_raid(
    *,
    ilo_host: str | None = None,
    guarded_context: GuardedActionContext | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    requested_host = requested_ilo_write_host(ilo_host)
    write_target, target_blockers = resolve_ilo_write_target_context(requested_host)
    blockers = _unique(
        [
            *target_blockers,
            *_reset_blockers(guarded_context=guarded_context),
        ]
    )
    if not blockers and write_target is not None:
        refreshed_target, _refreshed_config, refresh_blockers = (
            refresh_ilo_write_target_context(write_target)
        )
        blockers = _unique([*blockers, *refresh_blockers])
        if refreshed_target is not None:
            write_target = refreshed_target
    if blockers:
        result = {
            "provider_id": PROVIDER_ID,
            "status": "blocked",
            "message": "Server reset for RAID pending settings did not run.",
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "before": None,
            "reset": None,
            "after": None,
            "blockers": blockers,
            "write_target": compact_ilo_write_target(write_target),
            "next_safe_action": "Set the reset gates and exact confirmation phrase from a terminal.",
        }
        _write_reset_report(result)
        return result

    assert write_target is not None
    config = exact_ilo_write_config(write_target)
    before = _server_reset_observation(config=config)
    last_apply = _last_apply_full_state()
    pending, pending_blockers = _target_bound_reset_preconditions(
        write_target,
        before,
        last_apply,
    )
    if pending_blockers:
        result = {
            "provider_id": PROVIDER_ID,
            "status": "blocked",
            "message": "Server reset for RAID pending settings did not run.",
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "before": before,
            "pending": pending,
            "reset": None,
            "after": None,
            "blockers": pending_blockers,
            "write_target": compact_ilo_write_target(write_target),
            "next_safe_action": (
                "Collect fresh exact-target pending RAID evidence from the same apply receipt."
            ),
        }
        _write_reset_report(result)
        return result

    refreshed_target, refreshed_config, refresh_blockers = (
        refresh_ilo_write_target_context(write_target)
    )
    if refresh_blockers or refreshed_target is None or refreshed_config is None:
        result = {
            "provider_id": PROVIDER_ID,
            "status": "blocked",
            "message": "Server reset for RAID pending settings did not run.",
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "before": before,
            "pending": pending,
            "reset": None,
            "after": None,
            "blockers": refresh_blockers,
            "write_target": compact_ilo_write_target(refreshed_target),
            "next_safe_action": (
                "Rerun exact-target iLO Inventory Read and revalidate pending RAID evidence."
            ),
        }
        _write_reset_report(result)
        return result
    write_target = refreshed_target
    config = refreshed_config
    reset_type = _reset_type_for_power_state(before.get("power_state"))
    reset_result = _post_system_reset(reset_type, config=config)
    time.sleep(10)
    after = _server_reset_observation(config=config, allow_errors=True)
    result = {
        "provider_id": PROVIDER_ID,
        "status": "reset-requested" if 200 <= int(reset_result.get("status_code") or 0) < 300 else "failed",
        "message": "Server reset was requested through iLO Redfish." if 200 <= int(reset_result.get("status_code") or 0) < 300 else "Server reset request failed.",
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "before": before,
        "pending": pending,
        "reset_type": reset_type,
        "reset": reset_result,
        "after": after,
        "blockers": [],
        "write_target": compact_ilo_write_target(write_target),
        "next_safe_action": "Run provider-lab-hpe-raid-validate-after-reset after iLO and the server settle.",
    }
    _write_reset_report(result)
    return result


def _target_bound_reset_preconditions(
    write_target: IloWriteTargetContext,
    before: dict[str, Any],
    last_apply: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    apply_target = (
        last_apply.get("write_target")
        if isinstance(last_apply.get("write_target"), dict)
        else {}
    )
    for key, expected in (
        ("current_access_host", write_target.current_access_host),
        ("target_fingerprint", write_target.target_fingerprint),
        (
            "identity_fingerprint_sha256",
            write_target.identity_fingerprint_sha256,
        ),
    ):
        if apply_target.get(key) != expected:
            blockers.append(
                f"Last RAID apply receipt is not bound to this iLO write target ({key})."
            )
    if last_apply.get("status") != "succeeded":
        blockers.append("A successful target-bound RAID apply receipt is required before reset.")

    expected_payload = (
        last_apply.get("redfish_payload")
        if isinstance(last_apply.get("redfish_payload"), dict)
        else {}
    )
    expected_drives = _planned_logical_drive_debug(expected_payload)
    current_drives = (
        before.get("current_logical_drives")
        if isinstance(before.get("current_logical_drives"), list)
        else []
    )
    settings_drives = (
        before.get("settings_logical_drives")
        if isinstance(before.get("settings_logical_drives"), list)
        else []
    )
    pending_matches_expected = bool(expected_drives) and _drive_debug_equivalent(
        settings_drives,
        expected_drives,
    )
    live_matches_expected = bool(expected_drives) and _drive_debug_equivalent(
        current_drives,
        expected_drives,
    )
    pending_differs_from_live = not _drive_debug_equivalent(
        current_drives,
        settings_drives,
    )
    reset_required = (
        pending_matches_expected
        and not live_matches_expected
        and (
            _last_apply_has_message(last_apply, "iLO.2.25.SystemResetRequired")
            or pending_differs_from_live
        )
    )
    pending = {
        "expected_logical_drives": expected_drives,
        "current_logical_drives": current_drives,
        "settings_logical_drives": settings_drives,
        "pending_matches_expected": pending_matches_expected,
        "live_matches_expected": live_matches_expected,
        "pending_differs_from_live": pending_differs_from_live,
        "reset_required": reset_required,
    }
    if not expected_drives:
        blockers.append("Last RAID apply receipt has no reviewed logical-drive payload.")
    if not pending_matches_expected:
        blockers.append("Fresh pending SmartStorage settings do not match the last RAID apply receipt.")
    if not reset_required:
        blockers.append("Fresh exact-target RAID evidence does not prove that a reset is required.")
    return pending, _unique(blockers)


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
    guarded_context: GuardedActionContext | None = None,
) -> list[str]:
    blockers = []
    policy = current_lab_action_policy(settings.provider_mode)
    blockers.extend(_string_list(policy.action_blockers(APPLY_ACTION_ID, ActionCategory.STORAGE_CONFIG)))
    blockers.extend(_string_list(firmware_gate_blockers("HPE RAID apply")))
    if confirmation_phrase != CONFIRMATION_PHRASE:
        blockers.append(f"Exact confirmation phrase is required: {CONFIRMATION_PHRASE}")
    if not guarded_flag("HPE_RAID_ALLOW_DESTRUCTIVE", action_id="raid.apply", context=guarded_context):
        blockers.append("HPE_RAID_ALLOW_DESTRUCTIVE=true is required for destructive RAID apply.")
    blockers.extend(_string_list(preview.blockers))
    if not preview.desired_intent.volumes:
        blockers.append("Saved RAID intent must include at least one logical drive.")
    if preview.current_layout.logical_drives and not preview.desired_intent.wipe_existing_logical_drives:
        blockers.append(
            "Existing logical drives are present; saved RAID intent must explicitly request wipe/delete planning."
        )
    return _unique(blockers)


def _factory_reset_blockers(
    preview: dict[str, Any],
    *,
    confirmation_phrase: str,
    guarded_context: GuardedActionContext | None = None,
) -> list[str]:
    blockers = []
    policy = current_lab_action_policy(settings.provider_mode)
    blockers.extend(_string_list(policy.action_blockers(FACTORY_RESET_ACTION_ID, ActionCategory.FACTORY_RESET)))
    if confirmation_phrase != FACTORY_RESET_CONFIRMATION_PHRASE:
        blockers.append(f"Exact confirmation phrase is required: {FACTORY_RESET_CONFIRMATION_PHRASE}")
    if not guarded_flag(
        "HPE_RAID_ALLOW_FACTORY_RESET", action_id="raid.factory-reset-apply", context=guarded_context
    ):
        blockers.append("HPE_RAID_ALLOW_FACTORY_RESET=true is required for HPE RAID factory reset.")
    blockers.extend(_string_list(preview.get("blockers")))
    return _unique(blockers)


def _reset_blockers(*, guarded_context: GuardedActionContext | None = None) -> list[str]:
    blockers = []
    policy = current_lab_action_policy(settings.provider_mode)
    blockers.extend(_string_list(policy.action_blockers(RESET_ACTION_ID, ActionCategory.POWER_ACTION)))
    blockers.extend(_string_list(firmware_gate_blockers("HPE RAID reset")))
    if not guarded_flag("HPE_RAID_ALLOW_RESET", action_id="raid.reset-commit", context=guarded_context):
        blockers.append("HPE_RAID_ALLOW_RESET=true is required for server reset.")
    if guarded_confirmation(
        "HPE_RAID_RESET_CONFIRM", action_id="raid.reset-commit", context=guarded_context
    ) != RESET_CONFIRMATION_PHRASE:
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
    current_readable = _smartstorage_readable(current)
    settings_readable = _smartstorage_readable(settings_response)
    smartstorage_reads_available = current_readable and settings_readable
    last_apply_reset_required = _last_apply_has_message(last_apply, "iLO.2.25.SystemResetRequired")
    pending_matches_expected = _drive_debug_equivalent(settings_drives, expected_drives)
    live_matches_expected = _drive_debug_equivalent(current_drives, expected_drives)
    pending_differs_from_live = not _drive_debug_equivalent(current_drives, settings_drives)
    pending_config_exists = (
        smartstorage_reads_available
        and pending_matches_expected
        and not live_matches_expected
    )
    reset_required = pending_config_exists and (
        last_apply_reset_required or pending_differs_from_live
    )
    return {
        "smartstorage_reads_available": smartstorage_reads_available,
        "current_readable": current_readable,
        "settings_readable": settings_readable,
        "pending_config_exists": pending_config_exists,
        "pending_matches_expected": pending_matches_expected,
        "live_matches_expected": live_matches_expected,
        "pending_differs_from_live": pending_differs_from_live,
        "reset_required": reset_required,
        "last_apply_system_reset_required": last_apply_reset_required,
        "current_logical_drives": current_drives,
        "settings_logical_drives": settings_drives,
        "expected_logical_drives": expected_drives,
    }


def _smartstorage_readable(value: dict[str, Any]) -> bool:
    status = value.get("_http_status")
    return status is None or int(status or 0) < 400


def _pending_report_status(pending: dict[str, Any]) -> str:
    if not pending.get("smartstorage_reads_available"):
        return "blocked"
    if pending.get("reset_required"):
        return "pending-reset"
    return "ready"


def _pending_report_message(pending: dict[str, Any]) -> str:
    if not pending.get("smartstorage_reads_available"):
        return "HPE SmartStorage current/settings state cannot be read."
    if pending.get("reset_required"):
        return "Pending HPE RAID settings require a server reset."
    return "No reset-required pending RAID state was detected."


def _pending_next_safe_action(pending: dict[str, Any]) -> str:
    if not pending.get("smartstorage_reads_available"):
        return "Resolve iLO Redfish SmartStorage authorization, then rerun HPE RAID discovery and pending checks."
    if pending.get("reset_required"):
        return (
            f"Run `HPE_RAID_ALLOW_RESET=true HPE_RAID_RESET_CONFIRM=\"{RESET_CONFIRMATION_PHRASE}\" "
            "LAB_ALLOW_POWER_ACTIONS=true make -C app provider-lab-server-reset-for-raid` when ready."
        )
    return "No reset-required pending RAID state was detected."


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


def _patch_smartstorage_settings(
    payload: dict[str, Any],
    *,
    config: IloRedfishConfig,
) -> dict[str, Any]:
    if not config.host or not config.username or not config.password:
        raise RuntimeError("Complete iLO configuration is required for HPE RAID apply.")

    base_url = _base_url(config.host)
    timeout = httpx.Timeout(config.timeout_seconds)
    with httpx.Client(
        auth=(config.username, config.password),
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        verify=config.verify_tls,
    ) as client:
        current = _get_with_retries(
            client,
            base_url + SMART_STORAGE_SETTINGS_PATH,
            require_success=True,
        )
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
                ilo_redfish_redaction_values(config),
            ),
        }


def _get_smartstorage_resource(
    path: str,
    *,
    config: IloRedfishConfig | None = None,
) -> dict[str, Any]:
    # Every caller of this wrapper (write_hpe_raid_pending_report and others)
    # feeds the result straight into _resource_body_or_error/_response_summary,
    # which already tolerate a missing/None status_code - they were written
    # assuming a failed read comes back as data, not an exception. But
    # _get_redfish_resource raises on a real connection failure (e.g. the
    # target device is unreachable), so an unreachable device turned every
    # one of these endpoints into an unhandled 500 instead of a normal
    # failed-status response. Catch here, matching the same fallback shape
    # esxi_install_readiness.py's _safe_get already uses for the same class
    # of call.
    try:
        if config is None:
            return _get_redfish_resource(path)
        return _get_redfish_resource(path, config=config)
    except Exception as exc:
        return {
            "method": "GET",
            "path": path,
            "status_code": None,
            "error_class": type(exc).__name__,
            "error": str(exc),
        }


def _get_redfish_resource(
    path: str,
    *,
    config: IloRedfishConfig | None = None,
) -> dict[str, Any]:
    config = config or IloRedfishConfig.from_settings()
    if not config.target_candidates or not config.username or not config.password:
        raise RuntimeError("Complete iLO configuration is required for HPE Redfish access.")

    timeout = httpx.Timeout(config.timeout_seconds)
    last_exc: httpx.HTTPError | None = None
    for candidate in config.target_candidates:
        base_url = _base_url(candidate["host"])
        try:
            with httpx.Client(
                auth=(config.username, config.password),
                follow_redirects=False,
                timeout=timeout,
                trust_env=False,
                verify=config.verify_tls,
            ) as client:
                response = _get_with_retries(client, base_url + path)
        except httpx.HTTPError as exc:
            if not _try_next_redfish_get_candidate(exc):
                raise
            last_exc = exc
            continue
        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text}
        return {
            "method": "GET",
            "path": path,
            "target_source": candidate.get("source"),
            "target_fingerprint": ilo_target_fingerprint(candidate.get("host")),
            "status_code": response.status_code,
            "etag": response.headers.get("etag") or response.headers.get("ETag"),
            "body": body if isinstance(body, dict) else {"value": body},
        }
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Complete iLO target configuration is required for HPE Redfish access.")


def _post_system_reset(
    reset_type: str,
    *,
    config: IloRedfishConfig,
) -> dict[str, Any]:
    if not config.host or not config.username or not config.password:
        raise RuntimeError("Complete iLO configuration is required for server reset.")

    system = _get_redfish_resource(SYSTEM_PATH, config=config)
    system_status = int(system.get("status_code") or 0)
    if system_status < 200 or system_status >= 300:
        raise RuntimeError(
            "Exact-target system preflight must return HTTP 2xx before reset."
        )
    system_body = system.get("body") if isinstance(system.get("body"), dict) else {}
    target = _system_reset_target(system_body)
    if target is None:
        raise RuntimeError(
            "Exact-target system preflight did not advertise a reset action."
        )
    base_url = _base_url(config.host)
    timeout = httpx.Timeout(config.timeout_seconds)
    with httpx.Client(
        auth=(config.username, config.password),
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        verify=config.verify_tls,
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
                "target_source": config.host_source,
                "target_fingerprint": ilo_target_fingerprint(config.host),
                "status_code": response.status_code,
                "request": {"ResetType": reset_type},
                "response": body if isinstance(body, dict) else {"value": body},
            }
        )


def _reset_type_for_power_state(power_state: Any) -> str:
    return "On" if str(power_state or "").strip().lower() == "off" else "GracefulRestart"


def _system_reset_target(system_body: dict[str, Any]) -> str | None:
    actions = system_body.get("Actions")
    if isinstance(actions, dict):
        action = actions.get("#ComputerSystem.Reset") or actions.get("ComputerSystem.Reset")
        if isinstance(action, dict):
            target = action.get("target") or action.get("Target")
            if isinstance(target, str) and target:
                return target
    return None


def _server_reset_observation(
    *,
    config: IloRedfishConfig | None = None,
    allow_errors: bool = False,
) -> dict[str, Any]:
    try:
        system = _get_redfish_resource(SYSTEM_PATH, config=config)
        current = _get_smartstorage_resource(
            SMART_STORAGE_CONFIG_PATH,
            config=config,
        )
        settings_response = _get_smartstorage_resource(
            SMART_STORAGE_SETTINGS_PATH,
            config=config,
        )
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


def _wait_for_ilo(
    *,
    wait_seconds: int,
    interval_seconds: int,
    config: IloRedfishConfig | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    attempts = 0
    last_error = None
    while time.monotonic() - started <= wait_seconds:
        attempts += 1
        try:
            system = _get_redfish_resource(SYSTEM_PATH, config=config)
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


def _get_with_retries(
    client: httpx.Client,
    url: str,
    *,
    require_success: bool = False,
) -> httpx.Response:
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            response = client.get(url)
            if require_success:
                response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("GET failed without exception.")


def _try_next_redfish_get_candidate(exc: httpx.HTTPError) -> bool:
    text = str(exc).lower()
    if any(token in text for token in ("certificate", "tls", "ssl")):
        return False
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


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
    write_json_object(APPLY_STATE, sanitized)
    redfish_payload = sanitized.get("redfish_payload")
    if isinstance(redfish_payload, dict):
        write_json_object(APPLY_PAYLOAD_REDACTED, redfish_payload)
    write_text_value(APPLY_REPORT, _apply_report_markdown(sanitized))


def _write_reset_report(result: dict[str, Any]) -> None:
    sanitized = _sanitize_artifact(result)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(RESET_REPORT, _reset_markdown(sanitized))


def _write_after_reset_validation_report(result: dict[str, Any]) -> None:
    sanitized = _sanitize_artifact(result)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(AFTER_RESET_VALIDATION_REPORT, _after_reset_validation_markdown(sanitized))


def _sanitize_artifact(payload: Any) -> Any:
    return redact_sensitive(
        payload,
        ilo_redfish_redaction_values(),
    )


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _apply_state_exists() -> bool:
    return path_exists(APPLY_STATE)


def _last_apply_full_state() -> dict[str, Any]:
    if not _apply_state_exists():
        return {"status": "never", "report": _rel(APPLY_REPORT)}
    payload = read_json_object(APPLY_STATE)
    if not payload:
        return {"status": "failed", "message": "Apply state JSON could not be parsed."}
    return payload


def _last_apply_state() -> dict[str, Any]:
    if not _apply_state_exists():
        return {"status": "never", "report": _rel(APPLY_REPORT)}
    payload = read_json_object(APPLY_STATE)
    if not payload:
        return {"status": "failed", "report": _rel(APPLY_REPORT)}
    return {
        "status": payload.get("status") or "unknown",
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "message": payload.get("message"),
        "report": _rel(APPLY_REPORT),
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
        f"- SmartStorage reads available: {pending.get('smartstorage_reads_available')}",
        f"- Current readable: {pending.get('current_readable')}",
        f"- Settings readable: {pending.get('settings_readable')}",
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


def _factory_reset_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HPE RAID Factory Reset Preview",
        "",
        f"Checked: {report.get('checked_at')}",
        f"Status: {report.get('status')}",
        f"Message: {report.get('message')}",
        f"Executor available: {report.get('executor_available')}",
        "",
        "## Logical Drives That Would Be Deleted",
        "",
    ]
    for item in report.get("delete_existing_logical_drives") or []:
        lines.append(
            f"- {item.get('name')} {item.get('raid_level')} {item.get('capacity_label') or ''} ({item.get('resource') or 'resource unknown'})"
        )
    if not report.get("delete_existing_logical_drives"):
        lines.append("- none")
    lines.extend(["", "## Recreate Payload", ""])
    for item in (report.get("recreate_payload") or {}).get("LogicalDrives", []):
        lines.append(
            f"- {item.get('LogicalDriveName')} {item.get('Raid')} drives={', '.join(_string_list(item.get('DataDrives')))}"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- {item}" for item in report.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in report.get("warnings") or []] or ["- none"])
    lines.extend(["", "## Next Safe Action", "", f"- {report.get('next_safe_action')}", ""])
    return "\n".join(lines)


def _factory_reset_apply_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# HPE RAID Factory Reset Apply Report",
        "",
        f"Started: {result.get('started_at')}",
        f"Finished: {result.get('finished_at')}",
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in result.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Not Attempted", ""])
    lines.extend([f"- {item}" for item in result.get("not_attempted") or []] or ["- none"])
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

    if intent.volumes and discovery.physical_drives and not discovered_bays:
        blockers.append(
            "Discovered physical drives have only opaque Redfish resource IDs. "
            "RAID apply requires physical bay locations for the ControllerPort:Box:Bay payload."
        )

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


def _local_storage_readiness(
    discovery: HpeStorageDiscoveryRead,
    intent: HpeRaidIntentRead,
    planned_volumes: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    candidate = _recommended_local_storage_layout(discovery)
    if discovery.blockers:
        blockers.extend(discovery.blockers)
    if not discovery.storage_inventory_available:
        blockers.append("Storage controller and drive inventory is not available.")
    if not discovery.controllers:
        blockers.append("No RAID/storage controller is discovered.")
    if not discovery.physical_drives:
        blockers.append("No physical drives are discovered.")

    bad_drives = [
        _drive_label(drive)
        for drive in discovery.physical_drives
        if _drive_health_ok(drive) is False
    ]
    if bad_drives:
        blockers.append(f"Drive health needs review: {', '.join(bad_drives[:6])}.")

    unknown_drives = [
        _drive_label(drive)
        for drive in discovery.physical_drives
        if not _capacity_bytes(drive) or _drive_health_ok(drive) is None
    ]
    if unknown_drives:
        warnings.append(
            f"{len(unknown_drives)} drive(s) have unknown capacity or health and were not used for recommendation."
        )

    if candidate.get("status") == "blocked":
        blockers.extend(_string_list(candidate.get("blockers")))
    warnings.extend(_string_list(candidate.get("warnings")))

    current_logical_count = len(discovery.logical_drives)
    desired_count = len(intent.volumes)
    if desired_count:
        status = "planned" if not blockers else "blocked"
        answer = f"Desired local RAID intent has {desired_count} volume{'s' if desired_count != 1 else ''} saved."
        recommendation = "Review current-vs-intent drift before any guarded apply."
        candidate_volumes = planned_volumes
    elif current_logical_count and not blockers:
        status = "needs_review"
        answer = "Local storage exists; validate it against the ESXi datastore target."
        recommendation = "Use discovery as current state, then save desired RAID intent if the layout should change."
        candidate_volumes = candidate.get("volumes", [])
    elif blockers:
        status = "blocked"
        answer = "Local storage is not ready for ESXi."
        recommendation = candidate.get("summary") or "Resolve discovery blockers before planning RAID."
        candidate_volumes = []
    else:
        status = "recommendation"
        answer = "Local storage can be planned for standalone ESXi."
        recommendation = candidate.get("summary") or "Review the recommended RAID layout."
        candidate_volumes = candidate.get("volumes", [])

    return {
        "status": status,
        "answer": answer,
        "deployment_mode": "single_server_local_storage",
        "facts": {
            "controller_count": len(discovery.controllers),
            "physical_drive_count": len(discovery.physical_drives),
            "usable_drive_count": candidate.get("usable_drive_count", 0),
            "logical_drive_count": current_logical_count,
            "desired_volume_count": desired_count,
        },
        "recommendation": recommendation,
        "candidate_layout": candidate,
        "candidate_volumes": candidate_volumes,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
        "next_safe_action": _local_storage_next_action(blockers, desired_count, current_logical_count),
    }


def _recommended_local_storage_layout(discovery: HpeStorageDiscoveryRead) -> dict[str, Any]:
    if not discovery.storage_inventory_available:
        return {
            "status": "blocked",
            "summary": "Run the HPE iLO GET-only probe before RAID recommendation.",
            "volumes": [],
            "usable_drive_count": 0,
            "blockers": ["Storage inventory is unavailable."],
            "warnings": [],
        }

    bay_mapped_drives = [drive for drive in discovery.physical_drives if _bay_id(drive)]
    if discovery.physical_drives and not bay_mapped_drives:
        return {
            "status": "blocked",
            "summary": (
                "Physical drives are visible, but iLO did not report the physical bay locations "
                "required for a RAID plan."
            ),
            "volumes": [],
            "usable_drive_count": 0,
            "blockers": [
                "ControllerPort:Box:Bay drive locations are required before RAID recommendation or apply."
            ],
            "warnings": [
                "Opaque Redfish resource IDs are retained for inventory display only."
            ],
        }

    healthy_known = [
        drive
        for drive in bay_mapped_drives
        if _drive_health_ok(drive) is True and _capacity_bytes(drive) > 0
    ]
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for drive in healthy_known:
        key = (_drive_media_key(drive), _capacity_bytes(drive))
        groups.setdefault(key, []).append(drive)

    if not healthy_known:
        return {
            "status": "blocked",
            "summary": "No healthy drives with known capacity are available for RAID recommendation.",
            "volumes": [],
            "usable_drive_count": 0,
            "blockers": ["No usable drives were discovered."],
            "warnings": [],
        }

    selected = max(groups.values(), key=lambda group: (len(group), _capacity_bytes(group[0])))
    selected = sorted(selected, key=_drive_sort_key)
    warnings: list[str] = []
    opaque_drive_count = len(discovery.physical_drives) - len(bay_mapped_drives)
    if opaque_drive_count:
        warnings.append(
            f"{opaque_drive_count} drive(s) without physical bay locations were excluded from the recommendation."
        )
    if len(groups) > 1:
        warnings.append("Mixed drive media or capacity detected; recommendation uses the largest matching drive group only.")

    count = len(selected)
    bays = [_bay_id(drive) for drive in selected if _bay_id(drive)]
    volumes: list[dict[str, Any]] = []
    if count < 2:
        return {
            "status": "blocked",
            "summary": "At least two healthy matching drives are required for a protected ESXi local-storage layout.",
            "volumes": [],
            "usable_drive_count": count,
            "blockers": ["Fewer than two usable matching drives were discovered."],
            "warnings": warnings,
        }
    if count == 2:
        volumes = [_recommended_volume("ESXi-local", "ESXi boot and local datastore", "RAID1", bays[:2], True)]
        summary = "Recommend one RAID1 volume for ESXi boot and local VMFS datastore."
    elif count <= 5:
        volumes = [
            _recommended_volume("ESXi-OS", "ESXi boot", "RAID1", bays[:2], True),
            _recommended_volume("VM-Datastore", "Local VM datastore", "RAID1" if count == 4 else "RAID5", bays[2:], False),
        ]
        summary = "Recommend a small OS mirror and a protected local datastore from remaining matching drives."
        if len(bays[2:]) < _minimum_drives(volumes[1]["raid_level"]):
            volumes = [_recommended_volume("ESXi-local", "ESXi boot and local datastore", "RAID1", bays[:2], True)]
            warnings.append("Not enough remaining drives for a separate protected datastore; recommend a single RAID1 layout.")
            summary = "Recommend one RAID1 volume until more matching drives are available."
    else:
        datastore_bays = bays[2:]
        raid_level = "RAID6" if len(datastore_bays) >= 6 else "RAID5"
        spare_bays: list[str] = []
        if len(datastore_bays) >= 7 and len(datastore_bays) % 2 == 1:
            spare_bays = [datastore_bays[-1]]
            datastore_bays = datastore_bays[:-1]
        volumes = [
            _recommended_volume("ESXi-OS", "ESXi boot", "RAID1", bays[:2], True),
            _recommended_volume("VM-Datastore", "Local VM datastore", raid_level, datastore_bays, False, spare_bays),
        ]
        summary = "Recommend RAID1 for ESXi boot plus a resilient local datastore on the remaining matching drives."

    return {
        "status": "recommended",
        "summary": summary,
        "volumes": volumes,
        "usable_drive_count": count,
        "selected_drive_bays": bays,
        "blockers": [],
        "warnings": warnings,
    }


def _recommended_volume(
    name: str,
    purpose: str,
    raid_level: str,
    drive_bays: list[str],
    bootable: bool,
    spare_bays: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "purpose": purpose,
        "raid_level": raid_level,
        "drive_bays": drive_bays,
        "spare_bays": spare_bays or [],
        "size_policy": "max",
        "bootable": bootable,
    }


def _local_storage_next_action(blockers: list[str], desired_count: int, current_logical_count: int) -> str:
    if blockers:
        return "Resolve storage discovery blockers before saving or applying RAID intent."
    if desired_count:
        return "Compare desired RAID intent to current layout; apply remains guarded and destructive."
    if current_logical_count:
        return "Validate ESXi datastore visibility, then save intent only if the layout should change."
    return "Review the recommended layout, then save plan-only RAID intent before any destructive lane."


def _drive_for_ui(drive: dict[str, Any]) -> dict[str, Any]:
    bay = _bay_id(drive)
    capacity = _capacity_bytes(drive)
    selection_id, identity_kind = _physical_drive_inventory_identity(drive)
    return {
        **drive,
        "bay_id": bay,
        "selection_id": bay or selection_id,
        "inventory_id": selection_id,
        "identity_kind": identity_kind,
        "raid_payload_id": bay or None,
        "raid_payload_compatible": bool(bay),
        "display_label": _physical_drive_display_label(drive, bay, selection_id),
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


def _logical_delete_preview(drive: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": drive.get("display_label") or drive.get("LogicalDriveName") or drive.get("Name") or drive.get("Id"),
        "raid_level": drive.get("raid_level") or drive.get("RAIDType") or drive.get("Raid"),
        "capacity_label": drive.get("capacity_label"),
        "capacity_bytes": drive.get("capacity_bytes") or drive.get("CapacityBytes"),
        "health": drive.get("health") or _health(drive),
        "resource": drive.get("@odata.id"),
    }


def _dedupe_by_identity(items: list[dict[str, Any]], identity: Any) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = tuple(_identity_part(part) for part in identity(item))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _prefer_smartstorage_physical_drives(drives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    smartstorage_drives = [
        drive
        for drive in drives
        if ":" in str(drive.get("bay_id") or _bay_id(drive) or "")
    ]
    return smartstorage_drives or drives


def _pair_logical_drive_links(
    logical_drives: list[dict[str, Any]],
    physical_drives: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Carry cross-view hardware identity onto volume member links.

    DMTF volume links can target Storage-view drives while the useful bay is
    only present on the SmartStorage view.  The provider fingerprints both
    resources from stable hardware identity fields, so retain that bridge
    before the non-bay duplicate view is hidden from the UI inventory.
    """
    fingerprints_by_resource = {
        str(drive.get("@odata.id") or "").rstrip("/"): drive.get(
            "hardware_identity_fingerprint_sha256"
        )
        for drive in physical_drives
        if drive.get("@odata.id")
        and drive.get("hardware_identity_fingerprint_sha256")
    }
    paired: list[dict[str, Any]] = []
    for volume in logical_drives:
        copy = dict(volume)
        links = dict(copy.get("Links") or {})
        for key in ("Drives", "DedicatedSpareDrives"):
            members = []
            for member in _list(links.get(key)):
                item = dict(member)
                resource = str(item.get("@odata.id") or "").rstrip("/")
                fingerprint = fingerprints_by_resource.get(resource)
                if fingerprint:
                    item["hardware_identity_fingerprint_sha256"] = fingerprint
                members.append(item)
            if key in links:
                links[key] = members
        copy["Links"] = links
        paired.append(copy)
    return paired


def _identity_part(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value or "")


def _controller_identity(controller: dict[str, Any]) -> tuple[Any, ...]:
    return (
        controller.get("@odata.id"),
        controller.get("Id"),
        controller.get("Name"),
        controller.get("Model"),
        controller.get("FirmwareVersion"),
        controller.get("Location"),
    )


def _physical_drive_identity(drive: dict[str, Any]) -> tuple[Any, ...]:
    return _physical_drive_inventory_identity(drive)


def _physical_drive_inventory_identity(drive: dict[str, Any]) -> tuple[str, str]:
    bay = _bay_id(drive)
    if bay:
        return (f"bay:{bay}", "physical_bay")

    resource_path = drive.get("@odata.id")
    if isinstance(resource_path, str) and resource_path.strip():
        normalized_path = resource_path.strip().rstrip("/") or "/"
        return (f"redfish:{normalized_path}", "redfish_resource")

    fingerprint = drive.get("identity_fingerprint_sha256")
    if isinstance(fingerprint, str) and fingerprint.strip():
        return (f"fingerprint:{fingerprint.strip().lower()}", "redfish_fingerprint")

    canonical = json.dumps(
        drive,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return (f"fingerprint:{digest}", "inventory_fingerprint")


def _physical_drive_display_label(
    drive: dict[str, Any],
    bay: str,
    inventory_id: str,
) -> str:
    if bay:
        return f"Bay {bay}"

    name = str(drive.get("Name") or "Physical drive").strip() or "Physical drive"
    resource_token = str(drive.get("Id") or "").strip()
    if not resource_token:
        resource_path = drive.get("@odata.id")
        if isinstance(resource_path, str) and resource_path.strip():
            resource_token = resource_path.strip().rstrip("/").rsplit("/", 1)[-1]
    if not resource_token:
        resource_token = inventory_id.rsplit(":", 1)[-1][:12]
    return f"{name} (Redfish resource {resource_token})"


def _logical_drive_identity(drive: dict[str, Any]) -> tuple[Any, ...]:
    return (
        drive.get("LogicalDriveName") or drive.get("Name") or drive.get("display_label"),
        drive.get("RAIDType") or drive.get("Raid") or drive.get("raid_level"),
    )


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
    # No real bay/slot location is known for this drive. Do not fall back to
    # Id/Name here: those are Redfish resource identifiers (often large,
    # arbitrary integers), not physical bay numbers, and showing one as
    # "Bay 64518" misleads the operator into thinking it's a slot position.
    return ""


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


def _drive_health_ok(drive: dict[str, Any]) -> bool | None:
    normalized = _health(drive).strip().lower()
    if not normalized or normalized == "unknown":
        return None
    if normalized in {"ok", "enabled", "healthy"}:
        return True
    return False


def _drive_media_key(drive: dict[str, Any]) -> str:
    value = drive.get("media_type") or drive.get("MediaType") or drive.get("InterfaceType") or drive.get("Protocol")
    return str(value or "unknown").strip().lower()


def _drive_label(drive: dict[str, Any]) -> str:
    return str(
        drive.get("display_label")
        or (f"Bay {drive.get('bay_id')}" if drive.get("bay_id") else "")
        or drive.get("Name")
        or drive.get("Id")
        or "Drive"
    )


def _drive_sort_key(drive: dict[str, Any]) -> tuple[int, str]:
    label = _bay_id(drive)
    digits = "".join(ch for ch in label if ch.isdigit())
    if digits:
        return (int(digits), label)
    return (10_000, label)


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _unique(values: list[str]) -> list[str]:
    return unique_preserving_order(values, skip_falsey=True)


def _int_env(name: str, default: int) -> int:
    return _env_int(name, default, minimum=1)
