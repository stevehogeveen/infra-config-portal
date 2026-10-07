from datetime import UTC, datetime, timedelta
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditEvent, GuardedOperation, RuntimeScopeReview, RuntimeWriteScope
from app.services import runtime_write_scope as scope


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch):
    monkeypatch.setattr(
        "app.providers.action_policy.current_lab_action_policy",
        lambda: SimpleNamespace(provider_mode="local-lab-readwrite", readonly_blockers=lambda: []),
    )


def grant(session, actor="operator", target="firmware_only"):
    review = scope.preview(session, actor, target)
    return scope.apply(session, actor, review["review_token"], review["confirmation_phrase"])


def test_deployment_does_not_grant_and_preview_is_not_apply(db_session):
    assert scope.state(db_session)["source"] == "server_configuration"
    preview = scope.preview(db_session, "operator", "firmware_only")
    assert preview["blocker_details"] == []
    assert db_session.get(RuntimeWriteScope, 1).scope is None


def test_grant_is_durable_audited_and_does_not_change_env(db_session, monkeypatch):
    monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "ilo-redfish.hpe-raid-apply")
    result = grant(db_session)
    assert result["scope"] == "firmware_only"
    assert result["changed_by"] == "operator"
    assert scope.bootstrap()["actions"] == ["ilo-redfish.hpe-raid-apply"]
    db_session.expire_all()
    assert scope.state(db_session)["scope"] == "firmware_only"
    assert (
        db_session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "runtime.write_scope.applied")
        )
        is not None
    )


@pytest.mark.parametrize(
    "failure", ["actor", "phrase", "expired", "environment", "replay", "stale"]
)
def test_review_binding(db_session, monkeypatch, failure):
    review = scope.preview(db_session, "operator", "firmware_only")
    actor, phrase = "operator", review["confirmation_phrase"]
    if failure == "actor":
        actor = "someone-else"
    elif failure == "phrase":
        phrase = "yes"
    elif failure == "expired":
        db_session.scalar(select(RuntimeScopeReview)).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db_session.commit()
    elif failure == "environment":
        monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "changed")
    elif failure == "replay":
        scope.apply(db_session, actor, review["review_token"], phrase)
    elif failure == "stale":
        grant(db_session, target="read_only")
    with pytest.raises(scope.WriteScopeError):
        scope.apply(db_session, actor, review["review_token"], phrase)
    db_session.rollback()


def test_dispatch_after_preview_blocks_grant_and_revoke_keeps_lease(db_session):
    review = scope.preview(db_session, "operator", "firmware_only")
    lease = scope.admit_dispatch(db_session, "ilo-redfish.hpe-raid-apply")
    with pytest.raises(scope.WriteScopeError, match=lease):
        scope.apply(db_session, "operator", review["review_token"], review["confirmation_phrase"])
    db_session.rollback()
    result = grant(db_session, target="read_only")
    assert any(x["operation_id"] == lease for x in result["active_operations"])
    with pytest.raises(scope.WriteScopeError):
        scope.admit_dispatch(db_session, scope.FIRMWARE_ACTION)
    db_session.rollback()
    scope.finish_dispatch(db_session, lease)


def test_grant_before_dispatch_excludes_storage(db_session):
    grant(db_session)
    with pytest.raises(scope.WriteScopeError):
        scope.admit_dispatch(db_session, "ilo-redfish.hpe-raid-apply")
    db_session.rollback()
    lease = scope.admit_dispatch(db_session, scope.FIRMWARE_ACTION)
    assert lease


def test_guarded_lock_survives_read_only(db_session):
    db_session.add(
        GuardedOperation(
            profile_id="kit",
            device_id="server",
            resource="firmware",
            idempotency_key="key",
            intent_hash="f" * 64,
            active_device="server",
            status="uncertain",
        )
    )
    db_session.commit()
    assert scope.preview(db_session, "operator", "firmware_only")["blockers"]
    assert grant(db_session, target="read_only")["active_operations"][0]["status"] == "uncertain"


