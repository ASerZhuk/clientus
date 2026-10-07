"""service price kind: exact / from / on request

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.add_column(sa.Column("price_kind", sa.String(length=12), nullable=False, server_default="exact"))


def downgrade() -> None:
    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.drop_column("price_kind")
