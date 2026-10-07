"""Opt-in disposable PostgreSQL check; never points at configured app database."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import AuditEvent, GuardedOperation
from app.services.guarded_operation_ledger import (
    OperationConflict,
    claim_dispatch,
    mark_uncertain,
    reserve,
)


@pytest.mark.skipif(
    os.getenv("OFFLINE_POSTGRES_LEDGER_TEST") != "1",
    reason="Requires the disposable network-isolated PostgreSQL fixture",
)
def test_postgres_unique_reservation_and_dispatch():
    engine = create_engine(
        "postgresql+psycopg://fixture:fixture-only@127.0.0.1:5432/guarded_fixture",
        pool_size=8,
    )
    Base.metadata.create_all(engine)

    def reservation(session, key="one-attempt"):
        return reserve(
            session,
            profile_id="fixture-kit",
            device_id="fixture-device",
            resource="firmware-execution",
            idempotency_key=key,
            reviewed_intent={"fixture": True},
            actor="offline-postgres",
        )

    def submit(_):
        with Session(engine) as session:
            return reservation(session).id

    with ThreadPoolExecutor(max_workers=8) as workers:
        ids = list(workers.map(submit, range(8)))
    assert len(set(ids)) == 1

    def claim(_):
        with Session(engine) as session:
            return claim_dispatch(session, ids[0], actor="offline-worker")

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(claim, range(8)))
    assert results.count(True) == 1
    with Session(engine) as session:
        assert mark_uncertain(session, ids[0], actor="offline-worker")
        with pytest.raises(OperationConflict):
            reservation(session, "retry")
        assert session.get(GuardedOperation, ids[0]).status == "uncertain"
        assert len(list(session.scalars(select(AuditEvent)))) == 3
    engine.dispose()


@pytest.mark.skipif(
    os.getenv("OFFLINE_POSTGRES_LEDGER_TEST") != "1",
    reason="Requires the disposable network-isolated PostgreSQL fixture",
)
def test_postgres_review_fence_races_dispatch_without_late_send():
    import hashlib
    import json
    from threading import Barrier
    from app.models import FirmwareApproval
    from app.services.firmware_reviews import issue_review
    from app.services.firmware_reconcile import fence_unsent_attempt

    engine = create_engine(
        "postgresql+psycopg://fixture:fixture-only@127.0.0.1:5432/guarded_fixture", pool_size=8
    )
    Base.metadata.create_all(engine)
    for index in range(16):
        device = f"race-device-{index}"
        intent = {
            "profile_id": "race-kit",
            "device_id": device,
            "operation": "ilo-firmware-update",
            "target_identity_sha256": "a" * 64,
            "component_sha256": "b" * 64,
            "binary_sha256": "c" * 64,
            "target_version": "1.48",
            "installed_version": "1.37",
            "binary_size_bytes": 100,
            "ilo_reset_expected": True,
            "host_reboot_authorized": False,
        }
        with Session(engine) as session:
            review = issue_review(
                session,
                profile_id="race-kit",
                device_id=device,
                actor="fixture",
                intent=intent,
                confirmation_phrase="INSTALL FIXTURE",
            )
        barrier = Barrier(2)

        def dispatch():
            with Session(engine) as session:
                barrier.wait()
                try:
                    operation = reserve(
                        session,
                        profile_id="race-kit",
                        device_id=device,
                        resource="firmware-execution",
                        idempotency_key="race-attempt",
                        reviewed_intent={
                            "review_token_sha256": hashlib.sha256(
                                review.review_token.encode()
                            ).hexdigest(),
                            "intent": json.loads(review.intent_json),
                        },
                        actor="fixture",
                        firmware_review_id=review.review_id,
                    )
                    return claim_dispatch(session, operation.id, actor="fixture")
                except OperationConflict:
                    return False

        def fence():
            with Session(engine) as session:
                barrier.wait()
                return fence_unsent_attempt(
                    session,
                    profile_id="race-kit",
                    device_id=device,
                    actor="fixture",
                    review_token=review.review_token,
                    idempotency_key="race-attempt",
                )

        with ThreadPoolExecutor(max_workers=2) as workers:
            dispatched = workers.submit(dispatch)
            fenced = workers.submit(fence)
            was_sent, closed = dispatched.result(), fenced.result()
        with Session(engine) as session:
            row = session.get(FirmwareApproval, review.review_id)
            operation = session.get(GuardedOperation, row.operation_id)
            assert operation.status == ("running" if was_sent else "failed")
            assert operation.active_device == (device if was_sent else None)
            assert bool(closed.get("dispatch_prevented")) is not was_sent
            assert not claim_dispatch(session, operation.id, actor="late-duplicate")
    engine.dispose()
