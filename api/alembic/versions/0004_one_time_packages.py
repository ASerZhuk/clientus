"""one-time packages: standard / domain / self_hosted

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.alter_column("plan", existing_type=sa.String(length=16), server_default="standard", existing_nullable=False)
    # legacy tier names -> packages
    op.execute("UPDATE tenants SET plan = 'standard' WHERE plan = 'start'")
    op.execute("UPDATE tenants SET plan = 'domain' WHERE plan IN ('studio', 'pro')")


def downgrade() -> None:
    op.execute("UPDATE tenants SET plan = 'start' WHERE plan = 'standard'")
    op.execute("UPDATE tenants SET plan = 'studio' WHERE plan IN ('domain', 'self_hosted')")
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.alter_column("plan", existing_type=sa.String(length=16), server_default="start", existing_nullable=False)
