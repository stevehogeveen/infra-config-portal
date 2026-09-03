from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.services.ilo_device_storage import (
    LEGACY_ILO_BACKFILL_MARKER,
    IloDeviceStorageError,
    backfill_legacy_ilo_credentials,
    ensure_per_device_ilo_storage,
)


DEVICE_ID = "00000000-0000-0000-0000-000000000052"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _create_legacy_runtime_schema(engine) -> None:  # noqa: ANN001
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE device_inventory ("
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "device_type VARCHAR(80) NOT NULL, "
            "host VARCHAR(300), seed_key VARCHAR(80), "
            "created_at DATETIME NOT NULL)"
        )
        connection.execute(
            text(
                "INSERT INTO device_inventory "
                "(id, device_type, host, seed_key, created_at) "
                "VALUES (:id, 'ilo', :host, 'ilo-primary', :created_at)"
            ),
            {
                "id": DEVICE_ID,
                "host": "192.0.2.52",
                "created_at": "2026-08-11 12:00:00",
            },
        )
        connection.exec_driver_sql(
            "CREATE TABLE device_inventory_state ("
            "id VARCHAR(40) NOT NULL PRIMARY KEY, seeded_at DATETIME NOT NULL)"
        )
        for table_name in ("ilo_setup_intents", "hpe_raid_intents"):
            connection.exec_driver_sql(
                f"CREATE TABLE {table_name} ("
                "provider_id VARCHAR(80) NOT NULL PRIMARY KEY, "
                "intent_json JSON NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
            connection.execute(
                text(
                    f"INSERT INTO {table_name} "
                    "(provider_id, intent_json, created_at, updated_at) "
                    "VALUES ('ilo-redfish', :intent, :created_at, :created_at)"
                ),
                {
                    "intent": json.dumps({"notes": f"legacy {table_name}"}),
                    "created_at": "2026-08-11 12:01:00",
                },
            )


def test_startup_guard_upgrades_create_all_managed_legacy_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-runtime.db'}")
    _create_legacy_runtime_schema(engine)
    monkeypatch.setenv("ILO_TEST_HOST", "192.0.2.52")
    monkeypatch.setenv("ILO_TEST_USERNAME", "Mock-Administrator")
    monkeypatch.setenv("ILO_TEST_PASSWORD", "mock-startup-password")
    monkeypatch.setenv("ILO_TEST_VERIFY_TLS", "false")

    ensure_per_device_ilo_storage(engine)

    inspector = inspect(engine)
    assert inspector.get_pk_constraint("ilo_device_credentials")["constrained_columns"] == [
        "device_id"
    ]
    for table_name in ("ilo_setup_intents", "hpe_raid_intents"):
        assert inspector.get_pk_constraint(table_name)["constrained_columns"] == [
            "device_id",
            "provider_id",
        ]
    with engine.connect() as connection:
        credentials = connection.execute(
            text(
                "SELECT device_id, credentials_json "
                "FROM ilo_device_credentials"
            )
        ).one()
        assert credentials.device_id == DEVICE_ID
        assert json.loads(credentials.credentials_json)["password"] == "mock-startup-password"
        assert connection.scalar(
            text(
                "SELECT count(*) FROM device_inventory_state "
                "WHERE id = :marker"
            ),
            {"marker": LEGACY_ILO_BACKFILL_MARKER},
        ) == 1
        for table_name in ("ilo_setup_intents", "hpe_raid_intents"):
            assert connection.scalar(
                text(f"SELECT device_id FROM {table_name}")
            ) == DEVICE_ID
    engine.dispose()


def test_startup_guard_records_no_match_and_never_retries_import(
    tmp_path,
    monkeypatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-no-match-runtime.db'}")
    _create_legacy_runtime_schema(engine)
    monkeypatch.setenv("ILO_TEST_HOST", "192.0.2.99")
    monkeypatch.setenv("ILO_TEST_USERNAME", "Mock-Administrator")
    monkeypatch.setenv("ILO_TEST_PASSWORD", "mock-stale-password")
    monkeypatch.setenv("ILO_TEST_VERIFY_TLS", "false")

    ensure_per_device_ilo_storage(engine)
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ilo_device_credentials")) == 0
        assert connection.scalar(
            text(
                "SELECT count(*) FROM device_inventory_state "
                "WHERE id = :marker"
            ),
            {"marker": LEGACY_ILO_BACKFILL_MARKER},
        ) == 1
        connection.execute(
            text("UPDATE device_inventory SET host = '192.0.2.99' WHERE id = :id"),
            {"id": DEVICE_ID},
        )

    ensure_per_device_ilo_storage(engine)

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ilo_device_credentials")) == 0
    engine.dispose()


def test_alembic_no_match_marker_prevents_later_startup_import(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-no-match.db'}"
    engine = create_engine(database_url)
    _create_legacy_runtime_schema(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('0004_provider_runtime_state')")
        )
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ILO_TEST_HOST", "192.0.2.99")
    monkeypatch.setenv("ILO_TEST_USERNAME", "Mock-Administrator")
    monkeypatch.setenv("ILO_TEST_PASSWORD", "mock-stale-password")
    monkeypatch.setenv("ILO_TEST_VERIFY_TLS", "false")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ilo_device_credentials")) == 0
        assert connection.scalar(
            text(
                "SELECT count(*) FROM device_inventory_state "
                "WHERE id = :marker"
            ),
            {"marker": LEGACY_ILO_BACKFILL_MARKER},
        ) == 1
        connection.execute(
            text("UPDATE device_inventory SET host = '192.0.2.99' WHERE id = :id"),
            {"id": DEVICE_ID},
        )

    ensure_per_device_ilo_storage(engine)

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ilo_device_credentials")) == 0
    engine.dispose()


def test_backfill_failure_never_exposes_bound_legacy_password(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'backfill-failure.db'}")
    password = "mock-password-must-not-escape"
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE device_inventory ("
            "id VARCHAR(36) NOT NULL PRIMARY KEY, device_type VARCHAR(80) NOT NULL, "
            "host VARCHAR(300), seed_key VARCHAR(80), created_at DATETIME NOT NULL)"
        )
        connection.execute(
            text(
                "INSERT INTO device_inventory "
                "(id, device_type, host, seed_key, created_at) "
                "VALUES (:id, 'ilo', '192.0.2.52', 'ilo-primary', '2026-08-11 12:00:00')"
            ),
            {"id": DEVICE_ID},
        )
        connection.exec_driver_sql(
            "CREATE TABLE ilo_device_credentials ("
            "device_id VARCHAR(36) NOT NULL PRIMARY KEY, credentials_json JSON NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
            "CHECK (length(credentials_json) < 1))"
        )

        with pytest.raises(IloDeviceStorageError) as raised:
            backfill_legacy_ilo_credentials(
                connection,
                {
                    "ILO_TEST_HOST": "192.0.2.52",
                    "ILO_TEST_USERNAME": "Mock-Administrator",
                    "ILO_TEST_PASSWORD": password,
                    "ILO_TEST_VERIFY_TLS": "false",
                },
            )

    assert password not in str(raised.value)
    assert raised.value.__suppress_context__ is True
    engine.dispose()


def test_fresh_alembic_downgrade_removes_inventory_repair_tables(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'fresh-downgrade.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ILO_ACCESS_ENV_FILE", str(tmp_path / "missing-legacy-env"))
    for key in (
        "ILO_TEST_HOST",
        "ILO_TEST_USERNAME",
        "ILO_TEST_PASSWORD",
        "ILO_TEST_VERIFY_TLS",
    ):
        monkeypatch.delenv(key, raising=False)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    command.upgrade(config, "head")
    command.downgrade(config, "0004_provider_runtime_state")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "ilo_device_credentials" not in tables
    assert "device_inventory" not in tables
    assert "device_inventory_state" not in tables
    engine.dispose()
