"""add user badges

Revision ID: 7b1c9d2a3e4f
Revises: d5f3c1a7b8e9
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "7b1c9d2a3e4f"
down_revision = "d5f3c1a7b8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_badge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("badge_code", sa.String(length=40), nullable=False),
        sa.Column("badge_rank", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("badge_code IN ('pioneiro', 'desde_sempre')", name="ck_user_badge_code"),
        sa.CheckConstraint(
            "(badge_code = 'pioneiro' AND badge_rank BETWEEN 1 AND 100) OR (badge_code = 'desde_sempre' AND badge_rank IS NULL)",
            name="ck_user_badge_rank_rules",
        ),
        sa.CheckConstraint("source IN ('signup', 'backfill', 'admin')", name="ck_user_badge_source"),
        sa.UniqueConstraint("user_id", "badge_code", name="uq_user_badge_user_code"),
    )
    op.create_index(
        "uq_user_badge_pioneer_rank",
        "user_badge",
        ["badge_rank"],
        unique=True,
        sqlite_where=sa.text("badge_code = 'pioneiro'"),
        postgresql_where=sa.text("badge_code = 'pioneiro'"),
    )
    op.create_index("ix_user_badge_user_granted_at", "user_badge", ["user_id", "granted_at"])


def downgrade():
    op.drop_index("ix_user_badge_user_granted_at", table_name="user_badge")
    op.drop_index("uq_user_badge_pioneer_rank", table_name="user_badge")
    op.drop_table("user_badge")
