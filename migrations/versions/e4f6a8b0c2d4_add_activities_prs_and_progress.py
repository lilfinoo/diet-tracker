"""add activities prs and progress

Revision ID: e4f6a8b0c2d4
Revises: c2d4e6f8a1b3
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "e4f6a8b0c2d4"
down_revision = "c2d4e6f8a1b3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_profile") as batch_op:
        batch_op.add_column(sa.Column("timezone", sa.String(length=64), nullable=True))

    with op.batch_alter_table("workout_session") as batch_op:
        batch_op.add_column(sa.Column("completed_timezone", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("completed_local_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("completed_week_start", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("pr_processed_version", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_workout_session_user_completed",
            ["user_id", "completed_at", "id"],
            unique=False,
        )

    with op.batch_alter_table("workout_set_performance") as batch_op:
        batch_op.add_column(
            sa.Column("is_warmup", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        "personal_record_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("exercise_key", sa.String(length=80), nullable=False),
        sa.Column("exercise_name", sa.String(length=100), nullable=False),
        sa.Column("workout_session_id", sa.Integer(), nullable=False),
        sa.Column("completion_id", sa.Integer(), nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=24), nullable=False),
        sa.Column("metric_key", sa.String(length=80), nullable=False),
        sa.Column("previous_value", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("new_value", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("previous_load_kg", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("previous_repetitions", sa.Integer(), nullable=True),
        sa.Column("load_kg", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("formula", sa.String(length=20), nullable=True),
        sa.Column("formula_version", sa.Integer(), nullable=True),
        sa.Column("is_initial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_highlighted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_backfilled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("achieved_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "metric_type IN ('max_load', 'estimated_1rm', 'reps_at_load')",
            name="ck_pr_event_metric_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workout_session_id"], ["workout_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completion_id"], ["workout_session_exercise_completion.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["set_id"], ["workout_set_performance.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_session_id",
            "exercise_key",
            "metric_key",
            name="uq_pr_event_session_exercise_metric",
        ),
    )
    op.create_index(
        "ix_pr_event_user_exercise_date",
        "personal_record_event",
        ["user_id", "exercise_key", "achieved_at"],
    )
    op.create_index("ix_pr_event_session", "personal_record_event", ["workout_session_id"])

    op.create_table(
        "workout_weekly_goal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("target_sessions", sa.Integer(), nullable=False),
        sa.Column("effective_week_start", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("target_sessions BETWEEN 1 AND 14", name="ck_weekly_goal_target"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "effective_week_start", name="uq_weekly_goal_user_week"),
    )
    op.create_index(
        "ix_weekly_goal_user_effective",
        "workout_weekly_goal",
        ["user_id", "effective_week_start"],
    )

    op.create_table(
        "exercise_goal",
        sa.Column("id", UUIDType(binary=False), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("exercise_key", sa.String(length=80), nullable=False),
        sa.Column("exercise_name", sa.String(length=100), nullable=False),
        sa.Column("target_load_kg", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(), nullable=True),
        sa.Column("achieved_session_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('active', 'achieved', 'cancelled')", name="ck_exercise_goal_status"),
        sa.CheckConstraint("target_load_kg > 0", name="ck_exercise_goal_target_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["achieved_session_id"], ["workout_session.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_exercise_goal_user_active",
        "exercise_goal",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "achievement_unlock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("achievement_code", sa.String(length=40), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(), nullable=False),
        sa.Column("workout_session_id", sa.Integer(), nullable=True),
        sa.Column("exercise_goal_id", UUIDType(binary=False), nullable=True),
        sa.Column("is_backfilled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workout_session_id"], ["workout_session.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exercise_goal_id"], ["exercise_goal.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "achievement_code", name="uq_achievement_unlock_user_code"),
    )
    op.create_index(
        "ix_achievement_unlock_user_date",
        "achievement_unlock",
        ["user_id", "unlocked_at"],
    )


def downgrade():
    op.drop_index("ix_achievement_unlock_user_date", table_name="achievement_unlock")
    op.drop_table("achievement_unlock")
    op.drop_index("uq_exercise_goal_user_active", table_name="exercise_goal")
    op.drop_table("exercise_goal")
    op.drop_index("ix_weekly_goal_user_effective", table_name="workout_weekly_goal")
    op.drop_table("workout_weekly_goal")
    op.drop_index("ix_pr_event_session", table_name="personal_record_event")
    op.drop_index("ix_pr_event_user_exercise_date", table_name="personal_record_event")
    op.drop_table("personal_record_event")
    with op.batch_alter_table("workout_set_performance") as batch_op:
        batch_op.drop_column("is_warmup")
    with op.batch_alter_table("workout_session") as batch_op:
        batch_op.drop_index("ix_workout_session_user_completed")
        batch_op.drop_column("completed_week_start")
        batch_op.drop_column("pr_processed_version")
        batch_op.drop_column("completed_local_date")
        batch_op.drop_column("completed_timezone")
    with op.batch_alter_table("user_profile") as batch_op:
        batch_op.drop_column("timezone")
