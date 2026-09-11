"""add durable ai tasks

Revision ID: d3f8a1c5e7b2
Revises: e9b4c6d8a2f1
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "d3f8a1c5e7b2"
down_revision = "e9b4c6d8a2f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_task",
        sa.Column("id", UUIDType(binary=False), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("operation", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("request_image_data", sa.LargeBinary(), nullable=True),
        sa.Column("request_image_mime_type", sa.String(length=32), nullable=True),
        sa.Column("route_params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_ai_task_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_task_user_created", "ai_task", ["user_id", "created_at"])
    op.create_index("ix_ai_task_status_created", "ai_task", ["status", "created_at"])

    for table in ("chat_message", "workout_plan", "diet_plan"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("ai_task_id", UUIDType(binary=False), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table}_ai_task_id", "ai_task", ["ai_task_id"], ["id"], ondelete="SET NULL"
            )
            batch_op.create_unique_constraint(f"uq_{table}_ai_task_id", ["ai_task_id"])


def downgrade():
    for table in ("diet_plan", "workout_plan", "chat_message"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"uq_{table}_ai_task_id", type_="unique")
            batch_op.drop_constraint(f"fk_{table}_ai_task_id", type_="foreignkey")
            batch_op.drop_column("ai_task_id")

    op.drop_index("ix_ai_task_status_created", table_name="ai_task")
    op.drop_index("ix_ai_task_user_created", table_name="ai_task")
    op.drop_table("ai_task")
