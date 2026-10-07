"""Prevent late dispatch rather than interpreting a missing row as proof of no send."""

import hashlib
import json

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models import FirmwareApproval, GuardedOperation, utcnow
from app.services.audit import record_audit_event
from app.services.firmware_reviews import load_review
from app.services.guarded_operation_ledger import OperationConflict, find_attempt, recorded_result


def fence_unsent_attempt(session, *, profile_id, device_id, actor, review_token, idempotency_key):
    review = load_review(
        session, profile_id=profile_id, device_id=device_id, actor=actor, token=review_token
    )
    row = session.get(FirmwareApproval, review.review_id)
    intent = {"review_token_sha256": row.token_hash, "intent": row.intent_json}
    digest = hashlib.sha256(
        json.dumps(intent, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    existing = find_attempt(session, profile_id, device_id, "firmware-execution", idempotency_key)
    if existing is None:
        operation = GuardedOperation(
            profile_id=profile_id,
            device_id=device_id,
            resource="firmware-execution",
            idempotency_key=idempotency_key,
            intent_hash=digest,
            active_device=None,
            status="failed",
        )
        try:
            session.add(operation)
            session.flush()
            consumed = session.execute(
                update(FirmwareApproval)
                .where(
                    FirmwareApproval.id == row.id,
                    FirmwareApproval.operation_id.is_(None),
                )
                .values(operation_id=operation.id)
            )
            if consumed.rowcount != 1:
                raise OperationConflict(
                    "This review already belongs to another attempt; reconcile its recorded key"
                )
            _audit_fence(session, actor, operation)
            session.commit()
            return recorded_result(operation, session=session)
        except IntegrityError:
            session.rollback()
            existing = find_attempt(
                session, profile_id, device_id, "firmware-execution", idempotency_key
            )
            if existing is None:
                raise OperationConflict(
                    "Attempt changed during reconciliation; refresh the recorded result"
                ) from None
        except OperationConflict:
            session.rollback()
            raise
    if existing.intent_hash != digest:
        raise OperationConflict("Attempt key is bound to a different review")
    # A concurrent dispatch claim wins or loses this comparison in the database.
    cancelled = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == existing.id,
            GuardedOperation.status == "accepted",
        )
        .values(status="failed", active_device=None, updated_at=utcnow())
    )
    if cancelled.rowcount == 1:
        _audit_fence(session, actor, existing)
        session.commit()
    else:
        session.rollback()
    session.refresh(existing)
    return recorded_result(existing, session=session)


def _audit_fence(session, actor, operation):
    record_audit_event(
        session,
        actor=actor,
        event_type="firmware.operation.unsent_fenced",
        message="Attempt closed before dispatch. Delayed sends for this review are prevented; create a fresh review for another attempt.",
        data={
            "operation_id": operation.id,
            "profile_id": operation.profile_id,
            "device_id": operation.device_id,
            "idempotency_key": operation.idempotency_key,
        },
    )
