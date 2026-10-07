"""Offline durable admission/dispatch tests. No vendor process or network."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import FirmwareApproval, GuardedOperation
from app.services.guarded_operation_ledger import OperationConflict, reserve
from app.services.spp_update_contract import ApplyRequest
from app.services.spp_update_execution import (
    Readback,
    approve,
    claim_step,
    execute_next,
    issue_review,
    record_step,
    status,
)
from app.services.spp_update_plan import Assessment, assessment_digest


def assessment():
    return Assessment(
        profile_id="fixture-kit",
        device_id="fixture-server",
        source="sum-assessment",
        checked_at=datetime.now(UTC),
        target_identity_sha256="a" * 64,
        package_identity_sha256="b" * 64,
        report_sha256="c" * 64,
        server={"name": "Fixture", "model": "Fixture model", "manager_generation": 5},
        package={"file": "fixture.iso", "release": "fixture"},
        execution_mode="online",
        platform_supported=True,
        runner_supported=True,
        power_on_required=False,
        updates=[
            dict(
                component_id="ilo",
                component="iLO",
                from_version=start,
                to=end,
                package_sha256=digest * 64,
                applicable=True,
                signature_verified=True,
                dependencies_satisfied=True,
                adapter_supported=True,
                restarts="ilo",
            )
            for start, end, digest in [("1.37", "1.48", "d"), ("1.48", "3.19", "e")]
        ],
    )


def admission(session):
    evidence = assessment()
    plan = issue_review(session, evidence, actor="fixture")
    request = ApplyRequest(
        review_token=plan.review_token,
        confirmation_phrase=plan.confirmation_phrase,
        idempotency_key="attempt",
    )
    args = dict(
        profile_id=evidence.profile_id,
        device_id=evidence.device_id,
        actor="fixture",
        request=request,
        fresh_assessment=evidence,
    )
    return approve(session, **args), args


def finish(session, operation, step, outcome="done", **changes):
    return record_step(
        session,
        operation,
        step_id=step.step_id,
        actor="fixture",
        outcome=outcome,
        target_identity_sha256=changes.get("identity", "a" * 64),
        verified_version=changes.get("version", step.to if outcome == "done" else None),
    )


def test_approval_idempotent_and_each_step_dispatches_once(db_session):
    initial, args = admission(db_session)
    op = initial.operation_id
    assert approve(db_session, **args).operation_id == op
    for _ in range(2):
        step = claim_step(db_session, op, actor="fixture")
        assert step is not None
        assert claim_step(db_session, op, actor="duplicate") is None
        assert finish(db_session, op, step)
        assert not finish(db_session, op, step)
    result = status(db_session, op)
    assert result.status == "verified"
    assert not result.active
    assert [s.verified_version for s in result.steps] == ["1.48", "3.19"]
    assert db_session.get(GuardedOperation, op).active_device is None


@pytest.mark.parametrize("outcome", ["failed", "uncertain"])
def test_stop_on_first_unresolved_step(db_session, outcome):
    initial, _ = admission(db_session)
    step = claim_step(db_session, initial.operation_id, actor="fixture")
    assert finish(db_session, initial.operation_id, step, outcome)
    result = status(db_session, initial.operation_id)
    assert result.steps[1].state == "not_started"
    assert result.active == (outcome == "uncertain")
    assert claim_step(db_session, initial.operation_id, actor="restart") is None


def test_wrong_target_or_version_cannot_complete(db_session):
    initial, _ = admission(db_session)
    step = claim_step(db_session, initial.operation_id, actor="fixture")
    with pytest.raises(OperationConflict):
        finish(db_session, initial.operation_id, step, identity="f" * 64)
    with pytest.raises(ValueError):
        finish(db_session, initial.operation_id, step, version="wrong")
    assert status(db_session, initial.operation_id).active


@pytest.mark.parametrize("change", ["actor", "device", "phrase", "drift", "expired"])
def test_approval_binding(db_session, change):
    initial, args = admission(db_session)
    # A second review cannot admit a changed identity or caller.
    if change == "actor":
        args["actor"] = "other"
    elif change == "device":
        args["device_id"] = "other"
    elif change == "phrase":
        args["request"] = args["request"].model_copy(update={"confirmation_phrase": "wrong"})
    elif change == "drift":
        args["fresh_assessment"] = args["fresh_assessment"].model_copy(
            update={"package_identity_sha256": "f" * 64}
        )
    else:
        row = db_session.scalar(select(FirmwareApproval))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db_session.commit()
        args["request"] = args["request"].model_copy(update={"idempotency_key": "other"})
    with pytest.raises(OperationConflict):
        approve(db_session, **args)
    assert status(db_session, initial.operation_id).active


def test_shared_device_lock_blocks_other_resource(db_session):
    admission(db_session)
    with pytest.raises(OperationConflict):
        reserve(
            db_session,
            profile_id="fixture-kit",
            device_id="fixture-server",
            resource="drive-return-to-service",
            idempotency_key="storage",
            reviewed_intent={"operation": "fixture"},
            actor="fixture",
        )


def test_stale_preflight_cannot_claim_the_following_step(db_session):
    initial, _ = admission(db_session)
    first = claim_step(db_session, initial.operation_id, actor="fixture")
    finish(db_session, initial.operation_id, first)
    assert (
        claim_step(
            db_session, initial.operation_id, actor="slow-worker", expected_step_id=first.step_id
        )
        is None
    )
    assert status(db_session, initial.operation_id).steps[1].state == "waiting"


def test_crash_and_concurrent_claims(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "spp.db"), connect_args={"timeout": 20})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        initial, _ = admission(session)
        op = initial.operation_id

    def claim(_):
        with Session(engine) as session:
            return claim_step(session, op, actor="worker")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(claim, range(4)))
    assert sum(s is not None for s in results) == 1
    with Session(engine) as session:
        assert claim_step(session, op, actor="restarted-worker") is None
        assert status(session, op).active
        assert status(session, op).steps[0].state == "installing"
    engine.dispose()


class Adapter:
    def __init__(self, failure=None):
        self.failure = failure
        self.sent = []
        self.authorized = False
        self.revoked = 0

    @contextmanager
    def authority(self, assessment, step):
        self.authorized = True
        try:
            yield
        finally:
            self.authorized = False
            self.revoked += 1
            if self.failure in {"cleanup", "drift_cleanup"}:
                raise RuntimeError("secret-bearing fixture error")

    def preflight(self, assessment, step):
        return (
            "wrong" if self.failure in {"drift", "drift_cleanup"} else assessment_digest(assessment)
        )

    def send(self, assessment, step):
        assert self.authorized
        self.sent.append(step.step_id)
        if self.failure == "send":
            raise TimeoutError("secret-bearing fixture error")

    def verify(self, assessment, step):
        return Readback(
            assessment.target_identity_sha256, "wrong" if self.failure == "readback" else step.to
        )


def test_worker_revokes_authority_and_advances_only_after_readback(db_session):
    initial, _ = admission(db_session)
    adapter = Adapter()
    assert (
        execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter).status
        == "running"
    )
    assert not adapter.authorized and adapter.revoked == 1
    assert (
        execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter).status
        == "verified"
    )
    execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter)
    assert len(adapter.sent) == 2 and adapter.revoked == 2


@pytest.mark.parametrize("failure", ["send", "readback", "cleanup"])
def test_worker_unknown_outcome_never_retries(db_session, failure):
    initial, _ = admission(db_session)
    adapter = Adapter(failure)
    result = execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter)
    assert result.status == "uncertain" and result.active
    assert "secret" not in result.model_dump_json()
    execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter)
    assert len(adapter.sent) == 1


def test_worker_drift_fences_unsent_attempt(db_session):
    initial, _ = admission(db_session)
    adapter = Adapter("drift")
    result = execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter)
    assert result.status == "failed" and result.dispatch_prevented and not result.active
    assert not adapter.sent


def test_unsent_cleanup_failure_still_retains_lock(db_session):
    initial, _ = admission(db_session)
    adapter = Adapter("drift_cleanup")
    result = execute_next(db_session, initial.operation_id, actor="fixture", adapter=adapter)
    assert result.status == "uncertain" and result.active and not result.dispatch_prevented
    assert not adapter.sent
