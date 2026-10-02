"""landing page requests

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("business", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default=""),
        sa.Column("city", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("comment", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="new"),
    )
    op.create_index("ix_leads_created_at", "leads", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_leads_created_at", table_name="leads")
    op.drop_table("leads")
