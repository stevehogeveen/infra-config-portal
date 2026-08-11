from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from sqlalchemy import Connection, Engine, MetaData, Table, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

LEGACY_ENV_KEYS = (
    "ILO_TEST_HOST",
    "ILO_TEST_USERNAME",
    "ILO_TEST_PASSWORD",
    "ILO_TEST_VERIFY_TLS",
)
INTENT_TABLES = ("ilo_setup_intents", "hpe_raid_intents")
LEGACY_ILO_BACKFILL_MARKER = "legacy-ilo-credential-import-v1"
REPO_ROOT = Path(__file__).resolve().parents[4]


class IloDeviceStorageError(RuntimeError):
    pass


def read_legacy_ilo_env() -> dict[str, str]:
    configured = os.getenv("ILO_ACCESS_ENV_FILE")
    isolate_real_lab_env = _legacy_bool(
        os.getenv("INFRA_CONFIG_TEST_ISOLATE_REAL_LAB_ENV"),
        default=False,
    )
    if configured:
        path: Path | None = Path(configured)
    elif isolate_real_lab_env:
        path = None
    else:
        path = REPO_ROOT / ".env.local.real-lab"
    values: dict[str, Any] = {}
    if path is not None and path.exists():
        try:
            values.update(dotenv_values(path))
        except (OSError, UnicodeDecodeError, ValueError):
            pass
    legacy = {
        key: str(values[key]).strip()
        for key in LEGACY_ENV_KEYS
        if values.get(key) is not None and str(values[key]).strip()
    }
    for key in LEGACY_ENV_KEYS:
        runtime_value = _clean(os.getenv(key))
        if runtime_value is not None:
            legacy[key] = runtime_value
    return legacy


def matching_legacy_ilo_device_id(
    connection: Connection,
    values: dict[str, str] | None = None,
) -> str | None:
    legacy = values if values is not None else read_legacy_ilo_env()
    host = _clean(legacy.get("ILO_TEST_HOST"))
    if not host or "device_inventory" not in inspect(connection).get_table_names():
        return None
    rows = connection.execute(
        text(
            "SELECT id, device_type FROM device_inventory "
            "WHERE lower(trim(host)) = lower(:host) "
            "ORDER BY CASE WHEN seed_key = 'ilo-primary' THEN 0 ELSE 1 END, "
            "created_at, id"
        ),
        {"host": host},
    ).fetchall()
    # Device types are operator-entered free text ("ilo", "HPE ILO", "bmc"),
    # so match the same normalization the rack UI uses rather than an exact
    # 'ilo' string, or a legacy board keeps its credentials stranded.
    for row in rows:
        if _is_ilo_device_type(row[1]):
            return str(row[0])
    return None


def _is_ilo_device_type(device_type: Any) -> bool:
    parts = re.sub(r"[^a-z0-9]+", "_", str(device_type or "").casefold()).split("_")
    return "ilo" in parts or "bmc" in parts


def backfill_legacy_ilo_credentials(
    connection: Connection,
    values: dict[str, str] | None = None,
) -> str | None:
    legacy = values if values is not None else read_legacy_ilo_env()
    device_id = matching_legacy_ilo_device_id(connection, legacy)
    if device_id is None or "ilo_device_credentials" not in inspect(connection).get_table_names():
        return None
    table = Table("ilo_device_credentials", MetaData(), autoload_with=connection)
    existing = connection.execute(
        select(table.c.device_id).where(table.c.device_id == device_id)
    ).first()
    if existing is not None:
        return device_id
    now = datetime.now(UTC)
    credentials = {
        "host": _clean(legacy.get("ILO_TEST_HOST")),
        "username": _clean(legacy.get("ILO_TEST_USERNAME")),
        "password": _clean(legacy.get("ILO_TEST_PASSWORD")),
        "verify_tls": _legacy_bool(legacy.get("ILO_TEST_VERIFY_TLS"), default=True),
    }
    try:
        connection.execute(
            table.insert(),
            {
                "device_id": device_id,
                "credentials_json": credentials,
                "created_at": now,
                "updated_at": now,
            },
        )
    except SQLAlchemyError:
        # SQLAlchemy's exception string can include bound JSON parameters,
        # including the legacy password. Never let that text escape into an
        # Alembic/startup traceback.
        raise IloDeviceStorageError(
            "Could not backfill legacy iLO credentials into device-scoped storage."
        ) from None
    return device_id


