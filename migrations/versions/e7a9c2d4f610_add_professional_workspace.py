"""add professional workspace

Revision ID: e7a9c2d4f610
Revises: b4936c17e196
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "e7a9c2d4f610"
down_revision = "b4936c17e196"
branch_labels = None
depends_on = None


def _add_plan_lifecycle(table_name):
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(sa.Column("author_user_id", UUIDType(binary=False), nullable=True))
        batch_op.add_column(sa.Column("published_by_user_id", UUIDType(binary=False), nullable=True))
        batch_op.add_column(sa.Column("supersedes_plan_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            f"fk_{table_name}_author_user",
            "user",
            ["author_user_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            f"ck_{table_name}_status",
            "status IN ('draft', 'published', 'archived')",
        )
        batch_op.create_check_constraint(
            f"ck_{table_name}_source",
            "source IN ('manual', 'ai', 'legacy')",
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_published_by_user",
            "user",
            ["published_by_user_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            f"fk_{table_name}_supersedes",
            table_name,
            ["supersedes_plan_id"],
            ["id"],
        )

    op.execute(sa.text(
        f"UPDATE {table_name} SET author_user_id = user_id, status = 'published', "
        "source = 'legacy', published_at = created_at"
    ))

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.alter_column("author_user_id", existing_type=UUIDType(binary=False), nullable=False)
        batch_op.alter_column("status", existing_type=sa.String(length=20), nullable=False)
        batch_op.alter_column("source", existing_type=sa.String(length=20), nullable=False)


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_professional", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    _add_plan_lifecycle("workout_plan")
    _add_plan_lifecycle("diet_plan")

    op.create_table(
        "professional_student_relationship",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("professional_user_id", UUIDType(binary=False), nullable=False),
        sa.Column("student_user_id", UUIDType(binary=False), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=False),
        sa.Column("invite_expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_user_id", UUIDType(binary=False), nullable=True),
        sa.CheckConstraint(
            "student_user_id IS NULL OR professional_user_id != student_user_id",
            name="ck_professional_student_distinct_users",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'declined', 'revoked', 'expired')",
            name="ck_professional_student_status",
        ),
        sa.ForeignKeyConstraint(["professional_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["student_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_token_hash"),
    )
    op.create_index(
        "ix_professional_student_professional_status",
        "professional_student_relationship",
        ["professional_user_id", "status"],
    )
    op.create_index(
        "uq_professional_student_active_student",
        "professional_student_relationship",
        ["student_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "delegated_action_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", UUIDType(binary=False), nullable=False),
        sa.Column("subject_user_id", UUIDType(binary=False), nullable=False),
        sa.Column("relationship_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["subject_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(
            ["relationship_id"],
            ["professional_student_relationship.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_delegated_audit_actor_created",
        "delegated_action_audit",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_delegated_audit_subject_created",
        "delegated_action_audit",
        ["subject_user_id", "created_at"],
    )


def _drop_plan_lifecycle(table_name):
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.drop_constraint(f"ck_{table_name}_source", type_="check")
        batch_op.drop_constraint(f"ck_{table_name}_status", type_="check")
        batch_op.drop_constraint(f"fk_{table_name}_supersedes", type_="foreignkey")
        batch_op.drop_constraint(f"fk_{table_name}_published_by_user", type_="foreignkey")
        batch_op.drop_constraint(f"fk_{table_name}_author_user", type_="foreignkey")
        batch_op.drop_column("published_at")
        batch_op.drop_column("source")
        batch_op.drop_column("status")
        batch_op.drop_column("supersedes_plan_id")
        batch_op.drop_column("published_by_user_id")
        batch_op.drop_column("author_user_id")


def downgrade():
    op.drop_index("ix_delegated_audit_subject_created", table_name="delegated_action_audit")
    op.drop_index("ix_delegated_audit_actor_created", table_name="delegated_action_audit")
    op.drop_table("delegated_action_audit")
    op.drop_index(
        "uq_professional_student_active_student",
        table_name="professional_student_relationship",
    )
    op.drop_index(
        "ix_professional_student_professional_status",
        table_name="professional_student_relationship",
    )
    op.drop_table("professional_student_relationship")
    _drop_plan_lifecycle("diet_plan")
    _drop_plan_lifecycle("workout_plan")
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("is_professional")
