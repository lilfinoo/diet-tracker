"""add reviewed exercise media mappings

Revision ID: a9e3d6f4b2c1
Revises: e7a9c2d4f610
"""

from alembic import op
import sqlalchemy as sa


revision = "a9e3d6f4b2c1"
down_revision = "e7a9c2d4f610"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exercise_media_review",
        sa.Column("catalog_key", sa.String(length=80), nullable=False),
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=200), nullable=False),
        sa.Column("provider_equipment", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('approved', 'rejected')", name="ck_exercise_media_review_status"),
        sa.PrimaryKeyConstraint("catalog_key"),
    )


def downgrade():
    op.drop_table("exercise_media_review")
