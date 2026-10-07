"""Durable dispatch claims. No hardware adapters and no automatic retry.

Each mutation owns its transaction; use a dedicated session. A committed running
claim must precede any future external send. A crashed claimant stays locked.
"""

import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditEvent, FirmwareApproval, GuardedOperation, utcnow
from app.services.audit import record_audit_event

RESOURCES = frozenset({"firmware-execution", "drive-return-to-service", "esxi-install", "parts-update", "windows-deploy"})


class OperationConflict(ValueError):
    pass


def find_attempt(
    session: Session, profile_id: str, device_id: str, resource: str, idempotency_key: str
):
    return session.scalar(
        select(GuardedOperation)
        .where(
            GuardedOperation.profile_id == profile_id,
            GuardedOperation.device_id == device_id,
            GuardedOperation.resource == resource,
            GuardedOperation.idempotency_key == idempotency_key,
        )
        .execution_options(populate_existing=True)
    )


def reserve(
    session: Session,
    *,
    profile_id: str,
    device_id: str,
    resource: str,
    idempotency_key: str,
    reviewed_intent: dict,
    actor: str,
    firmware_review_id: str | None = None,
) -> GuardedOperation:
    """Internal only: caller must validate approval/capability before reserving.

    reviewed_intent must contain only non-secret immutable target/package evidence.
    Only its digest is retained. This function does not establish capability.
    """
    if resource not in RESOURCES or not reviewed_intent:
        raise ValueError("Unsupported resource or empty reviewed intent")
    digest = hashlib.sha256(
        json.dumps(
            reviewed_intent,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    existing = find_attempt(session, profile_id, device_id, resource, idempotency_key)
    if existing:
        if existing.intent_hash != digest:
            raise OperationConflict("Attempt key is already bound to a different intent")
        return existing
    operation = GuardedOperation(
        profile_id=profile_id,
        device_id=device_id,
        resource=resource,
        idempotency_key=idempotency_key,
        intent_hash=digest,
        active_device=device_id,
    )
    try:
        session.add(operation)
        session.flush()
        if firmware_review_id is not None:
            review = session.get(FirmwareApproval, firmware_review_id)
            if (
                resource != "firmware-execution"
                or review is None
                or review.profile_id != profile_id
                or review.device_id != device_id
                or review.actor != actor
                or review.token_hash != reviewed_intent.get("review_token_sha256")
                or review.intent_json != reviewed_intent.get("intent")
            ):
                raise OperationConflict("Persisted firmware review does not match this operation")
            consumed = session.execute(
                update(FirmwareApproval)
                .where(
                    FirmwareApproval.id == firmware_review_id,
                    FirmwareApproval.operation_id.is_(None),
                    FirmwareApproval.expires_at > utcnow(),
                )
                .values(operation_id=operation.id)
                .execution_options(synchronize_session="fetch")
            )
            if consumed.rowcount != 1:
                raise OperationConflict("Firmware review expired or was already consumed")
        record_audit_event(
            session,
            actor=actor,
            event_type="guarded.operation.reserved",
            message="Operation reserved; no hardware dispatch.",
            data={
                "operation_id": operation.id,
                "device_id": device_id,
                "profile_id": profile_id,
                "resource": resource,
                "idempotency_key": idempotency_key,
            },
        )
        session.commit()
    except OperationConflict:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        existing = find_attempt(session, profile_id, device_id, resource, idempotency_key)
        if existing and existing.intent_hash == digest:
            return existing
        raise OperationConflict("Attempt conflicts with an existing device operation") from None
    return operation


def claim_dispatch(session: Session, operation_id: str, *, actor: str) -> bool:
    """Only the single successful claimant may send; never reclaim running work."""
    result = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.status == "accepted",
        )
        .values(status="running", updated_at=utcnow())
    )
    if result.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(
        session,
        actor=actor,
        event_type="guarded.operation.dispatch_claimed",
        message="Dispatch claimed; completion is not proven.",
        data={"operation_id": operation_id},
    )
    session.commit()
    return True


