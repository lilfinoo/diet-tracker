"""Add idempotent records for value-based gamification rewards."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "da71c4b83920"
down_revision = "c1d8f4a6b2e9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("gamification_profile", sa.Column("last_diet_plan_xp_at", sa.DateTime(), nullable=True))
    op.add_column("gamification_profile", sa.Column("last_workout_plan_xp_at", sa.DateTime(), nullable=True))
    op.add_column("gamification_day", sa.Column("rest_checkin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "gamification_award",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "action", "source_key", name="uq_gamification_award_source"),
    )
    op.create_index("ix_gamification_award_user_date", "gamification_award", ["user_id", "local_date"])


def downgrade():
    op.drop_index("ix_gamification_award_user_date", table_name="gamification_award")
    op.drop_table("gamification_award")
    op.drop_column("gamification_day", "rest_checkin")
    op.drop_column("gamification_profile", "last_workout_plan_xp_at")
    op.drop_column("gamification_profile", "last_diet_plan_xp_at")
