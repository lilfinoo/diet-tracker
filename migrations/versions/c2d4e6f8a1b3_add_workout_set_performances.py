"""add workout set performances

Revision ID: c2d4e6f8a1b3
Revises: a9e3d6f4b2c1
"""

from alembic import op
import sqlalchemy as sa


revision = "c2d4e6f8a1b3"
down_revision = "a9e3d6f4b2c1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workout_session_exercise_completion") as batch_op:
        batch_op.add_column(sa.Column("exercise_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("exercise_catalog_key", sa.String(length=80), nullable=True))

    op.create_table(
        "workout_set_performance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("completion_id", sa.Integer(), nullable=False),
        sa.Column("set_order", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("load_kg", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("set_order > 0", name="ck_workout_set_order_positive"),
        sa.CheckConstraint("repetitions > 0", name="ck_workout_set_repetitions_positive"),
        sa.CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="ck_workout_set_load_nonnegative"),
        sa.ForeignKeyConstraint(
            ["completion_id"],
            ["workout_session_exercise_completion.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("completion_id", "set_order", name="uq_workout_set_completion_order"),
    )


def downgrade():
    op.drop_table("workout_set_performance")
    with op.batch_alter_table("workout_session_exercise_completion") as batch_op:
        batch_op.drop_column("exercise_catalog_key")
        batch_op.drop_column("exercise_name")
