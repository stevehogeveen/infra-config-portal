"""Make iLO credentials and intents device scoped.

Revision ID: 0005_per_device_ilo_credentials
Revises: 0004_provider_runtime_state
Create Date: 2026-08-11
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.services.ilo_device_storage import (
    LEGACY_ILO_BACKFILL_MARKER,
    backfill_legacy_ilo_credentials_once,
    legacy_ilo_backfill_completed,
    matching_legacy_ilo_device_id,
    read_legacy_ilo_env,
)

revision = "0005_per_device_ilo_credentials"
down_revision = "0004_provider_runtime_state"
branch_labels = None
depends_on = None

CREATED_INVENTORY_MARKER = "alembic-0005-created-inventory"
CREATED_STATE_MARKER = "alembic-0005-created-state"
CREATED_BACKFILL_MARKER = "alembic-0005-owns-ilo-backfill"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    created_device_inventory = "device_inventory" not in tables
    created_device_inventory_state = "device_inventory_state" not in tables

    # Device inventory was introduced through create_all before this project
    # added a corresponding Alembic revision. Repair the historical chain so
    # upgrading an empty Alembic-managed database remains valid.
    if "device_inventory" not in tables:
        _create_device_inventory_tables()
        tables.update({"device_inventory", "device_inventory_state"})
    else:
        columns = {column["name"] for column in inspector.get_columns("device_inventory")}
        if "dhcp_enabled" not in columns:
            op.add_column(
                "device_inventory",
                sa.Column(
                    "dhcp_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
    if "device_inventory_state" not in tables:
        _create_device_inventory_state_table()
        tables.add("device_inventory_state")
    _record_created_table_markers(
        connection,
        inventory=created_device_inventory,
        state=created_device_inventory_state,
    )

    if "ilo_device_credentials" not in tables:
        op.create_table(
            "ilo_device_credentials",
            sa.Column("device_id", sa.String(length=36), nullable=False),
            sa.Column("credentials_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["device_id"],
                ["device_inventory.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("device_id"),
        )

    legacy_values = read_legacy_ilo_env()
    device_id = matching_legacy_ilo_device_id(connection, legacy_values)
    for table_name in ("ilo_setup_intents", "hpe_raid_intents"):
        columns = {column["name"] for column in sa.inspect(connection).get_columns(table_name)}
        if "device_id" not in columns:
            _expand_intent_table(connection, table_name, device_id)

    # The credential import is deliberately last so the FK target and final
    # tables exist. It never overwrites an already-migrated credential row.
    backfill_marker_existed = legacy_ilo_backfill_completed(connection)
    backfill_legacy_ilo_credentials_once(connection, legacy_values)
    if not backfill_marker_existed:
        _record_state_marker(connection, CREATED_BACKFILL_MARKER)


def downgrade() -> None:
    connection = op.get_bind()
    created_inventory = _has_created_table_marker(connection, CREATED_INVENTORY_MARKER)
    created_state = _has_created_table_marker(connection, CREATED_STATE_MARKER)
    created_backfill_marker = _has_created_table_marker(
        connection,
        CREATED_BACKFILL_MARKER,
    )
    for table_name in ("ilo_setup_intents", "hpe_raid_intents"):
        _collapse_intent_table(connection, table_name)
    op.drop_table("ilo_device_credentials")
    if created_state:
        op.drop_table("device_inventory_state")
    elif "device_inventory_state" in sa.inspect(connection).get_table_names():
        state = sa.Table("device_inventory_state", sa.MetaData(), autoload_with=connection)
        removable_markers = [CREATED_INVENTORY_MARKER, CREATED_STATE_MARKER]
        if created_backfill_marker:
            removable_markers.extend(
                [LEGACY_ILO_BACKFILL_MARKER, CREATED_BACKFILL_MARKER]
            )
        connection.execute(
            state.delete().where(state.c.id.in_(removable_markers))
        )
    if created_inventory:
        op.drop_table("device_inventory")


def _create_device_inventory_tables() -> None:
    op.create_table(
        "device_inventory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_type", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("host", sa.String(length=300), nullable=True),
        sa.Column(
            "dhcp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("seed_key", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seed_key"),
    )
    op.create_index(
        op.f("ix_device_inventory_device_type"),
        "device_inventory",
        ["device_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_inventory_display_name"),
        "device_inventory",
        ["display_name"],
        unique=False,
    )
    _create_device_inventory_state_table()


def _create_device_inventory_state_table() -> None:
    op.create_table(
        "device_inventory_state",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def _record_created_table_markers(
    connection: Connection,
    *,
    inventory: bool,
    state: bool,
) -> None:
    if not inventory and not state:
        return
    table = sa.Table("device_inventory_state", sa.MetaData(), autoload_with=connection)
    now = datetime.now(UTC)
    for marker, created in (
        (CREATED_INVENTORY_MARKER, inventory),
        (CREATED_STATE_MARKER, state),
    ):
        if not created:
            continue
        _record_state_marker(connection, marker, table=table, now=now)


def _record_state_marker(
    connection: Connection,
    marker: str,
    *,
    table: sa.Table | None = None,
    now: datetime | None = None,
) -> None:
    state = (
        table
        if table is not None
        else sa.Table(
            "device_inventory_state",
            sa.MetaData(),
            autoload_with=connection,
        )
    )
    exists = connection.execute(
        sa.select(state.c.id).where(state.c.id == marker)
    ).first()
    if exists is None:
        connection.execute(
            state.insert(),
            {"id": marker, "seeded_at": now or datetime.now(UTC)},
        )


def _has_created_table_marker(connection: Connection, marker: str) -> bool:
    if "device_inventory_state" not in sa.inspect(connection).get_table_names():
        return False
    table = sa.Table("device_inventory_state", sa.MetaData(), autoload_with=connection)
    return connection.execute(
        sa.select(table.c.id).where(table.c.id == marker)
    ).first() is not None


def _collapse_intent_table(connection: Connection, table_name: str) -> None:
    if table_name not in {"ilo_setup_intents", "hpe_raid_intents"}:
        raise ValueError("Unsupported iLO intent table.")
    legacy = sa.Table(table_name, sa.MetaData(), autoload_with=connection)
    row = connection.execute(
        sa.select(
            legacy.c.provider_id,
            legacy.c.intent_json,
            legacy.c.created_at,
            legacy.c.updated_at,
        )
        .where(legacy.c.provider_id == "ilo-redfish")
        .order_by(legacy.c.updated_at.desc(), legacy.c.device_id)
        .limit(1)
    ).mappings().first()
    temporary = f"_{table_name}_singleton"
    op.create_table(
        temporary,
        sa.Column("provider_id", sa.String(length=80), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider_id"),
    )
    if row is not None:
        replacement = sa.Table(temporary, sa.MetaData(), autoload_with=connection)
        connection.execute(replacement.insert(), dict(row))
    op.drop_table(table_name)
    op.rename_table(temporary, table_name)


def _expand_intent_table(
    connection: Connection,
    table_name: str,
    device_id: str | None,
) -> None:
    if table_name not in {"ilo_setup_intents", "hpe_raid_intents"}:
        raise ValueError("Unsupported iLO intent table.")
    legacy = sa.Table(table_name, sa.MetaData(), autoload_with=connection)
    row = connection.execute(
        sa.select(
            legacy.c.provider_id,
            legacy.c.intent_json,
            legacy.c.created_at,
            legacy.c.updated_at,
        )
        .where(legacy.c.provider_id == "ilo-redfish")
        .limit(1)
    ).mappings().first()
    temporary = f"_{table_name}_per_device"
    op.create_table(
        temporary,
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=80), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["device_inventory.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", "provider_id"),
    )
    if device_id is not None and row is not None:
        replacement = sa.Table(temporary, sa.MetaData(), autoload_with=connection)
        connection.execute(replacement.insert(), {"device_id": device_id, **dict(row)})
    op.drop_table(table_name)
    op.rename_table(temporary, table_name)
