"""Explicit device-scoped RAID preview, stage and read-back verification."""
import os
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.disk_preparation import disk_preparation
from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.models import AuditEvent, DeviceInventory
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.hpe_storage_rebuild import StorageRebuildError, read_snapshot, requested_layout_matches, stage_configuration, read_boot_action, start_server
from app.services.audit import record_audit_event
from app.services.hardware_health import digest, health_issues
from app.services.hpe_raid import get_hpe_raid_intent, _redfish_settings_payload
from app.services.storage_diagnostics import diagnose_storage, read_diagnostic_log
from app.services.storage_recovery import confirmed_rejection
from app.services import disk_sanitization
from app.services.erase_options import erase_options
from app.services.hardware_health import read_health_review
from app.providers.probe_cache import get_probe_result
from app.providers.hpe_storage_rebuild import shutdown_action, request_shutdown

router = APIRouter(prefix="/api/v1/rack-plans", tags=["RAID rebuild"])


class RebuildPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["clear", "create", "reset", "sanitize"]
    erase_pattern: Literal["auto", "SanitizeRestrictedOverwrite", "SanitizeRestrictedBlockErase", "OnePass"] = "auto"


class RebuildApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=1, max_length=250)
    data_loss_confirmed: Literal[True]
    backups_confirmed: Literal[True]
    health_reviewed: Literal[True]
    firmware_reviewed: Literal[True]
    empty_bays_confirmed: list[str] = Field(default_factory=list, max_length=24)
    physical_erase_confirmed: bool = False


class BootApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=1, max_length=250)
    pending_changes_reviewed: Literal[True]
    data_loss_confirmed: Literal[True]
    maintenance_confirmed: Literal[True]


def write_blockers():
    blockers = current_lab_action_policy().action_blockers("ilo-redfish.hpe-raid-apply", ActionCategory.STORAGE_CONFIG)
    if os.getenv("HPE_RAID_ALLOW_DESTRUCTIVE", "").lower() != "true":
        blockers.append("HPE_RAID_ALLOW_DESTRUCTIVE=true is required. Storage writes are currently disabled.")
    return blockers


def reset_blockers():
    return current_lab_action_policy().action_blockers(
        "ilo-redfish.hpe-raid-factory-reset", ActionCategory.FACTORY_RESET
    )


def reset_target_blockers(device_id):
    allowed = {v.strip() for v in os.getenv('HPE_RAID_RESET_DEVICE_IDS', '').split(',') if v.strip()}
    return [] if device_id in allowed else ['This server is not enabled for the storage-reset workflow. An operator must enroll its device ID; unrelated devices remain blocked.']


class ShutdownPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    force: bool = False


class ShutdownApply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_id: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=1, max_length=250)
    downtime_confirmed: Literal[True]
    data_loss_confirmed: Literal[True]


def shutdown_review(session, profile_id, device_id, force):
    server = server_in_kit(profile_id, device_id, session)
    snapshot = read_snapshot(session, device_id)
    blockers = write_blockers() + reset_target_blockers(device_id)
    blockers += current_lab_action_policy().action_blockers('ilo-redfish.raid-shutdown', ActionCategory.POWER_ACTION)
    attempt = latest_event(session, device_id, 'attempt')
    if attempt and attempt.data_json.get('operation') == 'sanitize' and not latest_event(session, device_id, 'verified', attempt.id):
        failure = latest_event(session, device_id, 'failed', attempt.id)
        if (not failure or failure.data_json.get('reason') != 'erase_method_rejected'
                or snapshot['identity'] != attempt.data_json['identity']
                or disk_sanitization.scope(disk_sanitization.drive_rows(snapshot)) != attempt.data_json['drive_scope']
                or any(d['reasons'] != ['None'] or d['pattern'] is not None
                       for d in disk_sanitization.drive_rows(snapshot))):
            blockers.append('A physical-disk erasure is unresolved. Do not interrupt power; check erasure results first.')
    if any(set(d['reasons']) & {'EraseInProgress', 'QueuedForErase'} for d in disk_sanitization.drive_rows(snapshot)):
        blockers.append('A disk reports active or queued erasure. Keep the server powered on.')
    if snapshot['pending_differs']:
        blockers.append('Pending storage changes exist. Review them before changing power.')
    prior = latest_event(session, device_id, 'shutdown_attempt')
    boot = latest_event(session, device_id, 'boot_attempt')
    # A confirmed intervening boot starts a new shutdown cycle; never replay within one.
    if (prior and boot and boot.created_at > prior.created_at
            and boot.data_json.get('identity') == snapshot['identity']
            and snapshot['power'] == 'On'):
        boot_result = latest_event(session, device_id, 'boot_result', boot.data_json.get('attempt_id'))
        if boot_result and boot_result.data_json.get('status') == 'waiting':
            prior = None
    # A shutdown followed by a boot and then a verified storage operation is a finished cycle,
    # even if the manager identity changed later (observed after an iLO 1.48 -> 3.19 update).
    completed = latest_event(session, device_id, 'verified')
    if prior and boot and completed and prior.created_at < boot.created_at < completed.created_at:
        prior = None
    if prior:
        if not force or prior.data_json['force']:
            blockers.append('Shutdown was already requested. Read the power state; do not resend it.')
        elif datetime.now(UTC) - prior.created_at.replace(tzinfo=UTC) < timedelta(minutes=2):
            blockers.append('Allow at least two minutes for the shutdown request before reviewing forced power-off.')
        if prior.data_json['identity'] != snapshot['identity']:
            blockers.append('Server identity changed since the shutdown request.')
    elif force:
        blockers.append('Request a normal shutdown first. Forced power-off is a separately confirmed fallback.')
    path, payload = shutdown_action(snapshot, force)
    return snapshot, {'profile_id':profile_id, 'device_id':device_id, 'name':server.name,
        'identity':snapshot['identity'], 'state_digest':snapshot['state_digest'], 'force':force,
        'path':path, 'payload':payload, 'blockers':blockers, 'apply_enabled':not blockers,
        'confirmation':f"{'FORCE POWER OFF' if force else 'SHUT DOWN'} {server.name}",
        'expires_at':(datetime.now(UTC) + timedelta(minutes=5)).isoformat()}


