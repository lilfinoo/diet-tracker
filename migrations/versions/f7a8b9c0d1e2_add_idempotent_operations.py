"""store responses for retry-safe client mutations

Revision ID: f7a8b9c0d1e2
Revises: e4f6a8b0c2d4, f4d7a2c8e1b5
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "f7a8b9c0d1e2"
down_revision = ("e4f6a8b0c2d4", "f4d7a2c8e1b5")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "idempotent_operation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_idempotent_operation_user_key"),
    )
    op.create_index(
        "ix_idempotent_operation_user_created",
        "idempotent_operation",
        ["user_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_idempotent_operation_user_created", table_name="idempotent_operation")
    op.drop_table("idempotent_operation")
