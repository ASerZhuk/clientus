"""push subscriptions remember the device and delivery health; owners remember when they last saw the schedule

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("device", sa.String(length=80), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("last_success_at", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("last_error", sa.String(length=200), nullable=True))
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.add_column(sa.Column("seen_at", sa.Integer(), nullable=True))  # app icon badge: new bookings after this


def downgrade() -> None:
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.drop_column("seen_at")
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.drop_column("last_error")
        batch_op.drop_column("failure_count")
        batch_op.drop_column("last_success_at")
        batch_op.drop_column("device")
