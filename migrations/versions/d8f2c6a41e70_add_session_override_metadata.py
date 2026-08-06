"""Add exercise metadata to temporary session overrides.

Revision ID: d8f2c6a41e70
Revises: c4a7d9e21b30
"""

from alembic import op
import sqlalchemy as sa


revision = "d8f2c6a41e70"
down_revision = "c4a7d9e21b30"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workout_session_exercise_override") as batch_op:
        batch_op.add_column(sa.Column("movement_pattern", sa.String(length=50)))
        batch_op.add_column(sa.Column("primary_muscle", sa.String(length=50)))
        batch_op.add_column(sa.Column("equipment", sa.String(length=50)))
        batch_op.add_column(sa.Column("difficulty", sa.String(length=20)))


def downgrade():
    with op.batch_alter_table("workout_session_exercise_override") as batch_op:
        batch_op.drop_column("difficulty")
        batch_op.drop_column("equipment")
        batch_op.drop_column("primary_muscle")
        batch_op.drop_column("movement_pattern")
