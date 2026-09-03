from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import Engine


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_REVISION = "0005_per_device_ilo_credentials"
PROVIDER_ID = "ilo-redfish"
DEVICE_A = "00000000-0000-0000-0000-00000000000a"
DEVICE_B = "00000000-0000-0000-0000-00000000000b"
INTENT_TABLES = ("ilo_setup_intents", "hpe_raid_intents")

LEGACY_SETUP_INTENT = {
    "network": {"hostname": "legacy-mock-ilo"},
    "notes": "Legacy setup intent",
}
LEGACY_RAID_INTENT = {
    "controller_ref": "legacy-mock-controller",
    "volumes": [
        {
            "name": "Legacy-Mock-OS",
            "purpose": "ESXi install",
            "raid_level": "RAID1",
            "drive_bays": ["1", "2"],
        }
    ],
}


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _prepare_legacy_database(path: Path, *, device_hosts: tuple[str, str]) -> str:
    database_url = _sqlite_url(path)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": "0004_provider_runtime_state"},
            )
            connection.exec_driver_sql(
                "CREATE TABLE device_inventory ("
                "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                "device_type VARCHAR(80) NOT NULL, "
                "display_name VARCHAR(200) NOT NULL, "
                "host VARCHAR(300), "
                "dhcp_enabled BOOLEAN NOT NULL DEFAULT 0, "
                "notes TEXT, "
                "seed_key VARCHAR(80) UNIQUE, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL"
                ")"
            )
            for device_id, display_name, host, seed_key, created_at in (
                (
                    DEVICE_A,
                    "Legacy Mock iLO A",
                    device_hosts[0],
                    "ilo-primary",
                    "2026-08-10 12:00:00",
                ),
                (
                    DEVICE_B,
                    "Legacy Mock iLO B",
                    device_hosts[1],
                    None,
                    "2026-08-10 12:01:00",
                ),
            ):
                connection.execute(
                    text(
                        "INSERT INTO device_inventory ("
                        "id, device_type, display_name, host, dhcp_enabled, notes, "
                        "seed_key, created_at, updated_at"
                        ") VALUES ("
                        ":id, 'ilo', :display_name, :host, 0, NULL, :seed_key, "
                        ":created_at, :created_at"
                        ")"
                    ),
                    {
                        "id": device_id,
                        "display_name": display_name,
                        "host": host,
                        "seed_key": seed_key,
                        "created_at": created_at,
                    },
                )

            for table_name, intent in (
                ("ilo_setup_intents", LEGACY_SETUP_INTENT),
                ("hpe_raid_intents", LEGACY_RAID_INTENT),
            ):
                connection.exec_driver_sql(
                    f"CREATE TABLE {table_name} ("
                    "provider_id VARCHAR(80) NOT NULL PRIMARY KEY, "
                    "intent_json JSON NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL"
                    ")"
                )
                connection.execute(
                    text(
                        f"INSERT INTO {table_name} ("
                        "provider_id, intent_json, created_at, updated_at"
                        ") VALUES (:provider_id, :intent_json, :created_at, :updated_at)"
                    ),
                    {
                        "provider_id": PROVIDER_ID,
                        "intent_json": json.dumps(intent),
                        "created_at": "2026-08-10 12:02:00",
                        "updated_at": "2026-08-10 12:03:00",
                    },
                )
    finally:
        engine.dispose()
    return database_url


def _write_legacy_env(path: Path, *, host: str) -> bytes:
    contents = (
        f'ILO_TEST_HOST="{host}"\r\n'
        'ILO_TEST_USERNAME="Legacy-Mock-Administrator"\r\n'
        'ILO_TEST_PASSWORD="mock-legacy-password"\r\n'
        'ILO_TEST_VERIFY_TLS="false"\r\n'
    ).encode()
    path.write_bytes(contents)
    return contents


