"""Add invitation codes and one Premium referral reward per calendar month."""

import secrets

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

revision = "a2c4e6f8b0d1"
down_revision = "f1b2c3d4e5a6"
branch_labels = None
depends_on = None


def upgrade():
    codes = op.create_table(
        "referral_code",
        sa.Column(
            "user_id",
            UUIDType(binary=False),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("code", sa.String(12), nullable=False, unique=True),
    )
    op.create_table(
        "referral",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inviter_user_id",
            UUIDType(binary=False),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitee_user_id",
            UUIDType(binary=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("invitee_user_id", name="uq_referral_invitee"),
        sa.CheckConstraint("inviter_user_id != invitee_user_id", name="ck_referral_distinct_users"),
    )
    op.create_index("ix_referral_inviter_created", "referral", ["inviter_user_id", "created_at"])
    op.create_table(
        "referral_reward",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inviter_user_id",
            UUIDType(binary=False),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("inviter_user_id", "period", name="uq_referral_reward_month"),
    )
    connection = op.get_bind()
    users = sa.table("user", sa.column("id", UUIDType(binary=False)))
    used = set()
    for user_id in connection.execute(sa.select(users.c.id)).scalars():
        code = secrets.token_hex(6).upper()
        while code in used:
            code = secrets.token_hex(6).upper()
        used.add(code)
        connection.execute(codes.insert().values(user_id=user_id, code=code))


def downgrade():
    op.drop_table("referral_reward")
    op.drop_table("referral")
    op.drop_table("referral_code")
