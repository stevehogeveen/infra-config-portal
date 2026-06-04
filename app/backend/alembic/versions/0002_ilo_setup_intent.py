"""Add iLO setup intent persistence.

Revision ID: 0002_ilo_setup_intent
Revises: 0001_initial
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_ilo_setup_intent"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ilo_setup_intents",
        sa.Column("provider_id", sa.String(length=80), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider_id"),
    )


def downgrade() -> None:
    op.drop_table("ilo_setup_intents")
