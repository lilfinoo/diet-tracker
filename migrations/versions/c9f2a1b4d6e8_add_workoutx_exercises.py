"""add WorkoutX exercises

Revision ID: c9f2a1b4d6e8
Revises: d3f8a1c5e7b2
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "c9f2a1b4d6e8"
down_revision = "d3f8a1c5e7b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workoutx_exercise",
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("provider_id"),
    )


def downgrade():
    op.drop_table("workoutx_exercise")
