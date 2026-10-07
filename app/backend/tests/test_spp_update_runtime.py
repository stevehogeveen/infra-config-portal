"""Mock target/adapter only. No SUM or hardware network activity."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import pytest

from app.main import app
from app.models import FirmwareApproval, GuardedOperation
from app.services import spp_update_runtime as runtime
from app.services.guarded_operation_ledger import OperationConflict
from app.services.spp_update_contract import ApplyRequest
from test_spp_update_execution import Adapter, assessment


class Backend:
    def __init__(self):
        self.reads = 0
        self.transport = Adapter()
        self.evidence = assessment()

    def available(self, profile, device):
        return (profile, device) == ("fixture-kit", "fixture-server")

    def assess(self, profile, device):
        self.reads += 1
        return self.evidence

    def adapter(self, operation):
        return self.transport


def review(session, backend):
    plan = runtime.plan(session, backend, "fixture-kit", "fixture-server", "fixture")
    return ApplyRequest(
        review_token=plan.review_token,
        confirmation_phrase=plan.confirmation_phrase,
        idempotency_key="spp-attempt",
    )


def test_durable_queue_drains_after_worker_restart(db_session):
    backend = Backend()
    request = review(db_session, backend)
    first = runtime.submit(db_session, backend, "fixture-kit", "fixture-server", "fixture", request)
    assert first.status == "running" and not backend.transport.sent
    factory = sessionmaker(bind=db_session.get_bind())
    runtime.work_once(factory, backend)
    assert len(backend.transport.sent) == 1
    # A new scanner instance continues the committed next step, not the last send.
    runtime.work_once(factory, backend)
    runtime.work_once(factory, backend)
    assert len(backend.transport.sent) == 2
    assert runtime.recorded_status(db_session, "fixture-kit", "fixture-server").status == "verified"
    reads = backend.reads
    backend.evidence = backend.evidence.model_copy(
        update={"checked_at": datetime.now(UTC) - timedelta(days=2)}
    )
    assert (
        runtime.submit(
            db_session, backend, "fixture-kit", "fixture-server", "fixture", request
        ).status
        == "verified"
    )
    assert backend.reads == reads


def test_missing_lost_request_is_fenced_even_after_review_expiry(db_session):
    backend = Backend()
    request = review(db_session, backend)
    row = db_session.scalar(select(FirmwareApproval))
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    result = runtime.reconcile(db_session, "fixture-kit", "fixture-server", "fixture", request)
    assert result.dispatch_prevented and not result.active
    assert (
        runtime.submit(
            db_session, backend, "fixture-kit", "fixture-server", "fixture", request
        ).status
        == "failed"
    )
    runtime.work_once(sessionmaker(bind=db_session.get_bind()), backend)
    assert not backend.transport.sent


def test_wrong_actor_key_and_target_never_fence_or_dispatch(db_session):
    backend = Backend()
    request = review(db_session, backend)
    for actor, device in [("other", "fixture-server"), ("fixture", "other")]:
        with pytest.raises(OperationConflict):
            runtime.reconcile(db_session, "fixture-kit", device, actor, request)
    runtime.submit(db_session, backend, "fixture-kit", "fixture-server", "fixture", request)
    other = review(db_session, backend)
    with pytest.raises(OperationConflict):
        runtime.submit(db_session, backend, "fixture-kit", "fixture-server", "fixture", other)
    assert not backend.transport.sent


def test_sent_claim_is_not_repeated_after_process_death(db_session):
    from app.services.spp_update_execution import claim_step

    backend = Backend()
    request = review(db_session, backend)
    current = runtime.submit(
        db_session, backend, "fixture-kit", "fixture-server", "fixture", request
    )
    claim_step(db_session, current.operation_id, actor="dead-worker")
    runtime.work_once(sessionmaker(bind=db_session.get_bind()), backend)
    assert not backend.transport.sent
    assert runtime.recorded_status(db_session, "fixture-kit", "fixture-server").active


def test_api_withholds_availability_and_records_exact_attempt(client, db_session, monkeypatch):
    from app.api import spp_update

    monkeypatch.setattr(spp_update, "server_in_kit", lambda *args: None)
    monkeypatch.setattr(app.state, "spp_backend", None, raising=False)
    base = "/api/v1/rack-plans/fixture-kit/firmware-update"
    params = {"device_id": "fixture-server"}
    headers = {"X-Local-User": "fixture"}
    assert client.get(base + "/status", params=params).status_code == 501
    backend = Backend()
    monkeypatch.setattr(app.state, "spp_backend", backend)
    assert client.get(base + "/status", params=params).json()["status"] == "not_started"
    assert backend.reads == 0
    assert (
        client.post(base + "/plan", params=params, json={"device_id": "other"}).status_code == 409
    )
    plan = client.post(base + "/plan", params=params, json=params, headers=headers).json()
    payload = dict(
        review_token=plan["review_token"],
        confirmation_phrase=plan["confirmation_phrase"],
        idempotency_key="api-attempt",
    )
    assert (
        client.post(
            base + "/apply", params=params, json={**payload, "host": "192.0.2.99"}, headers=headers
        ).status_code
        == 422
    )
    result = client.post(base + "/apply", params=params, json=payload, headers=headers)
    assert result.status_code == 200 and result.json()["idempotency_key"] == "api-attempt"
    assert not backend.transport.sent
    reads = backend.reads
    assert (
        client.post(base + "/apply", params=params, json=payload, headers=headers).status_code
        == 200
    )
    assert backend.reads == reads
    monkeypatch.setattr(app.state, "spp_backend", None)
    assert (
        client.get(base + "/status", params=params).json()["operation_id"]
        == result.json()["operation_id"]
    )
    missing = client.get(base + "/status", params={**params, "idempotency_key": "another"})
    assert missing.status_code == 501


def test_worker_closes_interrupted_admission_without_send(db_session):
    backend = Backend()
    request = review(db_session, backend)
    current = runtime.submit(
        db_session, backend, "fixture-kit", "fixture-server", "fixture", request
    )
    row = db_session.get(GuardedOperation, current.operation_id)
    row.status = "accepted"
    row.updated_at = datetime.now(UTC) - timedelta(minutes=3)
    db_session.commit()
    runtime.work_once(sessionmaker(bind=db_session.get_bind()), backend)
    result = runtime.recorded_status(db_session, "fixture-kit", "fixture-server")
    assert result.dispatch_prevented and not result.active
    assert not backend.transport.sent


@pytest.mark.parametrize(
    "invalid", [None, "identity", "version", "early", "future", "running", "authority"]
)
def test_post_crash_completion_requires_exact_fresh_evidence(db_session, invalid):
    from app.services.spp_update_execution import (
        ReconciledReadback,
        claim_step,
        reconcile_step,
    )

    backend = Backend()
    request = review(db_session, backend)
    current = runtime.submit(
        db_session, backend, "fixture-kit", "fixture-server", "fixture", request
    )
    step = claim_step(db_session, current.operation_id, actor="interrupted-worker")
    evidence = dict(
        target_identity_sha256="a" * 64,
        version=step.to,
        checked_at=datetime.now(UTC),
        dispatch_ended=True,
        authority_released=True,
    )
    changes = {
        "identity": {"target_identity_sha256": "f" * 64},
        "version": {"version": "wrong"},
        "early": {"checked_at": step.started_at - timedelta(seconds=1)},
        "future": {"checked_at": datetime.now(UTC) + timedelta(days=1)},
        "running": {"dispatch_ended": False},
        "authority": {"authority_released": False},
    }
    evidence.update(changes.get(invalid, {}))
    proof = ReconciledReadback(**evidence)
    if invalid:
        with pytest.raises(OperationConflict):
            reconcile_step(db_session, current.operation_id, actor="reader", proof=proof)
        assert (
            runtime.recorded_status(db_session, "fixture-kit", "fixture-server").steps[0].state
            == "installing"
        )
    else:
        result = reconcile_step(db_session, current.operation_id, actor="reader", proof=proof)
        assert result.steps[0].state == "done" and result.steps[1].state == "waiting"
        assert result.active
        # Repeating the same proof cannot dispatch or finish a later component.
        assert (
            reconcile_step(db_session, current.operation_id, actor="reader", proof=proof) == result
        )
        runtime.work_once(sessionmaker(bind=db_session.get_bind()), backend)
        assert len(backend.transport.sent) == 1
        assert (
            runtime.recorded_status(db_session, "fixture-kit", "fixture-server").status
            == "verified"
        )
