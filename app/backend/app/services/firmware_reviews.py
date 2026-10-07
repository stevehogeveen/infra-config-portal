"""Server-issued, actor/target-bound reviews. Only reviewed non-secret intent belongs here."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import FirmwareApproval
from app.services.audit import record_audit_event
from app.services.firmware_worker import (
    FirmwareReview,
    FirmwareReviewError,
    canonical_intent,
    _validate_intent,
)


def issue_review(
    session, *, profile_id: str, device_id: str, actor: str, intent: dict, confirmation_phrase: str
) -> FirmwareReview:
    """Internal only: caller must have validated capability and all prerequisites."""
    if not confirmation_phrase or len(confirmation_phrase) > 256:
        raise FirmwareReviewError("A bounded typed confirmation is required.")
    token = secrets.token_hex(32)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    review = FirmwareReview(
        profile_id, device_id, token, expires, confirmation_phrase, canonical_intent(intent)
    )
    _validate_intent(intent, review)
    row = FirmwareApproval(
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        profile_id=profile_id,
        device_id=device_id,
        actor=actor,
        intent_json=intent,
        confirmation_phrase=confirmation_phrase,
        expires_at=expires,
    )
    session.add(row)
    session.flush()
    record_audit_event(
        session,
        actor=actor,
        event_type="firmware.review.issued",
        message="Single-use firmware review recorded; no dispatch.",
        data={"review_id": row.id, "profile_id": profile_id, "device_id": device_id},
    )
    session.commit()
    return FirmwareReview(
        profile_id, device_id, token, expires, confirmation_phrase, canonical_intent(intent), row.id
    )


def load_review(
    session, *, profile_id: str, device_id: str, actor: str, token: str
) -> FirmwareReview:
    row = session.scalar(
        select(FirmwareApproval).where(
            FirmwareApproval.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            FirmwareApproval.profile_id == profile_id,
            FirmwareApproval.device_id == device_id,
            FirmwareApproval.actor == actor,
        )
    )
    if row is None:
        raise FirmwareReviewError("No matching server-issued firmware review exists.")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return FirmwareReview(
        profile_id,
        device_id,
        token,
        expires,
        row.confirmation_phrase,
        canonical_intent(row.intent_json),
        row.id,
    )
