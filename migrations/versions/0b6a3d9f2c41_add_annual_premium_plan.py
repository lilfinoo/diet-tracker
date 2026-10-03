"""allow annual premium subscriptions

Revision ID: 0b6a3d9f2c41
Revises: f7a8b9c0d1e2
Create Date: 2026-10-03
"""

from alembic import op


revision = "0b6a3d9f2c41"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subscription", schema=None) as batch_op:
        batch_op.drop_constraint("ck_subscription_plan_code", type_="check")
        batch_op.create_check_constraint(
            "ck_subscription_plan_code",
            "plan_code IN ('free', 'premium_student', 'premium_student_annual', "
            "'professional_single', 'professional_complete')",
        )


def downgrade():
    with op.batch_alter_table("subscription", schema=None) as batch_op:
        batch_op.drop_constraint("ck_subscription_plan_code", type_="check")
        batch_op.create_check_constraint(
            "ck_subscription_plan_code",
            "plan_code IN ('free', 'premium_student', 'professional_single', 'professional_complete')",
        )
