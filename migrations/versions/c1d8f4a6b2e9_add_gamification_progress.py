"""Add daily gamification progress."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "c1d8f4a6b2e9"
down_revision = "b8d0f2a4c6e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gamification_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_protections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_gamification_profile_user"),
        sa.CheckConstraint("available_protections BETWEEN 0 AND 2", name="ck_gamification_protections"),
    )
    op.create_table(
        "gamification_day",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("meal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("water", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("workout", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_action_bonus", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("return_earned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_gamification_day_user_date"),
    )


def downgrade():
    op.drop_table("gamification_day")
    op.drop_table("gamification_profile")
