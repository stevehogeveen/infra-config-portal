"""Additive review migration checks against disposable SQLite only."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_review_migration_preserves_existing_records_and_refuses_downgrade(tmp_path):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0007_firmware_reviews.py"
    spec = importlib.util.spec_from_file_location("review_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE guarded_operations (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO guarded_operations VALUES ('preserved-operation')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(
            text("""
            INSERT INTO firmware_approvals
            (id, token_hash, profile_id, device_id, actor, intent_json,
             confirmation_phrase, expires_at, created_at, operation_id)
            VALUES ('review', 'hash', 'kit', 'device', 'operator', '{}', 'INSTALL',
                    '2026-09-28', '2026-09-28', 'preserved-operation')
        """)
        )
        migration.upgrade()
        assert connection.scalar(text("SELECT id FROM guarded_operations")) == "preserved-operation"
        assert connection.scalar(text("SELECT id FROM firmware_approvals")) == "review"
        constraints = inspect(connection).get_unique_constraints("firmware_approvals")
        assert {tuple(item["column_names"]) for item in constraints} == {
            ("token_hash",),
            ("operation_id",),
        }
        with pytest.raises(RuntimeError, match="must not be silently discarded"):
            migration.downgrade()
        assert connection.scalar(text("SELECT COUNT(*) FROM firmware_approvals")) == 1
    engine.dispose()
