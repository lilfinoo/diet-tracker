"""add profile highlights

Revision ID: 8c2a1f7b9d03
Revises: 7b1c9d2a3e4f
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "8c2a1f7b9d03"
down_revision = "7b1c9d2a3e4f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profile_highlight",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("achievement_unlock_id", sa.Integer(), sa.ForeignKey("achievement_unlock.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_badge_id", sa.Integer(), sa.ForeignKey("user_badge.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 3", name="ck_profile_highlight_position"),
        sa.CheckConstraint("target_kind IN ('achievement', 'badge')", name="ck_profile_highlight_target_kind"),
        sa.CheckConstraint(
            "achievement_unlock_id IS NOT NULL OR user_badge_id IS NOT NULL",
            name="ck_profile_highlight_target_present",
        ),
        sa.UniqueConstraint("user_id", "position", name="uq_profile_highlight_user_position"),
        sa.UniqueConstraint("user_id", "achievement_unlock_id", name="uq_profile_highlight_user_achievement"),
        sa.UniqueConstraint("user_id", "user_badge_id", name="uq_profile_highlight_user_badge"),
    )


def downgrade():
    op.drop_table("profile_highlight")
