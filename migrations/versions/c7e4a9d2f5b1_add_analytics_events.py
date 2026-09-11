"""add analytics events

Revision ID: c7e4a9d2f5b1
Revises: b2d8f6e4c1a3
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "c7e4a9d2f5b1"
down_revision = "b2d8f6e4c1a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analytics_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("anonymous_id", sa.String(length=36), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=180), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("dedupe_key", name="uq_analytics_event_dedupe_key"),
    )
    op.create_index("ix_analytics_event_name_created", "analytics_event", ["event_name", "created_at"])
    op.create_index("ix_analytics_event_user_created", "analytics_event", ["user_id", "created_at"])
    op.create_index("ix_analytics_event_anonymous_created", "analytics_event", ["anonymous_id", "created_at"])


def downgrade():
    op.drop_index("ix_analytics_event_anonymous_created", table_name="analytics_event")
    op.drop_index("ix_analytics_event_user_created", table_name="analytics_event")
    op.drop_index("ix_analytics_event_name_created", table_name="analytics_event")
    op.drop_table("analytics_event")
