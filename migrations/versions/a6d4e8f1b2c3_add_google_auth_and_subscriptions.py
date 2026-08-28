"""add Google identities, subscriptions, and entitlements

Revision ID: a6d4e8f1b2c3
Revises: e4f6a8b0c2d4
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "a6d4e8f1b2c3"
down_revision = "e4f6a8b0c2d4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        with op.batch_alter_table("user", schema=None) as batch_op:
            batch_op.alter_column(
                "password_hash",
                existing_type=sa.String(length=255),
                nullable=True,
            )
            batch_op.add_column(
                sa.Column("ai_trial_uses", sa.Integer(), nullable=False, server_default="0")
            )
            batch_op.add_column(sa.Column("professional_scope", sa.String(length=16), nullable=True))
            batch_op.create_check_constraint(
                "ck_user_professional_scope",
                "professional_scope IS NULL OR professional_scope IN ('diet', 'workout', 'both')",
            )
            batch_op.create_check_constraint(
                "ck_user_ai_trial_uses_nonnegative",
                "ai_trial_uses >= 0",
            )
    finally:
        if bind.dialect.name == "sqlite":
            op.execute(sa.text("PRAGMA foreign_keys=ON"))

    op.create_table(
        "oauth_identity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "issuer", "subject",
            name="uq_oauth_identity_provider_issuer_subject",
        ),
    )

    op.create_table(
        "subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_customer_id", sa.String(length=255), nullable=True),
        sa.Column("external_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "plan_code IN ('free', 'premium_student', 'professional_single', 'professional_complete')",
            name="ck_subscription_plan_code",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "external_subscription_id",
            name="uq_subscription_provider_external_id",
        ),
    )
    op.create_index(
        "ix_subscription_user_status", "subscription", ["user_id", "status"], unique=False
    )


def downgrade():
    op.drop_index("ix_subscription_user_status", table_name="subscription")
    op.drop_table("subscription")
    op.drop_table("oauth_identity")
    op.execute(sa.text("UPDATE \"user\" SET password_hash = '' WHERE password_hash IS NULL"))
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        with op.batch_alter_table("user", schema=None) as batch_op:
            batch_op.drop_constraint("ck_user_ai_trial_uses_nonnegative", type_="check")
            batch_op.drop_constraint("ck_user_professional_scope", type_="check")
            batch_op.drop_column("professional_scope")
            batch_op.drop_column("ai_trial_uses")
            batch_op.alter_column(
                "password_hash",
                existing_type=sa.String(length=255),
                nullable=False,
            )
    finally:
        if bind.dialect.name == "sqlite":
            op.execute(sa.text("PRAGMA foreign_keys=ON"))