@router.get('/{profile_id}/raid-rebuild/power-state')
def read_reset_power(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    try:
        snapshot = read_snapshot(session, device_id)
        return {'power': snapshot['power'], 'pending_changes':snapshot['pending_differs']}
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post('/{profile_id}/raid-rebuild/shutdown-preview')
def preview_shutdown(profile_id: str, device_id: str, payload: ShutdownPreview, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    try:
        _, review = shutdown_review(session, profile_id, device_id, payload.force)
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from None
    event = audit(session, actor, 'kit.raid_rebuild.shutdown_preview', 'Read-only shutdown review.', review)
    session.commit()
    return {**review, 'preview_id':event.id}


@router.post('/{profile_id}/raid-rebuild/shutdown')
def apply_shutdown(profile_id: str, device_id: str, payload: ShutdownApply, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    session.scalar(select(DeviceInventory).where(DeviceInventory.id == device_id).with_for_update())
    event = session.get(AuditEvent, payload.preview_id)
    if not event or event.event_type != 'kit.raid_rebuild.shutdown_preview' or event.data_json.get('device_id') != device_id or event.data_json.get('profile_id') != profile_id:
        raise HTTPException(404, 'Shutdown preview does not belong to this server and kit.')
    review = event.data_json
    if payload.confirmation != review['confirmation']:
        raise HTTPException(422, 'Enter the exact shutdown confirmation phrase.')
    if datetime.now(UTC) > datetime.fromisoformat(review['expires_at']):
        raise HTTPException(409, 'Shutdown preview expired. Read the server again.')
    try:
        snapshot, fresh = shutdown_review(session, profile_id, device_id, review['force'])
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from None
    if fresh['blockers'] or any(fresh[k] != review[k] for k in ['identity','state_digest','path','payload','confirmation']):
        raise HTTPException(409, ' '.join(fresh['blockers']) or 'Server state changed. Review shutdown again.')
    attempt = audit(session, actor, 'kit.raid_rebuild.shutdown_attempt', 'Confirmed shutdown request; result not verified.',
                    {**review, 'preview_id':event.id, 'confirmations':payload.model_dump()})
    session.commit()
    result = request_shutdown(snapshot, review['path'], review['payload'])
    audit(session, actor, 'kit.raid_rebuild.shutdown_result', result['message'], {'device_id':device_id,'profile_id':profile_id,'attempt_id':attempt.id,**result})
    session.commit()
    return result


def planned_payload(intent, view):
    volumes = intent.volumes
    boots = [v for v in volumes if v.bootable]
    if len(boots) != 1 or boots[0].raid_level != "RAID1" or len(boots[0].drive_bays) != 2 or not 1 <= len(volumes) <= 2:
        raise StorageRebuildError("Save a two-drive RAID1 boot mirror and optionally one separate VM-data array first.")
    if intent.controller_ref != view["controllers"][0]["id"]:
        raise StorageRebuildError("Saved RAID intent belongs to a different controller.")
    selected_bays = {bay for volume in volumes for bay in [*volume.drive_bays, *volume.spare_bays]}
    ineligible = [d for d in view["drives"] if d["location"] in selected_bays and not d["eligible"]]
    if ineligible:
        summary = "; ".join(f"{d['location']}: {d.get('label') or d.get('health') or 'not ready'}" for d in ineligible)
        raise StorageRebuildError(
            "Selected drives are not ready for RAID: " + summary
            + ". Inspect their hardware-health details and refresh inventory. Re-saving the same plan does not clear a drive warning."
        )
    used = set()
    for volume in volumes:
        drives = [d for d in view["drives"] if d["location"] in volume.drive_bays]
        count = len(drives)
        level = volume.raid_level
        valid_count = count == 2 if level == "RAID1" else count >= 3 if level == "RAID5" else count >= 4 if level == "RAID6" else count >= 4 and count % 2 == 0 if level == "RAID10" else False
        if (not valid_count or len(set(volume.drive_bays)) != len(volume.drive_bays) or count != len(volume.drive_bays)
                or used.intersection(volume.drive_bays) or volume.size_policy not in {None, "max"}
                or not all(d["eligible"] and d["id"].startswith(intent.controller_ref.rstrip("/") + "/") for d in drives)
                or len({(d["capacity_bytes"], d["media"]) for d in drives}) != 1):
            raise StorageRebuildError("The saved arrays no longer match healthy, separate drive groups. Review and save the storage plan again.")
        used.update(volume.drive_bays)
        spares = [d for d in view["drives"] if d["location"] in volume.spare_bays]
        if (len(spares) != len(volume.spare_bays) or len(set(volume.spare_bays)) != len(volume.spare_bays)
                or len(spares) > 1 or used.intersection(volume.spare_bays)
                or (spares and volume.spare_rebuild_mode != "Dedicated")
                or not all(d["eligible"] and d["id"].startswith(intent.controller_ref.rstrip("/") + "/")
                           and d["media"] == drives[0]["media"]
                           and d["capacity_bytes"] >= max(member["capacity_bytes"] for member in drives) for d in spares)):
            raise StorageRebuildError("The hot spare no longer matches a healthy, unused drive of suitable capacity and media. Review the storage plan again.")
        used.update(volume.spare_bays)
    result = _redfish_settings_payload(intent)
    result["DataGuard"] = "Disabled"
    for volume in result["LogicalDrives"]:
        volume.setdefault("SpareDrives", [])
    return result


def audit(session, actor, event_type, message, data):
    status = data.get("status") or event_type.rsplit(".", 1)[-1]
    event = record_audit_event(session, actor=actor, event_type=event_type, message=message, data=data, to_status=status)
    session.flush()
    return event


def latest_event(session, device_id, kind, attempt_id=None):
    query = select(AuditEvent).where(AuditEvent.event_type == "kit.raid_rebuild." + kind,
        AuditEvent.data_json["device_id"].as_string() == device_id)
    if attempt_id:
        query = query.where(AuditEvent.data_json["attempt_id"].as_string() == attempt_id)
    return session.scalar(query.order_by(AuditEvent.created_at.desc()).limit(1))


def boot_blockers():
    return write_blockers() + current_lab_action_policy().action_blockers("ilo-redfish.raid-boot", ActionCategory.POWER_ACTION)


@router.post("/{profile_id}/raid-rebuild/diagnose")
def diagnose_rebuild(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server = server_in_kit(profile_id, device_id, session)
    try:
        snapshot = read_snapshot(session, device_id)
        result = diagnose_storage(snapshot, read_diagnostic_log(snapshot))
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    # Reconcile only through the existing exact-identity and current-layout verifier.
    unresolved = unresolved_attempt(session, device_id, snapshot, actor)
    result["raid_verification"] = "A recorded operation is still unverified. No new write is enabled by this diagnosis." if unresolved else "No unresolved recorded RAID operation was found."
    result["name"] = server.name
    attempt = latest_event(session, device_id, "attempt")
    audit(session, actor, "kit.raid_rebuild.diagnosis", "Read-only storage diagnosis: " + result["summary"],
          {"profile_id": profile_id, "device_id": device_id, "attempt_id": attempt.id if attempt else None, **result})
    session.commit()
    return result


@router.get("/{profile_id}/raid-rebuild/status")
def rebuild_status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    attempt = latest_event(session, device_id, "attempt")
    if not attempt:
        return {"status": "not_started", "message": "No RAID operation has been submitted.", "active": False}
    result = latest_event(session, device_id, "result", attempt.id)
    verified = latest_event(session, device_id, "verified", attempt.id)
    failed = latest_event(session, device_id, "failed", attempt.id)
    boot = latest_event(session, device_id, "boot_attempt", attempt.id)
    boot_result = latest_event(session, device_id, "boot_result", attempt.id)
    diagnosis = latest_event(session, device_id, "diagnosis", attempt.id)
    state = "verified" if verified else "failed" if failed else "waiting" if boot else "staged" if result and result.data_json.get("status") == "pending" else "uncertain"
    if state == "waiting" and diagnosis and diagnosis.created_at > boot.created_at and diagnosis.data_json.get("status") == "needs_attention":
        state = "needs_attention"
    message = ("RAID operation verified against the server. This is the recorded result, not a live health check." if verified else
               failed.data_json["message"] if failed else
               "The latest diagnosis found storage problems. Review the troubleshooting findings before continuing; the RAID operation is not verified." if state == "needs_attention" else
               boot_result.data_json["message"] if boot_result else
               "Power-on was submitted; its outcome is not yet verified. Do not submit again." if boot else
               "RAID changes are staged, not completed. Review the pending operation, then start the server to apply it." if state == "staged" else
               "The storage submission outcome is uncertain. Inspect pending settings before booting; do not resubmit.")
    sanitize_check = latest_event(session, device_id, "sanitize_check", attempt.id)
    if attempt.data_json["operation"] == "sanitize":
        if sanitize_check and not failed:
            message = sanitize_check.data_json["message"]
            if not verified and sanitize_check.data_json["status"] == "needs_attention":
                state = "needs_attention"
        elif state == "staged":
            message = "Physical-disk erasure staged, not started. Review and approve power-on. This can take hours; do not interrupt it."
    return {"status": state, "message": message, "active": not bool(verified or failed), "attempt_id": attempt.id,
            "erase_recovery": {"rejected_method": failed.data_json["rejected_method"], "message": failed.data_json["message"]}
                if failed and failed.data_json.get("reason") == "erase_method_rejected" else None,
            "sanitization": sanitize_check.data_json if sanitize_check else None,
            "erase_scope": [{**d, "erase_pattern": attempt.data_json.get("drive_methods", {}).get(d["identity"], attempt.data_json.get("erase_pattern"))}
                            for d in attempt.data_json.get("drive_scope", [])] if attempt.data_json["operation"] == "sanitize" else None,
            "operation": attempt.data_json["operation"], "submitted_at": attempt.created_at.replace(tzinfo=UTC).isoformat(),
            "boot_started_at": boot.created_at.replace(tzinfo=UTC).isoformat() if boot else None,
            "verified_at": verified.created_at.replace(tzinfo=UTC).isoformat() if verified else None,
            "boot_blockers": (boot_blockers() + (reset_blockers() if attempt.data_json["operation"] == "reset" else [])
                              + (disk_sanitization.policy_blockers(device_id, session) if attempt.data_json["operation"] == "sanitize" else [])) if state == "staged" else []}


def build_boot_review(session, profile_id, device_id):
    server = server_in_kit(profile_id, device_id, session)
    attempt = latest_event(session, device_id, "attempt")
    if not attempt or latest_event(session, device_id, "verified", attempt.id) or latest_event(session, device_id, "failed", attempt.id):
        raise StorageRebuildError("No unverified RAID operation needs a boot.")
    result = latest_event(session, device_id, "result", attempt.id)
    if not result or result.data_json.get("status") != "pending":
        raise StorageRebuildError("Storage acceptance is uncertain. Inspect the server's pending configuration; power-on is blocked.")
    if latest_event(session, device_id, "boot_attempt", attempt.id):
        raise StorageRebuildError("Power-on was already submitted for this operation. Verify the result; do not resubmit.")
    snapshot = read_snapshot(session, device_id)
    if snapshot["identity"] != attempt.data_json["identity"]:
        raise StorageRebuildError("Server identity changed since the RAID submission. No power request was sent.")
    desired = attempt.data_json["payload"]
    if (not snapshot["pending_differs"]
            or (attempt.data_json["operation"] != "reset" and not requested_layout_matches(snapshot["pending"], desired))
            or snapshot["pending"].get("Actions", []) != desired.get("Actions", [])
            or snapshot["pending"].get("DataGuard") != desired.get("DataGuard")):
        raise StorageRebuildError("Pending RAID settings do not match the accepted operation. Verify or inspect them before booting.")
    if snapshot["power"] != "Off":
        raise StorageRebuildError("The server is not powered off. Check the RAID result first; the app will not force a restart.")
    if any(i["health"] in {"Critical", "Failed"} and i["group"] != "Logical volume" for i in health_issues(snapshot["probe"])):
        raise StorageRebuildError("A component reports critical health. Resolve it before starting the server.")
    path = read_boot_action(snapshot)
    blockers = boot_blockers()
    if attempt.data_json["operation"] == "reset":
        blockers += reset_blockers()
        blockers += reset_target_blockers(device_id)
    if attempt.data_json["operation"] == "sanitize":
        blockers += disk_sanitization.policy_blockers(device_id, session)
        if disk_sanitization.scope(disk_sanitization.drive_rows(snapshot)) != attempt.data_json["drive_scope"]:
            blockers.append("Physical drives changed since erasure approval. Power-on is blocked.")
        original_raw = attempt.data_json.get("raw_preparation")
        if original_raw:
            controllers = [c for c in snapshot["probe"].get("storage", {}).get("controllers", []) if c.get("Model")]
            fresh_raw = disk_sanitization.raw_drive_preparation(snapshot, disk_sanitization.drive_rows(snapshot),
                                                              controllers[0] if len(controllers) == 1 else {})
            if (not fresh_raw or not fresh_raw["assignment_verified"]
                    or fresh_raw["evidence"] != original_raw["evidence"]):
                blockers.append("Raw-drive preparation changed after the wipe request. Power-on is blocked; check controller mode, disk assignment and pending settings.")
    return snapshot, {"profile_id": profile_id, "device_id": device_id, "attempt_id": attempt.id,
        "name": server.name, "operation": attempt.data_json["operation"], "identity": snapshot["identity"],
        "state_digest": snapshot["state_digest"], "pending_digest": digest(snapshot["pending"]),
        "pending_payload": desired, "path": path, "method": "POST", "payload": {"ResetType": "On"},
        "confirmation": f"START RAID {server.name}", "blockers": blockers, "apply_enabled": not blockers,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}


@router.post("/{profile_id}/raid-rebuild/boot-preview")
def preview_boot(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    try:
        _, review = build_boot_review(session, profile_id, device_id)
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    event = audit(session, actor, "kit.raid_rebuild.boot_preview", "Read-only review of pending RAID and server power-on.", review)
    session.commit()
    return {**review, "preview_id": event.id}


@router.post("/{profile_id}/raid-rebuild/boot")
def apply_boot(profile_id: str, device_id: str, payload: BootApply,
               session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    session.scalar(select(DeviceInventory).where(DeviceInventory.id == device_id).with_for_update())
    event = session.get(AuditEvent, payload.preview_id)
    if (not event or event.event_type != "kit.raid_rebuild.boot_preview"
            or event.data_json.get("profile_id") != profile_id or event.data_json.get("device_id") != device_id):
        raise HTTPException(404, "This power-on preview does not belong to this kit and server.")
    review = event.data_json
    if payload.confirmation != review["confirmation"]:
        raise HTTPException(422, "Enter the exact power-on confirmation phrase.")
    if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
        raise HTTPException(409, "Power-on preview expired. Review the pending operation again.")
    if boot_blockers():
        raise HTTPException(409, " ".join(boot_blockers()))
    try:
        snapshot, fresh = build_boot_review(session, profile_id, device_id)
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    if fresh["blockers"] or any(fresh[k] != review[k] for k in ("attempt_id", "identity", "state_digest", "pending_digest", "path", "confirmation")):
        raise HTTPException(409, "The server or pending configuration changed. Review again; no power request was sent.")
    # Persist a single-use claim before power-on, including when the response is lost.
    claim = audit(session, actor, "kit.raid_rebuild.boot_attempt", "Confirmed power-on to apply the reviewed RAID operation.",
                  {**review, "preview_id": event.id, "confirmations": payload.model_dump()})
    session.commit()
    result = start_server(snapshot, review["path"])
    audit(session, actor, "kit.raid_rebuild.boot_result", result["message"],
          {"profile_id": profile_id, "device_id": device_id, "attempt_id": review["attempt_id"], "boot_attempt_id": claim.id, **result})
    session.commit()
    return result


def reconcile_erase_rejection(session, device_id, snapshot, attempt, actor):
    if latest_event(session, device_id, "failed", attempt.id):
        return
    boot = latest_event(session, device_id, "boot_attempt", attempt.id)
    previous = latest_event(session, device_id, "sanitize_check", attempt.id)
    result = latest_event(session, device_id, "result", attempt.id)
    rejected = disk_sanitization.rejected_method(snapshot, attempt.data_json,
        previous.data_json if previous else None, boot.created_at if boot else None)
    if rejected and result and result.data_json.get("status") == "pending":
        audit(session, actor, "kit.raid_rebuild.failed", rejected["message"],
              {"profile_id": attempt.data_json["profile_id"], "device_id": device_id,
               "attempt_id": attempt.id, "identity": snapshot["identity"], **rejected})


def unresolved_attempt(session, device_id, snapshot, actor):
    attempts = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.raid_rebuild.attempt",
        AuditEvent.data_json["device_id"].as_string() == device_id).order_by(AuditEvent.created_at.desc())).all()
    verified = {r.data_json.get("attempt_id") for r in session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "kit.raid_rebuild.verified", AuditEvent.data_json["device_id"].as_string() == device_id))}
    # A later verified write on this device supersedes older unverified attempts: they were followed
    # by a proven, successful storage operation (observed: a 09-22 reset failure, then a verified reset).
    newest_verified = next((a.created_at for a in attempts if a.id in verified), None)
    for attempt in attempts:
        if attempt.id in verified:
            continue
        if newest_verified is not None and attempt.created_at < newest_verified:
            continue
        if attempt.data_json.get("operation") == "sanitize":
            reconcile_erase_rejection(session, device_id, snapshot, attempt, actor)
            failure = latest_event(session, device_id, "failed", attempt.id)
            if not failure or failure.data_json.get("reason") != "erase_method_rejected":
                return "Physical-disk erasure is unresolved. Verify every reviewed drive before any RAID changes."
        if latest_event(session, device_id, "failed", attempt.id):
            if snapshot["identity"] != attempt.data_json["identity"] or snapshot["pending_differs"]:
                return "Target changed or new pending settings exist after the recorded failure. Diagnose before another write."
            continue
        boot = latest_event(session, device_id, "boot_attempt", attempt.id)
        result = latest_event(session, device_id, "result", attempt.id)
        rejected = confirmed_rejection(snapshot, attempt.data_json, boot.created_at if boot else None)
        if rejected and result and result.data_json.get("status") == "pending":
            audit(session, actor, "kit.raid_rebuild.failed", rejected["message"],
                  {"profile_id": attempt.data_json["profile_id"], "device_id": device_id,
                   "attempt_id": attempt.id, "identity": snapshot["identity"], **rejected})
            continue
        matches = (snapshot["identity"] == attempt.data_json["identity"] and not snapshot["pending_differs"]
                   and requested_layout_matches(snapshot["current"], attempt.data_json["payload"]))
        messages = snapshot["current"].get("@Redfish.Settings", {}).get("Messages", [])
        success = bool(messages) and all(str(m.get("MessageId", "")).endswith(".Success") for m in messages)
        if matches and success:
            audit(session, actor, "kit.raid_rebuild.verified", "HPE current configuration matches the staged RAID operation.",
                  {"profile_id": attempt.data_json["profile_id"], "device_id": device_id, "attempt_id": attempt.id,
                   "operation": attempt.data_json["operation"], "identity": snapshot["identity"]})
        else:
            return "A previous storage request has not been verified. Inspect pending settings in HPE SSA; boot only after reviewing them, then refresh. Do not resubmit the request."
    return None


def build_review(session, profile_id, device_id, operation, actor, erase_pattern="auto"):
    server = server_in_kit(profile_id, device_id, session)
    snapshot = read_snapshot(session, device_id)
    if operation == "sanitize":
        details = disk_sanitization.plan(snapshot, erase_pattern, device_id, session)
        details["blockers"] += write_blockers()
        unresolved = unresolved_attempt(session, device_id, snapshot, actor)
        if unresolved:
            details["blockers"].append(unresolved)
        failures = session.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "kit.raid_rebuild.failed",
            AuditEvent.data_json["device_id"].as_string() == device_id)).all()
        rejected = {f.data_json["rejected_method"] for f in failures
                    if f.data_json.get("reason") == "erase_method_rejected"
                    and f.data_json.get("capability_context") == details["capability_context"]
                    and f.data_json.get("drive_scope") == details["drive_scope"]}
        if rejected.intersection(details["drive_methods"].values()):
            details["blockers"].append("This erase method was rejected by the current hardware. Choose a different method; the same request cannot be repeated.")
        options = erase_options(snapshot["probe"], executor_available=True, current=True,
                                arrays_present=bool(snapshot["current"].get("LogicalDrives")))
        for option in options["options"]:
            if option["id"] in rejected:
                option.update(selectable=False, status="Rejected by controller",
                              reason="This hardware rejected this method. Choose a different erase method.")
        controllers = [c for c in snapshot["probe"].get("storage", {}).get("controllers", []) if c.get("Model")]
        return snapshot, {**details, "profile_id": profile_id, "device_id": device_id, "operation": operation,
            "erase_options": options,
            "name": server.name, "host": snapshot["config"].host, "controller": controllers[0]["Model"],
            "identity": snapshot["identity"], "state_digest": snapshot["state_digest"],
            "intent_digest": digest({"scope": details["drive_scope"], "methods": details["drive_methods"],
                                     "raw_preparation": details["raw_preparation"]}), "method": "PATCH", "path": snapshot["path"],
            "power": snapshot["power"], "arrays_present": bool(snapshot["current"].get("LogicalDrives")),
            "authorization_expires_at": disk_sanitization.enrollment(session, device_id).get("expires_at"),
            "volumes": [], "empty_bays": [], "warnings": [details["scope_note"], details["assurance"]],
            "confirmation": f"ERASE ALL {len(details['drives'])} DISKS {server.name}",
            "apply_enabled": not details["blockers"], "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
    view = disk_preparation(profile_id, device_id, session)
    if view["blockers"]:
        raise StorageRebuildError(" ".join(view["blockers"]))
    intent = get_hpe_raid_intent(session, device_id)
    payload = planned_payload(intent, view)
    blockers = write_blockers()
    if snapshot["power"] != "Off":
        blockers.append("Shut down the server cleanly first. This operation requires the server power state to be Off; iLO stays on.")
    pending = unresolved_attempt(session, device_id, snapshot, actor)
    if pending:
        blockers.append(pending)
    previous = latest_event(session, device_id, "attempt")
    previous_failure = latest_event(session, device_id, "failed", previous.id) if previous else None
    corrected_reset = bool(previous and previous_failure
        and previous.data_json.get("operation") == "reset"
        and previous.data_json.get("payload") == {"Actions": [{"Action": "FactoryReset"}], "DataGuard": "Disabled"}
        and "SmartStorageMessages.2.0.1.PropertyKeyMissing" in previous_failure.data_json.get("codes", []))
    if previous and latest_event(session, device_id, "failed", previous.id) and operation == "clear":
        blockers.append("The previous deletion was rejected by the controller. Repeating it is blocked. Review Advanced storage recovery instead.")
    if (previous and previous.data_json.get("operation") == "reset" and operation == "reset"
            and previous_failure and not corrected_reset):
        blockers.append("The controller rejected the reset request. Repeating the same request is blocked; the recovery method must be corrected first.")
    if snapshot["pending_differs"]:
        blockers.append("Pending storage settings differ from the current layout. Resolve them in HPE SSA before staging another operation.")
    issues = health_issues(snapshot["probe"])
    if any(i["health"] in {"Critical", "Failed"} and i["group"] != "Logical volume" for i in issues):
        blockers.append("A known component still reports critical health. Diagnose it before storage changes; acknowledgement does not bypass this block.")
    if operation in {"clear", "reset"}:
        if not intent.wipe_existing_logical_drives or not snapshot["current"]["LogicalDrives"]:
            blockers.append("Review and save removal of the existing logical volumes first. No clear is needed when the controller is already empty.")
        payload = {"DataGuard": "Disabled", "LogicalDrives": [], "Actions": [{"Action": "ClearConfigurationMetadata"}]}
        if operation == "reset":
            blockers += reset_blockers()
            blockers += reset_target_blockers(device_id)
            payload = {"Actions": [{"Action": "FactoryReset"}], "DataGuard": "Disabled"}
            if corrected_reset:
                payload["LogicalDrives"] = []
    elif snapshot["current"]["LogicalDrives"]:
        blockers.append("Existing logical volumes remain. Clear them, complete the attended boot, and verify the empty controller before creating the new arrays.")
    if operation == "create":
        controllers = [c for c in snapshot["probe"].get("storage", {}).get("controllers", []) if c.get("Model")]
        if len(controllers) != 1 or (controllers[0].get("Status") or {}).get("Health") != "OK":
            blockers.append("The storage controller must report healthy before new arrays are created. Diagnose controller and cache warnings first; an empty layout alone is not build-ready.")
    expected_count = len(snapshot["current"]["LogicalDrives"])
    if expected_count != len(view["volumes"]):
        blockers.append("The configuration and inventory disagree about existing volumes. Refresh or inspect in HPE SSA.")
    return snapshot, {"profile_id": profile_id, "device_id": device_id, "operation": operation,
        "name": server.name, "host": view["host"], "controller": view["controllers"][0]["model"],
        "state_digest": snapshot["state_digest"], "intent_digest": digest(intent.model_dump()), "identity": snapshot["identity"],
        "payload": payload, "path": snapshot["path"], "method": "PUT", "volumes": view["volumes"],
        "empty_bays": [d["location"] for d in view["drives"] if d["presence"] != "identified"],
        "warnings": [i["title"] + ": " + "; ".join(i["details"]) for i in issues],
        "blockers": blockers, "apply_enabled": not blockers,
        "confirmation": f"{ {'clear': 'CLEAR RAID', 'create': 'CREATE RAID', 'reset': 'RESET STORAGE CONTROLLER'}[operation]} {server.name}",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}


@router.get("/{profile_id}/raid-rebuild/erase-options")
def read_erase_options(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    health = read_health_review(session, profile_id, device_id)
    probe, _ = get_probe_result("ilo-redfish", scope=device_id)
    return erase_options(probe or {}, current=health["current"])


@router.post("/{profile_id}/raid-rebuild/preview")
def preview_rebuild(profile_id: str, device_id: str, payload: RebuildPreview,
                    session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    try:
        _, review = build_review(session, profile_id, device_id, payload.operation, actor, payload.erase_pattern)
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    event = audit(session, actor, "kit.raid_rebuild.preview", "Read-only RAID rebuild preview. No storage writes sent.", review)
    session.commit()
    return {**review, "preview_id": event.id}


class SanitizeAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=36, max_length=36)
    confirmation: str = Field(min_length=1, max_length=250)
    vendor_support_reviewed: Literal[True]
    sources: dict[str, str] = Field(min_length=1, max_length=24)


@router.post("/{profile_id}/raid-rebuild/sanitize-authorization")
def authorize_sanitization(profile_id: str, device_id: str, payload: SanitizeAuthorization,
                           session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server = server_in_kit(profile_id, device_id, session)
    session.scalar(select(DeviceInventory).where(DeviceInventory.id == device_id).with_for_update())
    blockers = write_blockers()
    if blockers:
        raise HTTPException(409, " ".join(blockers))
    event = session.get(AuditEvent, payload.preview_id)
    if (not event or event.event_type != "kit.raid_rebuild.preview"
            or event.data_json.get("profile_id") != profile_id
            or event.data_json.get("device_id") != device_id
            or event.data_json.get("operation") != "sanitize"):
        raise HTTPException(404, "Open an erase review for this server first.")
    review = event.data_json
    if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
        raise HTTPException(409, "Review expired. Refresh disk readiness first.")
    if payload.confirmation != f"AUTHORIZE ERASURE {server.name}":
        raise HTTPException(422, "Enter the exact authorization phrase.")
    try:
        snapshot, fresh = build_review(session, profile_id, device_id, "sanitize", actor, review["erase_pattern"])
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    if any(fresh[k] != review[k] for k in ("identity", "drive_scope", "drive_methods", "capability_context")):
        raise HTTPException(409, "Hardware changed. Refresh the erase review.")
    drives = fresh["drives"]
    if (not drives or len(drives) > 24 or len({d["identity"] for d in drives}) != len(drives)
            or set(payload.sources) != {d["identity"] for d in drives}
            or any(not d["identity"] or not d["model"] or not d["firmware"]
                   or d["media"] not in disk_sanitization.MEDIA_METHODS
                   or d["erase_pattern"] not in disk_sanitization.METHODS for d in drives)):
        raise HTTPException(422, "Every identified disk needs a supported method and its own evidence reference.")
    if any(not 10 <= len(source.strip()) <= 2000 for source in payload.sources.values()):
        raise HTTPException(422, "Provide a vendor document reference and applicability notes (10-2000 characters) for each disk.")
    expires = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    approvals = [{**fresh["capability_context"], "drive_identity": d["identity"],
                  "drive_model": d["model"], "drive_firmware": d["firmware"],
                  "method": d["erase_pattern"], "source": payload.sources[d["identity"]].strip(),
                  "reviewed_by": actor, "expires_at": expires} for d in drives]
    audit(session, actor, "kit.raid_rebuild.sanitize_enrollment",
          "Operator recorded vendor-support review and authorized this server for erasure. No hardware writes sent.",
          {"profile_id": profile_id, "device_id": device_id, "identity": snapshot["identity"],
           "expires_at": expires, "approvals": approvals, "preview_id": event.id})
    session.commit()
    return {"expires_at": expires, "message": "Authorization saved for 24 hours. No disks changed. Refresh readiness before proceeding."}


@router.post("/{profile_id}/raid-rebuild/apply")
def apply_rebuild(profile_id: str, device_id: str, payload: RebuildApply,
                  session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    session.scalar(select(DeviceInventory).where(DeviceInventory.id == device_id).with_for_update())
    event = session.get(AuditEvent, payload.preview_id)
    if not event or event.event_type != "kit.raid_rebuild.preview" or event.data_json.get("profile_id") != profile_id or event.data_json.get("device_id") != device_id:
        raise HTTPException(404, "This preview does not belong to this server and kit.")
    review = event.data_json
    if review.get("operation") == "sanitize" and not payload.physical_erase_confirmed:
        raise HTTPException(422, "Explicit physical-disk erasure acknowledgement is required.")
    if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
        raise HTTPException(409, "The preview expired. Read and review the server again.")
    if payload.confirmation != review["confirmation"] or sorted(payload.empty_bays_confirmed) != sorted(review["empty_bays"]):
        raise HTTPException(422, "Enter the exact confirmation and confirm the listed empty/unidentified bays after physical inspection.")
    prior = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "kit.raid_rebuild.attempt",
        AuditEvent.data_json["preview_id"].as_string() == event.id))
    if prior:
        raise HTTPException(409, "This preview has already been submitted. Read back the result; do not retry it.")
    if write_blockers():
        raise HTTPException(409, " ".join(write_blockers()))
    try:
        snapshot, fresh = build_review(session, profile_id, device_id, review["operation"], actor, review.get("erase_pattern", "SanitizeRestrictedOverwrite"))
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    if fresh["blockers"] or any(fresh[k] != review[k] for k in ("state_digest", "intent_digest", "payload", "confirmation", "empty_bays")):
        raise HTTPException(409, " ".join(fresh["blockers"]) or "The server, drives, pending settings or saved plan changed. Create a new preview.")
    if review["operation"] == "sanitize" and fresh["capability_digest"] != review["capability_digest"]:
        raise HTTPException(409, "Erase capability approval changed. Create a new preview.")
    # Commit the claim before the network write, so a lost response never invites replay.
    attempt = audit(session, actor, "kit.raid_rebuild.attempt", "Confirmed RAID write is starting; outcome unverified.",
                    {**review, "preview_id": event.id, "confirmations": payload.model_dump(exclude={"preview_id"})})
    session.commit()
    result = (stage_configuration(snapshot, review["payload"], sanitize=True) if review["operation"] == "sanitize"
              else stage_configuration(snapshot, review["payload"]))
    audit(session, actor, "kit.raid_rebuild.result", result["message"],
          {"profile_id": profile_id, "device_id": device_id, "attempt_id": attempt.id, "operation": review["operation"], **result})
    session.commit()
    return {**result, "attempt_id": attempt.id, "verified": False, "reboot_sent": False, "secure_erase_sent": review["operation"] == "sanitize"}


@router.post("/{profile_id}/raid-rebuild/verify")
def verify_rebuild(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    attempt = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "kit.raid_rebuild.attempt",
        AuditEvent.data_json["device_id"].as_string() == device_id).order_by(AuditEvent.created_at.desc()))
    if not attempt:
        return {"status": "not_started", "verified": False, "message": "No staged RAID operation is recorded for this server. Refresh drive inventory to inspect changes made outside the app."}
    try:
        snapshot = read_snapshot(session, device_id)
        if attempt.data_json["operation"] == "sanitize":
            boot = latest_event(session, device_id, "boot_attempt", attempt.id)
            previous = latest_event(session, device_id, "sanitize_check", attempt.id)
            result = disk_sanitization.verify(snapshot, attempt.data_json, previous.data_json if previous else None,
                                              boot.created_at if boot else None)
            reconcile_erase_rejection(session, device_id, snapshot, attempt, actor)
            failure = latest_event(session, device_id, "failed", attempt.id)
            if failure and failure.data_json.get("reason") == "erase_method_rejected":
                result.update(status="failed", message=failure.data_json["message"])
            audit(session, actor, "kit.raid_rebuild.sanitize_check", result["message"],
                  {**result, "device_id": device_id, "profile_id": profile_id, "attempt_id": attempt.id})
            if result["verified"] and not latest_event(session, device_id, "verified", attempt.id):
                audit(session, actor, "kit.raid_rebuild.verified", result["message"],
                      {**result, "device_id": device_id, "profile_id": profile_id, "attempt_id": attempt.id, "operation": "sanitize"})
            session.commit()
            return result
        blocker = unresolved_attempt(session, device_id, snapshot, actor)
        messages = snapshot["current"].get("@Redfish.Settings", {}).get("Messages", [])
        success = bool(messages) and all(str(m.get("MessageId", "")).endswith(".Success") for m in messages)
        matches = success and snapshot["identity"] == attempt.data_json["identity"] and not snapshot["pending_differs"] and requested_layout_matches(snapshot["current"], attempt.data_json["payload"])
    except StorageRebuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    verified = not blocker and matches
    failed = latest_event(session, device_id, "failed", attempt.id)
    if failed:
        return {"status": "failed", "verified": False, "message": failed.data_json["message"]}
    return {"status": "verified" if verified else "unverified", "verified": verified,
            "message": ("Verified: the controller reports reset success and no logical volumes. This does not certify secure erasure or clear hardware health alerts." if attempt.data_json["operation"] == "reset" else "Verified: the old RAID layout is cleared." if attempt.data_json["operation"] == "clear" else "Verified: the new RAID arrays match the saved operation.") if verified else
            blocker or "The current layout differs from the last staged operation. Review the server in HPE SSA."}


@router.get("/{profile_id}/raid-rebuild/sanitization-report")
def sanitization_report(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server = server_in_kit(profile_id, device_id, session)
    attempt = session.scalar(select(AuditEvent).where(
        AuditEvent.event_type == "kit.raid_rebuild.attempt",
        AuditEvent.data_json["device_id"].as_string() == device_id,
        AuditEvent.data_json["profile_id"].as_string() == profile_id,
        AuditEvent.data_json["operation"].as_string() == "sanitize",
    ).order_by(AuditEvent.created_at.desc()).limit(1))
    if not attempt:
        return {"status": "not_started", "message": "No physical-disk erasure has been submitted for this server."}
    check = latest_event(session, device_id, "sanitize_check", attempt.id)
    verified = latest_event(session, device_id, "verified", attempt.id)
    failed = latest_event(session, device_id, "failed", attempt.id)
    return {"status": "verified" if verified else "failed" if failed else "unverified", "historical": True,
            "rejection": failed.data_json if failed else None,
            "server": server.name, "profile_id": profile_id, "device_id": device_id, "attempt_id": attempt.id,
            "submitted_at": attempt.created_at.replace(tzinfo=UTC).isoformat(), "actor": attempt.actor,
            "method": attempt.data_json["erase_pattern"], "scope": attempt.data_json["drive_scope"],
            "drive_methods": attempt.data_json.get("drive_methods", {
                d["identity"]: attempt.data_json["erase_pattern"] for d in attempt.data_json["drive_scope"]}),
            "scope_note": attempt.data_json["scope_note"], "assurance": attempt.data_json["assurance"],
            "capability_evidence": attempt.data_json["capability_evidence"],
            "last_check": check.data_json if check else None,
            "verified_at": verified.created_at.replace(tzinfo=UTC).isoformat() if verified else None,
            "message": "Recorded evidence only; this is not proof of current contents after subsequent writes or a compliance certificate."}
