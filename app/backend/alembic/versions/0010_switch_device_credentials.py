"""Per-switch sign-in for the Connect step."""

import sqlalchemy as sa
from alembic import op

revision = "0010_switch_device_credentials"
down_revision = "0009_guarded_status_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "switch_device_credentials",
        sa.Column("device_id", sa.String(36), sa.ForeignKey("device_inventory.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("credentials_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("switch_device_credentials")
