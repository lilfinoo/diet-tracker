"""persist WorkoutX GIF cache in the application database

Revision ID: e2b7c4d9f610
Revises: f7a8b9c0d1e2
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa


revision = "e2b7c4d9f610"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workoutx_gif",
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("cached_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("provider_id"),
    )


def downgrade():
    op.drop_table("workoutx_gif")
