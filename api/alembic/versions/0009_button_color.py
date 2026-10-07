"""studio button colour

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("button_color", sa.String(length=9), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenant_settings", schema=None) as batch_op:
        batch_op.drop_column("button_color")