def _configure_migration_environment(
    monkeypatch,
    *,
    database_url: str,
    env_path: Path,
    host: str,
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ILO_ACCESS_ENV_FILE", str(env_path))
    monkeypatch.setenv("ILO_TEST_HOST", host)
    monkeypatch.setenv("ILO_TEST_USERNAME", "Legacy-Mock-Administrator")
    monkeypatch.setenv("ILO_TEST_PASSWORD", "mock-legacy-password")
    monkeypatch.setenv("ILO_TEST_VERIFY_TLS", "false")


def _upgrade_to_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _assert_per_device_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    assert inspector.get_pk_constraint("ilo_device_credentials")["constrained_columns"] == [
        "device_id"
    ]
    for table_name in INTENT_TABLES:
        assert inspector.get_pk_constraint(table_name)["constrained_columns"] == [
            "device_id",
            "provider_id",
        ]

    for table_name in ("ilo_device_credentials", *INTENT_TABLES):
        foreign_keys = inspector.get_foreign_keys(table_name)
        assert len(foreign_keys) == 1
        assert foreign_keys[0]["constrained_columns"] == ["device_id"]
        assert foreign_keys[0]["referred_table"] == "device_inventory"
        assert foreign_keys[0]["referred_columns"] == ["id"]
        assert foreign_keys[0].get("options", {}).get("ondelete") == "CASCADE"


def test_migration_backfills_matching_device_and_preserves_legacy_env_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy-match.db"
    database_url = _prepare_legacy_database(
        database_path,
        device_hosts=("192.0.2.11", "192.0.2.12"),
    )
    env_path = tmp_path / ".env.local.real-lab"
    original_env = _write_legacy_env(env_path, host="192.0.2.11")
    _configure_migration_environment(
        monkeypatch,
        database_url=database_url,
        env_path=env_path,
        host="192.0.2.11",
    )

    _upgrade_to_head()

    assert env_path.read_bytes() == original_env
    engine = create_engine(database_url)
    try:
        _assert_per_device_schema(engine)
        metadata = MetaData()
        credentials = Table("ilo_device_credentials", metadata, autoload_with=engine)
        setup_intents = Table("ilo_setup_intents", metadata, autoload_with=engine)
        raid_intents = Table("hpe_raid_intents", metadata, autoload_with=engine)
        with engine.connect() as connection:
            credential_rows = connection.execute(select(credentials)).mappings().all()
            setup_rows = connection.execute(select(setup_intents)).mappings().all()
            raid_rows = connection.execute(select(raid_intents)).mappings().all()
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))

        assert revision == MIGRATION_REVISION
        assert len(credential_rows) == 1
        assert credential_rows[0]["device_id"] == DEVICE_A
        assert _json(credential_rows[0]["credentials_json"]) == {
            "host": "192.0.2.11",
            "username": "Legacy-Mock-Administrator",
            "password": "mock-legacy-password",
            "verify_tls": False,
        }
        assert len(setup_rows) == 1
        assert setup_rows[0]["device_id"] == DEVICE_A
        assert setup_rows[0]["provider_id"] == PROVIDER_ID
        assert _json(setup_rows[0]["intent_json"]) == LEGACY_SETUP_INTENT
        assert len(raid_rows) == 1
        assert raid_rows[0]["device_id"] == DEVICE_A
        assert raid_rows[0]["provider_id"] == PROVIDER_ID
        assert _json(raid_rows[0]["intent_json"]) == LEGACY_RAID_INTENT
    finally:
        engine.dispose()


def test_migration_without_matching_device_drops_singletons_cleanly(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy-no-match.db"
    database_url = _prepare_legacy_database(
        database_path,
        device_hosts=("198.51.100.11", "198.51.100.12"),
    )
    env_path = tmp_path / ".env.local.real-lab"
    original_env = _write_legacy_env(env_path, host="198.51.100.99")
    _configure_migration_environment(
        monkeypatch,
        database_url=database_url,
        env_path=env_path,
        host="198.51.100.99",
    )

    _upgrade_to_head()

    assert env_path.read_bytes() == original_env
    engine = create_engine(database_url)
    try:
        _assert_per_device_schema(engine)
        metadata = MetaData()
        credentials = Table("ilo_device_credentials", metadata, autoload_with=engine)
        setup_intents = Table("ilo_setup_intents", metadata, autoload_with=engine)
        raid_intents = Table("hpe_raid_intents", metadata, autoload_with=engine)
        with engine.connect() as connection:
            assert connection.execute(select(credentials)).all() == []
            assert connection.execute(select(setup_intents)).all() == []
            assert connection.execute(select(raid_intents)).all() == []
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == MIGRATION_REVISION
    finally:
        engine.dispose()
