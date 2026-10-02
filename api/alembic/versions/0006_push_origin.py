"""push subscriptions remember the site origin they were made on (absolute links in declarative web push)

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("origin", sa.String(length=200), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.drop_column("origin")