def test_legacy_pending_blocks_but_verified_wipe_does_not(db_session):
    attempt = AuditEvent(
        actor="operator",
        event_type="kit.raid_rebuild.attempt",
        message="test",
        data_json={"device_id": "server", "operation": "sanitize"},
    )
    db_session.add(attempt)
    db_session.commit()
    assert scope.preview(db_session, "operator", "firmware_only")["blockers"]
    db_session.add(
        AuditEvent(
            actor="operator",
            event_type="kit.raid_rebuild.verified",
            message="test",
            data_json={"device_id": "server", "attempt_id": attempt.id},
        )
    )
    db_session.commit()
    assert not scope.preview(db_session, "operator", "firmware_only")["blockers"]


def test_no_new_storage_scope(db_session):
    with pytest.raises(scope.WriteScopeError):
        scope.preview(db_session, "operator", "storage")


def test_historical_proven_rejection_is_not_an_active_operation(db_session):
    attempt = AuditEvent(
        actor="operator",
        event_type="kit.raid_rebuild.attempt",
        message="test",
        data_json={"device_id": "server", "operation": "reset", "identity": "same-target"},
    )
    db_session.add(attempt)
    db_session.commit()
    failure = AuditEvent(
        actor="operator",
        event_type="kit.raid_rebuild.failed",
        message="test",
        data_json={"device_id": "server", "attempt_id": attempt.id},
    )
    db_session.add(failure)
    db_session.commit()
    assert scope.active_operations(db_session)
    failure.data_json = {
        **failure.data_json,
        "identity": "same-target",
        "codes": ["SmartStorageMessages.2.0.1.PropertyKeyMissing"],
        "reported_at": datetime.now(UTC).isoformat(),
    }
    db_session.commit()
    assert scope.active_operations(db_session) == []


@pytest.mark.parametrize("identity,blocked", [("same-target", False), ("different-target", True)])
def test_old_shutdown_needs_subsequent_same_target_completion(db_session, identity, blocked):
    old = datetime.now(UTC) - timedelta(minutes=5)
    db_session.add(
        AuditEvent(
            actor="operator",
            event_type="kit.raid_rebuild.shutdown_attempt",
            message="test",
            created_at=old,
            data_json={"device_id": "server", "identity": "same-target"},
        )
    )
    attempt = AuditEvent(
        actor="operator",
        event_type="kit.raid_rebuild.attempt",
        message="test",
        data_json={"device_id": "server", "identity": identity},
    )
    db_session.add(attempt)
    db_session.commit()
    db_session.add(
        AuditEvent(
            actor="operator",
            event_type="kit.raid_rebuild.verified",
            message="test",
            data_json={"device_id": "server", "attempt_id": attempt.id},
        )
    )
    db_session.commit()
    assert bool(scope.active_operations(db_session)) is blocked


def test_api_matches_frontend_contract(client):
    base = "/api/v1/runtime/write-scope"
    assert client.get(base).json()["source"] == "server_configuration"
    response = client.post(
        base + "/preview",
        json={"target_scope": "firmware_only"},
        headers={"X-Local-User": "operator"},
    )
    assert response.status_code == 200
    review = response.json()
    body = {
        "review_token": review["review_token"],
        "confirmation_phrase": review["confirmation_phrase"],
    }
    assert client.post(base + "/apply", json=body).status_code == 409
    result = client.post(base + "/apply", json=body, headers={"X-Local-User": "operator"})
    assert result.status_code == 200
    assert client.get(base).json()["scope"] == "firmware_only"
    assert (
        client.post(base + "/apply", json=body, headers={"X-Local-User": "operator"}).status_code
        == 409
    )
    assert client.post(base + "/preview", json={"target_scope": "storage"}).status_code == 422