def legacy_ilo_backfill_completed(connection: Connection) -> bool:
    if "device_inventory_state" not in inspect(connection).get_table_names():
        return False
    table = Table("device_inventory_state", MetaData(), autoload_with=connection)
    return connection.execute(
        select(table.c.id).where(table.c.id == LEGACY_ILO_BACKFILL_MARKER)
    ).first() is not None


def record_legacy_ilo_backfill_completed(connection: Connection) -> None:
    if legacy_ilo_backfill_completed(connection):
        return
    table = Table("device_inventory_state", MetaData(), autoload_with=connection)
    connection.execute(
        table.insert(),
        {
            "id": LEGACY_ILO_BACKFILL_MARKER,
            "seeded_at": datetime.now(UTC),
        },
    )


def backfill_legacy_ilo_credentials_once(
    connection: Connection,
    values: dict[str, str] | None = None,
) -> str | None:
    """Attempt the compatibility import once, including a durable no-match result."""
    tables = set(inspect(connection).get_table_names())
    if "ilo_device_credentials" not in tables or "device_inventory_state" not in tables:
        return None
    if legacy_ilo_backfill_completed(connection):
        return None
    device_id = backfill_legacy_ilo_credentials(connection, values)
    record_legacy_ilo_backfill_completed(connection)
    return device_id


def ensure_per_device_ilo_storage(target_engine: Engine) -> None:
    """Upgrade create_all-managed SQLite databases to per-device iLO storage."""
    if target_engine.dialect.name != "sqlite":
        return
    with target_engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "device_inventory" not in tables:
            return
        if "ilo_device_credentials" not in tables:
            _create_credentials_table(connection)

        legacy_values = read_legacy_ilo_env()
        device_id = matching_legacy_ilo_device_id(connection, legacy_values)
        for table_name in INTENT_TABLES:
            if table_name not in tables:
                continue
            columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
            if "device_id" not in columns:
                rebuild_legacy_intent_table(connection, table_name, device_id)

        # This intentionally runs even when the intent tables already have the
        # new shape: a fresh create_all database is seeded immediately before
        # this guard and still needs its one-time legacy credential import.
        # The marker records both a match and a no-match so later inventory
        # edits cannot revive stale environment credentials.
        backfill_legacy_ilo_credentials_once(connection, legacy_values)


def _create_credentials_table(connection: Connection) -> None:
    connection.exec_driver_sql(
        "CREATE TABLE ilo_device_credentials ("
        "device_id VARCHAR(36) NOT NULL, "
        "credentials_json JSON NOT NULL, "
        "created_at DATETIME NOT NULL, "
        "updated_at DATETIME NOT NULL, "
        "PRIMARY KEY (device_id), "
        "FOREIGN KEY(device_id) REFERENCES device_inventory (id) ON DELETE CASCADE"
        ")"
    )


def rebuild_legacy_intent_table(
    connection: Connection,
    table_name: str,
    device_id: str | None,
) -> None:
    if table_name not in INTENT_TABLES:
        raise ValueError("Unsupported iLO intent table.")
    temporary = f"_{table_name}_per_device"
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {temporary}")
    connection.exec_driver_sql(
        f"CREATE TABLE {temporary} ("
        "device_id VARCHAR(36) NOT NULL, "
        "provider_id VARCHAR(80) NOT NULL, "
        "intent_json JSON NOT NULL, "
        "created_at DATETIME NOT NULL, "
        "updated_at DATETIME NOT NULL, "
        "PRIMARY KEY (device_id, provider_id), "
        "FOREIGN KEY(device_id) REFERENCES device_inventory (id) ON DELETE CASCADE"
        ")"
    )
    if device_id is not None:
        connection.execute(
            text(
                f"INSERT INTO {temporary} "
                "(device_id, provider_id, intent_json, created_at, updated_at) "
                f"SELECT :device_id, provider_id, intent_json, created_at, updated_at FROM {table_name} "
                "WHERE provider_id = 'ilo-redfish' LIMIT 1"
            ),
            {"device_id": device_id},
        )
    connection.exec_driver_sql(f"DROP TABLE {table_name}")
    connection.exec_driver_sql(f"ALTER TABLE {temporary} RENAME TO {table_name}")


def _legacy_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
