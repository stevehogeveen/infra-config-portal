from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import select

from app.models import AuditEvent, GuardedOperation
from app.services.firmware_worker import (
    FirmwareReview,
    FirmwareReviewError,
    PreparedFirmware,
    canonical_intent,
    run_reviewed_firmware,
)
from app.services.guarded_operation_ledger import OperationConflict
from app.services.firmware_transport import FirmwareDispatchError


@pytest.fixture
def review():
    return FirmwareReview(
        profile_id="fixture-kit",
        device_id="fixture-device",
        review_token="r" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        confirmation_phrase="INSTALL ILO ON FIXTURE; ILO WILL RESET",
        intent_json=canonical_intent(
            {
                "profile_id": "fixture-kit",
                "device_id": "fixture-device",
                "operation": "ilo-firmware-update",
                "target_identity_sha256": "a" * 64,
                "component_sha256": "b" * 64,
                "binary_sha256": "c" * 64,
                "target_version": "3.19",
                "ilo_reset_expected": True,
                "installed_version": "2.78",
                "binary_size_bytes": 100,
                "host_reboot_authorized": False,
            }
        ),
    )


class FakeAdapter:
    def __init__(self):
        self.sends = 0
        self.blockers = ()
        self.changed = False
        self.lost_response = False

    def prepare(self, review):
        return PreparedFirmware(
            "{}" if self.changed else review.intent_json, self.blockers, object()
        )

    def send(self, prepared):
        self.sends += 1
        if self.lost_response:
            raise TimeoutError("fixture secret must not be persisted")


def run(session, review, adapter, **overrides):
    args = dict(
        review=review,
        review_token=review.review_token,
        confirmation_phrase=review.confirmation_phrase,
        idempotency_key="attempt",
        actor="fixture",
        adapter=adapter,
    )
    args.update(overrides)
    return run_reviewed_firmware(session, **args)


def test_success_is_pending_not_verified_and_duplicate_never_resends(db_session, review):
    adapter = FakeAdapter()
    first = run(db_session, review, adapter)
    second = run(db_session, review, adapter)
    assert first["status"] == second["status"] == "running"
    assert first["operation_id"] == second["operation_id"]
    assert first["evidence_at"] is None
    assert first["safe_to_retry"] is False
    assert adapter.sends == 1


def test_lost_response_stays_locked_without_retry_or_secret_leak(db_session, review):
    adapter = FakeAdapter()
    adapter.lost_response = True
    assert run(db_session, review, adapter)["status"] == "uncertain"
    assert run(db_session, review, adapter)["status"] == "uncertain"
    with pytest.raises(OperationConflict):
        run(db_session, review, adapter, idempotency_key="another-attempt")
    assert adapter.sends == 1
    events = list(db_session.scalars(select(AuditEvent)))
    assert "fixture secret" not in str([(e.message, e.data_json) for e in events])


@pytest.mark.parametrize("case", ["expired", "token", "phrase", "changed", "blocked", "key"])
def test_preflight_rejection_never_reserves_or_sends(db_session, review, case):
    adapter = FakeAdapter()
    args = {}
    if case == "expired":
        review = replace(review, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    elif case == "token":
        args["review_token"] = "wrong"
    elif case == "phrase":
        args["confirmation_phrase"] = review.confirmation_phrase.lower()
    elif case == "changed":
        adapter.changed = True
    elif case == "blocked":
        adapter.blockers = ("Upgrade prerequisites not established.",)
    else:
        args["idempotency_key"] = "invalid key"
    with pytest.raises(FirmwareReviewError):
        run(db_session, review, adapter, **args)
    assert adapter.sends == 0
    assert not list(db_session.scalars(select(GuardedOperation)))


def test_commit_failure_cannot_send(db_session, review, monkeypatch):
    adapter = FakeAdapter()
    original_commit = db_session.commit
    calls = 0

    def commit():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture commit failure")
        original_commit()

    monkeypatch.setattr(db_session, "commit", commit)
    with pytest.raises(RuntimeError, match="commit failure"):
        run(db_session, review, adapter)
    db_session.rollback()
    assert adapter.sends == 0
    assert db_session.scalar(select(GuardedOperation)).status == "accepted"


def test_missing_first_bridge_never_reserved(db_session, review):
    intent = json.loads(review.intent_json)
    intent.update(installed_version="1.37", binary_size_bytes=33557086)
    review = replace(review, intent_json=canonical_intent(intent))
    adapter = FakeAdapter()
    with pytest.raises(FirmwareReviewError, match="1.48"):
        run(db_session, review, adapter)
    assert adapter.sends == 0
    assert not list(db_session.scalars(select(GuardedOperation)))


def test_reviewed_148_to_319_passes_version_gate_with_fake_adapter(db_session, review):
    intent = json.loads(review.intent_json)
    intent.update(installed_version="1.48", binary_size_bytes=33557086)
    review = replace(review, intent_json=canonical_intent(intent))
    adapter = FakeAdapter()
    result = run(db_session, review, adapter)
    assert adapter.sends == 1
    assert result["status"] == "running"
    assert result["safe_to_retry"] is False


@pytest.mark.parametrize("started", [False, True])
def test_typed_transport_failure_only_unlocks_when_upload_never_started(
    db_session, review, started
):
    class FailedTransport(FakeAdapter):
        def send(self, prepared):
            self.sends += 1
            raise FirmwareDispatchError(
                stage="upload" if started else "session_creation",
                upload_started=started,
                facts={
                    "http_status": 401,
                    "content_type": "application/json",
                    "json_error_present": True,
                },
            )

    adapter = FailedTransport()
    result = run(db_session, review, adapter)
    assert result["status"] == ("uncertain" if started else "failed")
    assert result["transport"]["http_status"] == 401
    assert result["safe_to_retry"] is False
    assert result.get("dispatch_prevented", False) is (not started)
    assert (db_session.get(GuardedOperation, result["operation_id"]).active_device is None) is (
        not started
    )
    duplicate = run(db_session, review, adapter)
    assert duplicate["operation_id"] == result["operation_id"]
    assert adapter.sends == 1
