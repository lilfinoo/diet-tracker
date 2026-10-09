"""Store the effective prescription for planned exercise completions.

Revision ID: b7c4d2e9f106
Revises: a1c3e5f7b9d2
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c4d2e9f106"
down_revision = "a1c3e5f7b9d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workout_session_exercise_completion") as batch_op:
        batch_op.add_column(sa.Column("completion_mode", sa.String(length=16), nullable=False, server_default="performed"))
        batch_op.add_column(sa.Column("planned_prescription", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("workout_session_exercise_completion") as batch_op:
        batch_op.drop_column("planned_prescription")
        batch_op.drop_column("completion_mode")
