"""Add provider runtime state persistence.

Revision ID: 0004_provider_runtime_state
Revises: 0003_hpe_raid_intent
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_provider_runtime_state"
down_revision = "0003_hpe_raid_intent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_runtime_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=80), nullable=False),
        sa.Column("device_role", sa.String(length=120), nullable=False),
        sa.Column("discovered_console_port", sa.String(length=300), nullable=True),
        sa.Column("discovered_baud", sa.Integer(), nullable=True),
        sa.Column("configured_state", sa.String(length=80), nullable=False),
        sa.Column("configured", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("last_successful_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_report_path", sa.String(length=400), nullable=True),
        sa.Column("confidence", sa.String(length=40), nullable=True),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "device_role",
            name="uq_provider_runtime_states_provider_device",
        ),
    )
    op.create_index(op.f("ix_provider_runtime_states_provider_id"), "provider_runtime_states", ["provider_id"], unique=False)
    op.create_index(op.f("ix_provider_runtime_states_device_role"), "provider_runtime_states", ["device_role"], unique=False)
    op.create_index(
        op.f("ix_provider_runtime_states_configured_state"),
        "provider_runtime_states",
        ["configured_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_runtime_states_configured_state"), table_name="provider_runtime_states")
    op.drop_index(op.f("ix_provider_runtime_states_device_role"), table_name="provider_runtime_states")
    op.drop_index(op.f("ix_provider_runtime_states_provider_id"), table_name="provider_runtime_states")
    op.drop_table("provider_runtime_states")
