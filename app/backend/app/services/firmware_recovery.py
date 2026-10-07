"""Explicit lab-operator closure of an unverified attempt; never a hardware retry."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.config import settings
from app.models import AuditEvent, FirmwareApproval, GuardedOperation, RuntimeDispatchLease, utcnow
from app.services.audit import record_audit_event
from app.services.guarded_operation_ledger import OperationConflict, recorded_result
from app.services.spp_assessment import numeric_version

PHRASE = "CLOSE UNVERIFIED UPDATE"
WARNING = (
    "The previous upload outcome is unknown. Closing this attempt records an unverified "
    "failure and releases its app lock; it does not prove nothing happened or resend firmware. "
    "Any further update requires a fresh review and separate installation approval."
)


def _event(session, operation_id, kind):
    return session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == kind,
            AuditEvent.data_json["operation_id"].as_string() == operation_id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )


def _eligibility(session, profile_id, device_id, operation_id):
    operation = session.scalar(
        select(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.profile_id == profile_id,
            GuardedOperation.device_id == device_id,
            GuardedOperation.resource == "firmware-execution",
        )
        .execution_options(populate_existing=True)
    )
    if operation is None:
        raise OperationConflict("No matching firmware operation exists.")
    blockers = []
    if settings.provider_mode not in {"mock", "local-lab-readwrite"}:
        blockers.append("Operator close-out is available only for the configured local lab.")
    evidence = _event(session, operation_id, "firmware.readback.unproven")
    # A "running" install whose latest read shows the iLO idle, error-free, on the exact target
    # version has finished; closing it releases the lock without any risk of a second send.
    finished = False
    if operation.status == "running" and evidence is not None:
        review = session.scalar(select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id))
        observed = evidence.data_json.get("observation") or {}
        target = numeric_version(str((review.intent_json if review else {}).get("target_version") or ""), "ilo")
        seen = numeric_version(str(observed.get("manager_firmware_version") or ""), "ilo")
        finished = bool(target and seen == target and observed.get("update_state") == "Idle"
                        and observed.get("errors") == [] and observed.get("identity_verified") is True)
    if (operation.status != "uncertain" and not finished) or operation.active_device != device_id:
        blockers.append("Only a settled uncertain upload, or a finished install the app could not match, can be closed.")
    # Request-activity leases are not hardware dispatch leases. The upload lease
    # remains present through send/cleanup, including after a worker crash.
    leases = session.scalars(select(RuntimeDispatchLease))
    if any(not row.action_id.startswith(("POST ", "PUT ", "PATCH ", "DELETE ")) for row in leases):
        blockers.append("A hardware dispatch is still in flight or unreconciled.")
    evidence = _event(session, operation_id, "firmware.readback.unproven")
    return operation, evidence, blockers


def preview_closure(session, *, profile_id, device_id, operation_id, actor):
    operation, evidence, blockers = _eligibility(session, profile_id, device_id, operation_id)
    token = secrets.token_hex(32) if not blockers else None
    expires = datetime.now(UTC) + timedelta(minutes=5)
    if token:
        record_audit_event(
            session,
            actor=actor,
            event_type="firmware.recovery.review",
            message="Reviewed closure of an unverified firmware attempt; no hardware action.",
            data={
                "operation_id": operation.id,
                "profile_id": profile_id,
                "device_id": device_id,
                "evidence_id": evidence.id if evidence else None,
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "expires_at": expires.isoformat(),
            },
        )
        session.commit()
    return {
        "operation_id": operation_id,
        "profile_id": profile_id,
        "device_id": device_id,
        "can_close": not blockers,
        "blockers": blockers,
        "review_token": token,
        "expires_at": expires.isoformat() if token else None,
        "confirmation_phrase": PHRASE if token else None,
        "message": WARNING,
        "evidence_at": (evidence.data_json.get("observation") or {}).get("checked_at")
        if evidence
        else None,
    }


def close_unverified(
    session, *, profile_id, device_id, operation_id, actor, review_token, confirmation_phrase
):
    # Serialize against completion and another close-out; no adapter is called.
    session.scalar(
        select(GuardedOperation).where(GuardedOperation.id == operation_id).with_for_update()
    )
    operation, evidence, blockers = _eligibility(session, profile_id, device_id, operation_id)
    review = _event(session, operation_id, "firmware.recovery.review")
    if blockers:
        raise OperationConflict(" ".join(blockers))
    if (
        review is None
        or review.actor != actor
        or confirmation_phrase != PHRASE
        or not secrets.compare_digest(
            review.data_json["token_hash"], hashlib.sha256(review_token.encode()).hexdigest()
        )
        or datetime.fromisoformat(review.data_json["expires_at"]) <= datetime.now(UTC)
    ):
        raise OperationConflict("Close-out review is missing, expired, changed or not confirmed.")
    changed = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.status.in_(("uncertain", "running")),  # running only when read back finished
            GuardedOperation.active_device == device_id,
        )
        .values(status="failed", active_device=None, updated_at=utcnow())
    )
    if changed.rowcount != 1:
        raise OperationConflict("Operation changed; review its current status.")
    record_audit_event(
        session,
        actor=actor,
        event_type="firmware.operation.closed_unverified",
        message="Unverified update attempt closed by the operator. No firmware was resent; a fresh review is required.",
        data={
            "operation_id": operation_id,
            "profile_id": profile_id,
            "device_id": device_id,
            "evidence_id": evidence.id if evidence else None,
            "review_id": review.id,
            "dispatch_prevented": False,
            "resolution": "operator_closed_unverified",
        },
    )
    session.commit()
    session.refresh(operation)
    return recorded_result(operation, session=session)
