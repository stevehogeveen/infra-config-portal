"""Add durable runtime permissions, reviews and dispatch admissions."""

from alembic import op
import sqlalchemy as sa

revision = "0008_runtime_write_scope"
down_revision = "0007_firmware_reviews"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("runtime_write_scopes"):
        op.create_table(
            "runtime_write_scopes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scope", sa.String(24), nullable=True),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("changed_by", sa.String(255), nullable=True),
        )
    if not sa.inspect(bind).has_table("runtime_scope_reviews"):
        op.create_table(
            "runtime_scope_reviews",
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("actor", sa.String(255), nullable=False),
            sa.Column("target_scope", sa.String(24), nullable=False),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("bootstrap_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed", sa.Boolean(), nullable=False),
        )
    if not sa.inspect(bind).has_table("runtime_dispatch_leases"):
        op.create_table(
            "runtime_dispatch_leases",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("action_id", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade():
    raise RuntimeError("Runtime permission and dispatch history must not be silently discarded")
