"""add current diet plan

Revision ID: b2d8f6e4c1a3
Revises: a1c7e5d9b3f2
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "b2d8f6e4c1a3"
down_revision = "a1c7e5d9b3f2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.add_column(sa.Column("current_diet_plan_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_profile_current_diet_plan_id",
            "diet_plan",
            ["current_diet_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.drop_constraint("fk_user_profile_current_diet_plan_id", type_="foreignkey")
        batch_op.drop_column("current_diet_plan_id")
