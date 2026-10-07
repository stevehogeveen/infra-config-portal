from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditEvent, FirmwareApproval, GuardedOperation
from app.services.firmware_reviews import issue_review, load_review
from app.services.firmware_worker import (
    FirmwareReviewError,
    PreparedFirmware,
    run_reviewed_firmware,
)
from app.services.guarded_operation_ledger import OperationConflict


@pytest.fixture
def issued(db_session):
    return issue_review(
        db_session,
        profile_id="kit",
        device_id="device",
        actor="fixture",
        confirmation_phrase="INSTALL ILO 1.48 ON DEVICE; ILO WILL RESET",
        intent={
            "profile_id": "kit",
            "device_id": "device",
            "operation": "ilo-firmware-update",
            "target_identity_sha256": "a" * 64,
            "component_sha256": "b" * 64,
            "binary_sha256": "c" * 64,
            "target_version": "1.48",
            "installed_version": "1.37",
            "binary_size_bytes": 100,
            "ilo_reset_expected": True,
            "host_reboot_authorized": False,
        },
    )


class Adapter:
    sends = 0

    def prepare(self, review):
        return PreparedFirmware(review.intent_json, (), None)

    def send(self, prepared):
        self.sends += 1


def execute(session, review, adapter, key="attempt"):
    return run_reviewed_firmware(
        session,
        review=review,
        review_token=review.review_token,
        confirmation_phrase=review.confirmation_phrase,
        idempotency_key=key,
        actor="fixture",
        adapter=adapter,
    )


def test_persist_and_load_scoped_review_without_plaintext_token(db_session, issued):
    loaded = load_review(
        db_session, profile_id="kit", device_id="device", actor="fixture", token=issued.review_token
    )
    assert loaded == issued
    row = db_session.get(FirmwareApproval, issued.review_id)
    assert row.token_hash != issued.review_token
    events = list(db_session.scalars(select(AuditEvent)))
    assert issued.review_token not in str([e.data_json for e in events])
    for changes in (
        {"profile_id": "wrong"},
        {"device_id": "wrong"},
        {"actor": "wrong"},
        {"token": "wrong"},
    ):
        args = dict(
            profile_id="kit", device_id="device", actor="fixture", token=issued.review_token
        )
        args.update(changes)
        with pytest.raises(FirmwareReviewError):
            load_review(db_session, **args)


def test_atomic_consumption_and_replay_after_lock_release(db_session, issued):
    adapter = Adapter()
    result = execute(db_session, issued, adapter)
    row = db_session.get(FirmwareApproval, issued.review_id)
    assert row.operation_id == result["operation_id"]
    assert execute(db_session, issued, adapter)["operation_id"] == row.operation_id
    operation = db_session.get(GuardedOperation, row.operation_id)
    operation.status = "verified"
    operation.active_device = None
    db_session.commit()
    with pytest.raises(OperationConflict, match="consumed"):
        execute(db_session, issued, adapter, key="new-attempt")
    assert adapter.sends == 1
    assert len(list(db_session.scalars(select(GuardedOperation)))) == 1


def test_database_expiry_is_checked_after_preflight(db_session, issued):
    adapter = Adapter()
    row = db_session.get(FirmwareApproval, issued.review_id)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(OperationConflict, match="expired"):
        execute(db_session, issued, adapter)
    assert adapter.sends == 0
    assert db_session.get(FirmwareApproval, issued.review_id).operation_id is None
    assert not list(db_session.scalars(select(GuardedOperation)))
