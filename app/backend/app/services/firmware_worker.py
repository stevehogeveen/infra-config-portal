"""Reviewed dispatch runner used by the guarded iLO firmware flow.

Review objects must be built on the server from persisted evidence, never directly
from an API payload. The adapter owns exact-target preflight and byte revalidation.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.services.guarded_operation_ledger import (
    claim_dispatch,
    mark_uncertain,
    mark_upload_not_started,
    recorded_result,
    reserve,
)
from app.services.ilo_upgrade_path import ilo_upgrade_blockers
from app.services.firmware_transport import FirmwareDispatchError


class FirmwareReviewError(ValueError):
    pass


@dataclass(frozen=True)
class FirmwareReview:
    profile_id: str
    device_id: str
    review_token: str
    expires_at: datetime
    confirmation_phrase: str
    # Canonical JSON avoids mutation of reviewed facts after approval.
    intent_json: str
    review_id: str | None = None


@dataclass(frozen=True)
class PreparedFirmware:
    intent_json: str
    blockers: tuple[str, ...]
    # Adapter-private staged bytes/transport context; never persisted or returned.
    handle: object


class FirmwareAdapter(Protocol):
    def prepare(self, review: FirmwareReview) -> PreparedFirmware:
        """Read-only preflight; verify current identity, payload, support and prerequisites."""

    def send(self, prepared: PreparedFirmware) -> None:
        """Exactly one upload; no retries, host power action or secret-bearing result."""


def canonical_intent(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_intent(value: dict, review: FirmwareReview):
    if value.get("profile_id") != review.profile_id or value.get("device_id") != review.device_id:
        raise FirmwareReviewError("Review does not match the selected kit and device.")
    for key in ("target_identity_sha256", "component_sha256", "binary_sha256"):
        digest = value.get(key)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise FirmwareReviewError("Review is missing immutable target or package identity.")
    if (
        value.get("operation") != "ilo-firmware-update"
        or value.get("ilo_reset_expected") is not True
        or value.get("host_reboot_authorized") is not False
        or not isinstance(value.get("target_version"), str)
        or not value["target_version"]
    ):
        raise FirmwareReviewError("Review does not contain the complete iLO update/reset scope.")


def run_reviewed_firmware(
    session: Session,
    *,
    review: FirmwareReview,
    review_token: str,
    confirmation_phrase: str,
    idempotency_key: str,
    actor: str,
    adapter: FirmwareAdapter,
    now: datetime | None = None,
) -> dict:
    """A caller must own a dedicated session and load a server-issued review.

    This function cannot issue a review or establish vendor support. The HTTP flow
    loads a persisted review and supplies the exact-target production adapter.
    """
    current = now or datetime.now(UTC)
    if review.expires_at.tzinfo is None or current.tzinfo is None or current >= review.expires_at:
        raise FirmwareReviewError("Firmware review expired.")
    if (
        not review.review_token
        or not review.confirmation_phrase
        or not hmac.compare_digest(review.review_token.encode(), review_token.encode())
        or not hmac.compare_digest(
            review.confirmation_phrase.encode(), confirmation_phrase.encode()
        )
    ):
        raise FirmwareReviewError("Exact review token and typed confirmation are required.")
    if not 1 <= len(idempotency_key) <= 128 or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
        for c in idempotency_key
    ):
        raise FirmwareReviewError("Invalid attempt key.")
    try:
        intent = json.loads(review.intent_json)
    except (TypeError, ValueError):
        raise FirmwareReviewError("Review intent is invalid.") from None
    if not isinstance(intent, dict):
        raise FirmwareReviewError("Review intent must be an object.")
    _validate_intent(intent, review)
    blockers = ilo_upgrade_blockers(
        intent.get("installed_version", ""),
        intent.get("target_version", ""),
        intent.get("binary_size_bytes"),
    )
    if blockers:
        raise FirmwareReviewError(" ".join(blockers))
    prepared = adapter.prepare(review)
    if prepared.blockers:
        raise FirmwareReviewError(" ".join(prepared.blockers))
    if canonical_intent(json.loads(prepared.intent_json)) != canonical_intent(intent):
        raise FirmwareReviewError("Target, package or reviewed prerequisites changed.")
    # Preparation may be slow; expiry must still hold immediately before reservation.
    if now is None and datetime.now(UTC) >= review.expires_at:
        raise FirmwareReviewError("Firmware review expired during preparation.")
    operation = reserve(
        session,
        profile_id=review.profile_id,
        device_id=review.device_id,
        resource="firmware-execution",
        idempotency_key=idempotency_key,
        reviewed_intent={
            "review_token_sha256": hashlib.sha256(review.review_token.encode()).hexdigest(),
            "intent": intent,
        },
        actor=actor,
        firmware_review_id=review.review_id,
    )
    if not claim_dispatch(session, operation.id, actor=actor):
        session.refresh(operation)
        return recorded_result(operation, session=session)
    try:
        adapter.send(prepared)
    except FirmwareDispatchError as exc:
        if exc.upload_started:
            mark_uncertain(session, operation.id, actor=actor, transport=exc.facts)
        else:
            mark_upload_not_started(session, operation.id, actor=actor, transport=exc.facts)
    except Exception:
        # Even an HTTP error can follow a partial send. Never log raw transport errors.
        mark_uncertain(session, operation.id, actor=actor)
    session.refresh(operation)
    # Acceptance is not completion; no lock is released by this runner.
    return recorded_result(operation, session=session)