def mark_uncertain(
    session: Session, operation_id: str, *, actor: str, transport: dict | None = None
) -> bool:
    result = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.status == "running",
        )
        .values(status="uncertain", updated_at=utcnow())
    )
    if result.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(
        session,
        actor=actor,
        event_type="guarded.operation.uncertain",
        message="Dispatch outcome unknown; device remains locked.",
        data={"operation_id": operation_id, **({"transport": transport} if transport else {})},
    )
    session.commit()
    return True


def mark_upload_not_started(
    session: Session, operation_id: str, *, actor: str, transport: dict
) -> bool:
    """Only the live adapter's pre-upload exception may close a claimed dispatch."""
    if transport.get("upload_started") is not False:
        raise OperationConflict("No proof that upload was prevented")
    result = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.status == "running",
        )
        .values(status="failed", active_device=None, updated_at=utcnow())
    )
    if result.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(
        session,
        actor=actor,
        event_type="firmware.operation.upload_not_started",
        message="The firmware upload did not start. Prepare a fresh review.",
        data={"operation_id": operation_id, "transport": transport, "dispatch_prevented": True},
    )
    session.commit()
    return True


def recorded_result(operation: GuardedOperation, *, session: Session | None = None) -> dict:
    result = {
        "profile_id": operation.profile_id,
        "device_id": operation.device_id,
        "resource": operation.resource,
        "operation_id": operation.id,
        "idempotency_key": operation.idempotency_key,
        "status": operation.status,
        "record_found": True,
        "safe_to_retry": False,
        "evidence_at": None,
        "recorded_at": operation.updated_at.isoformat(),
        "stages": [],
        "execution_available": False,
        "message": "Recorded operation only; no verified hardware completion.",
        "next_action": "Keep the device blocked until supported target-bound verification.",
    }
    if operation.status == "verified" and session is not None:
        event = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "firmware.operation.verified",
                AuditEvent.data_json["operation_id"].as_string() == operation.id,
                AuditEvent.data_json["profile_id"].as_string() == operation.profile_id,
                AuditEvent.data_json["device_id"].as_string() == operation.device_id,
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        if event:
            result.update(
                evidence_at=event.data_json["evidence_at"],
                message=event.message,
                next_action="Review the remaining firmware prerequisites before another change.",
                stages=[
                    {
                        "name": "Verification",
                        "status": "verified",
                        "evidence_at": event.data_json["evidence_at"],
                    }
                ],
            )
    if operation.status == "failed" and session is not None:
        fence = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type.in_(
                    ["firmware.operation.unsent_fenced", "firmware.operation.upload_not_started"]
                ),
                AuditEvent.data_json["operation_id"].as_string() == operation.id,
            )
            .limit(1)
        )
        if fence:
            result.update(
                message=fence.message,
                dispatch_prevented=True,
                next_action="Create a fresh firmware review; this attempt cannot be sent.",
            )
    if session is not None:
        closure = (
            _closed_unverified(session, operation.id) if operation.status == "failed" else None
        )
        if closure:
            result.update(
                message=closure.message,
                dispatch_prevented=False,
                resolution="operator_closed_unverified",
                next_action="Prepare a fresh update review; the prior outcome remains unverified.",
            )
        diagnostic = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type.in_(
                    ["guarded.operation.uncertain", "firmware.operation.upload_not_started"]
                ),
                AuditEvent.data_json["operation_id"].as_string() == operation.id,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        if diagnostic and diagnostic.data_json.get("transport"):
            result["transport"] = diagnostic.data_json["transport"]
    return result


def _closed_unverified(session, operation_id):
    return session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "firmware.operation.closed_unverified",
            AuditEvent.data_json["operation_id"].as_string() == operation_id,
        )
        .limit(1)
    )
