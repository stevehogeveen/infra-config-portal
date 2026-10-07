"""Pure completion rules for server-collected iLO firmware observations.

The observation must be supplied by a trusted collector, never an API request.
This module performs no collection and does not release operation locks.
"""
from datetime import UTC, datetime, timedelta

from app.services.spp_assessment import numeric_version

MAX_READBACK_AGE = timedelta(minutes=5)


def evaluate_ilo_readback(
    *, device_id: str, target_identity_sha256: str, target_version: str,
    submitted_at: datetime, observation: dict, now: datetime | None = None,
    target_hardware_identity_sha256: str | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    blockers = []
    checked = observation.get("checked_at")
    try:
        checked_at = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        if checked_at.tzinfo is None or submitted_at.tzinfo is None or now.tzinfo is None:
            raise ValueError("timezone required")
        if checked_at <= submitted_at or checked_at > now or now - checked_at > MAX_READBACK_AGE:
            raise ValueError("not fresh post-submission evidence")
    except (AttributeError, TypeError, ValueError):
        blockers.append("Fresh, timestamped post-submission readback is required.")
    if (observation.get("source") != "live-ilo-firmware-readback"
            or observation.get("authenticated") is not True
            or observation.get("exact_target_only") is not True
            or observation.get("identity_verified") is not True):
        blockers.append("Authenticated exact-target firmware readback is required.")
    # Reviews that recorded the server's hardware identity compare that: the iLO's own identity
    # fields can legitimately change when its firmware is updated. Older reviews compare the full one.
    if target_hardware_identity_sha256:
        identity_ok = observation.get("target_hardware_identity_sha256") == target_hardware_identity_sha256
    else:
        identity_ok = bool(target_identity_sha256) and observation.get("target_identity_sha256") == target_identity_sha256
    if observation.get("device_id") != device_id or not identity_ok:
        blockers.append("Readback does not match the reviewed hardware identity.")
    expected = numeric_version(target_version, "ilo")
    installed = numeric_version(str(observation.get("manager_firmware_version") or ""), "ilo")
    if expected is None or installed is None or expected != installed:
        blockers.append("The reviewed iLO version has not been independently observed.")
    # Busy/unknown state is not completion, even if a version string has changed.
    if observation.get("update_state") not in {"Idle", "Complete"}:
        blockers.append("Firmware update service is not verified idle or complete.")
    if observation.get("errors") != []:
        blockers.append("Firmware readback has errors or an incomplete error check.")
    return {
        "status": "uncertain" if blockers else "verified",
        "evidence_at": None if blockers else checked,
        "device_id": device_id, "blockers": blockers, "safe_to_retry": False,
        "message": ("Completion is not proven; keep this attempt blocked." if blockers
                    else "The reviewed iLO version was read back on the exact target."),
    }
