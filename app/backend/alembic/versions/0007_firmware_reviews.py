"""Persist single-use firmware reviews without changing historical operations."""

from alembic import op
import sqlalchemy as sa

revision = "0007_firmware_reviews"
down_revision = "0006_guarded_operations"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("firmware_approvals"):
        return
    op.create_table(
        "firmware_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("profile_id", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("confirmation_phrase", sa.String(256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "operation_id",
            sa.String(36),
            sa.ForeignKey("guarded_operations.id"),
            unique=True,
            nullable=True,
        ),
    )


def downgrade():
    raise RuntimeError("Firmware approval history must not be silently discarded")