def test_policy_uses_database_instead_of_old_flags(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.providers.action_policy import ActionCategory, LabActionPolicy

    monkeypatch.setattr("app.core.database.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    monkeypatch.setenv("LAB_ALLOWED_WRITE_ACTIONS", "ilo-redfish.hpe-raid-apply")
    policy = LabActionPolicy(
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        acknowledge_real_hardware=True,
        acknowledge_device_reconfiguration=True,
        acknowledge_data_loss_risk=True,
        acknowledge_lab_only=True,
        allow_power_actions=True,
        allow_firmware_updates=False,
        allow_factory_reset=True,
        legacy_closed_loop_ack=False,
        legacy_readonly_ack=False,
        legacy_destructive_ack=False,
    )
    assert policy.action_blockers(scope.FIRMWARE_ACTION, ActionCategory.FIRMWARE_UPDATE)
    grant(db_session)
    assert scope.firmware_only()
    assert not policy.action_blockers(scope.FIRMWARE_ACTION, ActionCategory.FIRMWARE_UPDATE)
    assert policy.action_blockers("ilo-redfish.hpe-raid-apply", ActionCategory.STORAGE_CONFIG)
    assert policy.action_blockers("ilo.power-action", ActionCategory.POWER_ACTION)
    grant(db_session, target="read_only")
    assert policy.action_blockers(scope.FIRMWARE_ACTION, ActionCategory.FIRMWARE_UPDATE)
    assert not policy.action_blockers("ilo-redfish.inventory", ActionCategory.READONLY)


@pytest.mark.parametrize(
    "backend",
    [
        "sqlite",
        pytest.param(
            "postgres",
            marks=pytest.mark.skipif(
                os.getenv("OFFLINE_POSTGRES_LEDGER_TEST") != "1",
                reason="Explicit disposable PostgreSQL fixture only",
            ),
        ),
    ],
)
def test_admission_and_scope_change_serialize_across_sessions(tmp_path, backend):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.database import Base
    from sqlalchemy.schema import CreateSchema
    from uuid import uuid4

    engine = create_engine(
        "sqlite:///" + str(tmp_path / "races.db"),
        connect_args={"check_same_thread": False, "timeout": 20},
    )
    if backend == "postgres":
        engine.dispose()
        engine = create_engine(
            "postgresql+psycopg://fixture:fixture-only@127.0.0.1:5432/guarded_fixture"
        )
        schema = "scope_" + uuid4().hex
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        review = scope.preview(session, "operator", "firmware_only")
    barrier = Barrier(2)

    def compete(granting):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                if granting:
                    scope.apply(
                        session, "operator", review["review_token"], review["confirmation_phrase"]
                    )
                else:
                    scope.admit_dispatch(session, "ilo-redfish.hpe-raid-apply")
                return True
            except scope.WriteScopeError:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, [True, False]))
    assert sum(results) == 1
    engine.dispose()


def test_middleware_holds_legacy_activity_until_response(db_session, monkeypatch):
    import asyncio
    from dataclasses import replace
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr("app.core.database.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    monkeypatch.setattr(
        scope, "settings", replace(scope.settings, provider_mode="local-lab-readwrite")
    )
    observed = []

    async def application(request, receive, send):
        observed.extend(scope.active_operations(db_session))

    middleware = scope.WriteScopeActivityMiddleware(application)
    asyncio.run(
        middleware({"type": "http", "method": "POST", "path": "/api/v1/legacy/apply"}, None, None)
    )
    assert len(observed) == 1
    assert observed[0]["resource"] == "POST /api/v1/legacy/apply"
    assert scope.active_operations(db_session) == []


