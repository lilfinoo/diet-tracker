"""persist workout session drafts

Revision ID: a1c7e5d9b3f2
Revises: f6a9c2e4b7d1
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "a1c7e5d9b3f2"
down_revision = "f6a9c2e4b7d1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workout_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("draft_sets", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("workout_session", schema=None) as batch_op:
        batch_op.drop_column("draft_sets")
