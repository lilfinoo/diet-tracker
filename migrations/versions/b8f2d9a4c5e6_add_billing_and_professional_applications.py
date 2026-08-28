"""add billing checkouts, webhook events, and professional applications

Revision ID: b8f2d9a4c5e6
Revises: a6d4e8f1b2c3
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "b8f2d9a4c5e6"
down_revision = "a6d4e8f1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_checkout",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_checkout_id", sa.String(length=255), nullable=True),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("payment_method", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "external_checkout_id",
            name="uq_billing_checkout_provider_external_id",
        ),
    )
    op.create_index("ix_billing_checkout_user", "billing_checkout", ["user_id"], unique=False)

    op.create_table(
        "billing_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_billing_event_provider_event_id"),
    )

    op.create_table(
        "professional_application",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("profession", sa.String(length=20), nullable=False),
        sa.Column("registration_number", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("admin_note", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by_user_id", UUIDType(binary=False), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "profession IN ('personal_trainer', 'nutritionist')",
            name="ck_professional_application_profession",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_professional_application_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("professional_application")
    op.drop_table("billing_event")
    op.drop_index("ix_billing_checkout_user", table_name="billing_checkout")
    op.drop_table("billing_checkout")