def test_additive_migration_preserves_existing_data(tmp_path):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    spec = importlib.util.spec_from_file_location(
        "scope_migration",
        Path(__file__).parents[1] / "alembic/versions/0008_runtime_write_scope.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE preserved (value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO preserved VALUES ('saved input')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        assert connection.scalar(text("SELECT value FROM preserved")) == "saved input"
        assert connection.scalar(text("SELECT count(*) FROM runtime_write_scopes")) == 0
        assert "runtime_dispatch_leases" in inspect(connection).get_table_names()
    engine.dispose()


def test_storage_only_allows_exactly_the_raid_build(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.providers.action_policy import ActionCategory, LabActionPolicy

    monkeypatch.setattr("app.core.database.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    policy = LabActionPolicy(
        provider_mode="local-lab-readwrite", lab_environment="isolated-real-lab",
        acknowledge_real_hardware=True, acknowledge_device_reconfiguration=True, acknowledge_data_loss_risk=True,
        acknowledge_lab_only=True, allow_power_actions=False, allow_firmware_updates=False, allow_factory_reset=False,
        legacy_closed_loop_ack=False, legacy_readonly_ack=False, legacy_destructive_ack=False,
    )
    review = scope.preview(db_session, "operator", "storage_only")
    assert review["confirmation_phrase"] == "ONLY BUILD RAID"
    assert review["effects"] == ["Only the server's disks and RAID can be changed (build, delete or wipe), including the restarts that apply it. Nothing else on the server can be changed."]
    scope.apply(db_session, "operator", review["review_token"], review["confirmation_phrase"])
    assert not policy.action_blockers("ilo-redfish.hpe-raid-apply", ActionCategory.STORAGE_CONFIG)
    assert not policy.action_blockers("ilo-redfish.raid-boot", ActionCategory.POWER_ACTION)
    assert not policy.action_blockers("ilo-redfish.raid-shutdown", ActionCategory.POWER_ACTION)
    assert policy.action_blockers("ilo.power-action", ActionCategory.POWER_ACTION)
    assert policy.action_blockers(scope.FIRMWARE_ACTION, ActionCategory.FIRMWARE_UPDATE)
    assert policy.action_blockers("ilo-redfish.hpe-raid-factory-reset", ActionCategory.FACTORY_RESET)
    assert policy.action_blockers("ilo.virtual-media", ActionCategory.VIRTUAL_MEDIA)
    with pytest.raises(scope.WriteScopeError):
        scope.admit_dispatch(db_session, scope.FIRMWARE_ACTION)
    lease = scope.admit_dispatch(db_session, "ilo-redfish.hpe-raid-apply")
    scope.finish_dispatch(db_session, lease)
    grant(db_session, target="read_only")
    assert policy.action_blockers("ilo-redfish.hpe-raid-apply", ActionCategory.STORAGE_CONFIG)


def test_api_accepts_the_disks_and_raid_scope(client):
    # The storage installers call this endpoint; the request schema must allow storage_only.
    base = "/api/v1/runtime/write-scope"
    headers = {"X-Local-User": "operator"}
    review = client.post(base + "/preview", json={"target_scope": "storage_only"}, headers=headers)
    assert review.status_code == 200, review.text
    assert review.json()["confirmation_phrase"] == "ONLY BUILD RAID"
    body = {"review_token": review.json()["review_token"], "confirmation_phrase": "ONLY BUILD RAID"}
    assert client.post(base + "/apply", json=body, headers=headers).status_code == 200
    assert client.get(base).json()["scope"] == "storage_only"


def test_esxi_install_scope_allows_only_the_installer_actions(db_session):
    result = grant(db_session, target="esxi_install_only")
    assert result["scope"] == "esxi_install_only"
    for action in sorted(scope.ESXI_INSTALL_ACTIONS):
        scope.finish_dispatch(db_session, scope.admit_dispatch(db_session, action))
    for action in ("ilo-redfish.hpe-raid-apply", scope.FIRMWARE_ACTION, "ilo-redfish.disk-sanitize"):
        with pytest.raises(scope.WriteScopeError):
            scope.admit_dispatch(db_session, action)
        db_session.rollback()


def test_every_scope_target_is_accepted_by_the_api_schema():
    from typing import get_args

    from app.api.runtime_write_scope import ScopePreview as PreviewRequest
    from app.services.runtime_write_scope import TARGETS

    assert set(get_args(PreviewRequest.model_fields["target_scope"].annotation)) == TARGETS
