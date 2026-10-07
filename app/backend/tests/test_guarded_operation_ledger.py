"""Offline persistence and race tests; no provider imports or hardware dispatch."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import AuditEvent, GuardedOperation
from app.services.guarded_operation_ledger import (
    OperationConflict, claim_dispatch, find_attempt, mark_uncertain, reserve,
)


def reservation(session, **overrides):
    args = dict(profile_id="kit-fixture", device_id="device-fixture",
                resource="firmware-execution", idempotency_key="attempt-1",
                reviewed_intent={"target_serial": "fixture", "sha256": "a" * 64},
                actor="offline-test")
    args.update(overrides)
    return reserve(session, **args)


def test_duplicate_and_changed_intent(db_session):
    first = reservation(db_session)
    assert reservation(db_session).id == first.id
    with pytest.raises(OperationConflict):
        reservation(db_session, reviewed_intent={"sha256": "b" * 64})
    assert len(list(db_session.scalars(select(GuardedOperation)))) == 1
    assert len(list(db_session.scalars(select(AuditEvent)))) == 1


@pytest.mark.parametrize("changes", [
    {"idempotency_key": "attempt-2"},
    {"resource": "drive-return-to-service"},
    {"profile_id": "different-kit"},
])
def test_device_lock_excludes_other_keys_resources_and_kits(db_session, changes):
    reservation(db_session)
    with pytest.raises(OperationConflict):
        reservation(db_session, **changes)
    assert reservation(db_session, device_id="other-device").id


def test_uncertain_never_reclaims_or_releases_device(db_session):
    operation = reservation(db_session)
    assert claim_dispatch(db_session, operation.id, actor="worker")
    assert not claim_dispatch(db_session, operation.id, actor="worker")
    assert mark_uncertain(db_session, operation.id, actor="worker")
    assert not claim_dispatch(db_session, operation.id, actor="worker")
    assert not mark_uncertain(db_session, operation.id, actor="worker")
    with pytest.raises(OperationConflict):
        reservation(db_session, idempotency_key="retry")


def test_persists_across_sessions_and_crashed_worker(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "ledger.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        operation_id = reservation(session).id
        assert claim_dispatch(session, operation_id, actor="worker")
    with Session(engine) as session:
        row = find_attempt(session, "kit-fixture", "device-fixture",
                           "firmware-execution", "attempt-1")
        assert row.id == operation_id
        assert row.status == "running"
        assert not claim_dispatch(session, operation_id, actor="restarted-worker")
        assert find_attempt(session, "other-kit", "device-fixture",
                            "firmware-execution", "attempt-1") is None
    engine.dispose()


def test_concurrent_reservations_and_claims(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "race.db"),
                           connect_args={"timeout": 20})
    Base.metadata.create_all(engine)

    def submit(_):
        with Session(engine) as session:
            return reservation(session).id

    with ThreadPoolExecutor(max_workers=4) as workers:
        ids = list(workers.map(submit, range(4)))
    assert len(set(ids)) == 1

    def claim(_):
        with Session(engine) as session:
            return claim_dispatch(session, ids[0], actor="worker")

    with ThreadPoolExecutor(max_workers=4) as workers:
        claims = list(workers.map(claim, range(4)))
    assert claims.count(True) == 1
    with Session(engine) as session:
        assert len(list(session.scalars(select(AuditEvent)))) == 2
    engine.dispose()


def test_additive_migration_preserves_existing_history(tmp_path):
    path = Path(__file__).parents[1] / "alembic/versions/0006_guarded_operations.py"
    spec = importlib.util.spec_from_file_location("guarded_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    # Existing audit history must survive; build the ledger through the migration.
    AuditEvent.__table__.create(engine)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        unique = inspect(connection).get_unique_constraints("guarded_operations")
        assert any(c["column_names"] == ["active_device"] for c in unique)
        assert any(c["name"] == "uq_guarded_attempt" for c in unique)
    with Session(engine) as session:
        operation_id = reservation(session).id
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        with pytest.raises(RuntimeError, match="history"):
            migration.downgrade()
    with Session(engine) as session:
        assert session.get(GuardedOperation, operation_id)
        assert len(list(session.scalars(select(AuditEvent)))) == 1
    engine.dispose()


def test_rollback_before_claim_commit_cannot_authorize_dispatch(db_session, monkeypatch):
    import app.services.guarded_operation_ledger as ledger

    operation_id = reservation(db_session).id

    def audit_failure(*args, **kwargs):
        raise RuntimeError("fixture audit failure")

    monkeypatch.setattr(ledger, "record_audit_event", audit_failure)
    with pytest.raises(RuntimeError, match="audit failure"):
        claim_dispatch(db_session, operation_id, actor="worker")
    db_session.rollback()
    assert db_session.get(GuardedOperation, operation_id).status == "accepted"
    assert len(list(db_session.scalars(select(AuditEvent)))) == 1
