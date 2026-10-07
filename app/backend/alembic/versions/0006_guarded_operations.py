"""Add durable guarded operation identities and device exclusion."""
from alembic import op
import sqlalchemy as sa

revision = "0006_guarded_operations"
down_revision = "0005_per_device_ilo_credentials"
branch_labels = None
depends_on = None


def upgrade():
    # Startup create_all may already have installed this additive table.
    if sa.inspect(op.get_bind()).has_table("guarded_operations"):
        return
    op.create_table(
        "guarded_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("intent_hash", sa.String(64), nullable=False),
        sa.Column("active_device", sa.String(36), unique=True, nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "device_id", "resource", "idempotency_key",
                            name="uq_guarded_attempt"),
    )


def downgrade():
    raise RuntimeError("Guarded operation history must not be silently discarded")
