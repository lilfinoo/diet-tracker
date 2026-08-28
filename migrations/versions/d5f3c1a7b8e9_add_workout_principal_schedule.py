"""add workout principal schedule

Revision ID: d5f3c1a7b8e9
Revises: b8f2d9a4c5e6
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa


revision = "d5f3c1a7b8e9"
down_revision = "b8f2d9a4c5e6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_profile") as batch_op:
        batch_op.add_column(sa.Column("current_workout_plan_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("current_workout_schedule", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("pending_workout_plan_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("pending_workout_schedule", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("workout_schedule_effective_from", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("workout_schedule_timezone", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_profile_current_workout_plan_id_workout_plan",
            "workout_plan",
            ["current_workout_plan_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_user_profile_pending_workout_plan_id_workout_plan",
            "workout_plan",
            ["pending_workout_plan_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("user_profile") as batch_op:
        batch_op.drop_constraint("fk_user_profile_pending_workout_plan_id_workout_plan", type_="foreignkey")
        batch_op.drop_constraint("fk_user_profile_current_workout_plan_id_workout_plan", type_="foreignkey")
        batch_op.drop_column("workout_schedule_timezone")
        batch_op.drop_column("workout_schedule_effective_from")
        batch_op.drop_column("pending_workout_schedule")
        batch_op.drop_column("pending_workout_plan_id")
        batch_op.drop_column("current_workout_schedule")
        batch_op.drop_column("current_workout_plan_id")
