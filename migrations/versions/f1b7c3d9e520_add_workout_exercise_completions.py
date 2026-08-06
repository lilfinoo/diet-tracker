"""add workout exercise completions

Revision ID: f1b7c3d9e520
Revises: d8f2c6a41e70
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision = "f1b7c3d9e520"
down_revision = "d8f2c6a41e70"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_workout_session_user_active", table_name="workout_session")
    op.execute(sa.text("""
        UPDATE workout_session
        SET completed_at = started_at
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id
                           ORDER BY started_at DESC, id DESC
                       ) AS active_order
                FROM workout_session
                WHERE completed_at IS NULL
            ) ranked_sessions
            WHERE active_order > 1
        )
    """))
    op.create_index(
        "ix_workout_session_user_active",
        "workout_session",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("completed_at IS NULL"),
        sqlite_where=sa.text("completed_at IS NULL"),
    )
    op.create_table(
        "workout_session_exercise_completion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workout_session_id", sa.Integer(), nullable=False),
        sa.Column("workout_exercise_id", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workout_exercise_id"],
            ["workout_exercise.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"],
            ["workout_session.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_session_id",
            "workout_exercise_id",
            name="uq_session_exercise_completion",
        ),
    )


def downgrade():
    op.drop_table("workout_session_exercise_completion")
    op.drop_index("ix_workout_session_user_active", table_name="workout_session")
    op.create_index(
        "ix_workout_session_user_active",
        "workout_session",
        ["user_id", "completed_at"],
        unique=False,
    )
