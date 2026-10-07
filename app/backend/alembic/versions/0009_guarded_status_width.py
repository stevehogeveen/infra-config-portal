"""Widen guarded_operations.status: offline-SPP states such as
"spp-offline-observation-timeout" and "spp-offline-uncertain-media" exceed 24 characters."""

import sqlalchemy as sa
from alembic import op

revision = "0009_guarded_status_width"
down_revision = "0008_runtime_write_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("guarded_operations") as batch:
        batch.alter_column("status", type_=sa.String(64), existing_type=sa.String(24), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("guarded_operations") as batch:
        batch.alter_column("status", type_=sa.String(24), existing_type=sa.String(64), existing_nullable=False)
