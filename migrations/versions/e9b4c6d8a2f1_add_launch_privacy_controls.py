"""add launch privacy controls

Revision ID: e9b4c6d8a2f1
Revises: c7e4a9d2f5b1
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "e9b4c6d8a2f1"
down_revision = "c7e4a9d2f5b1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite recreates tables for nullable changes. Existing audit rows otherwise
        # prevent the parent relationship table from being dropped during the copy.
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
        bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_professional_student_relationship")

    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("user")}
    new_user_columns = (
        sa.Column("terms_version", sa.String(length=40), nullable=True),
        sa.Column("terms_accepted_at", sa.DateTime(), nullable=True),
        sa.Column("privacy_version", sa.String(length=40), nullable=True),
        sa.Column("privacy_accepted_at", sa.DateTime(), nullable=True),
        sa.Column("ai_consent_version", sa.String(length=40), nullable=True),
        sa.Column("ai_consent_at", sa.DateTime(), nullable=True),
    )
    missing_user_columns = [column for column in new_user_columns if column.name not in user_columns]
    if missing_user_columns:
        with op.batch_alter_table("user", schema=None) as batch_op:
            for column in missing_user_columns:
                batch_op.add_column(column)

    inspector = sa.inspect(bind)
    if "consent_record" not in inspector.get_table_names():
        op.create_table(
            "consent_record",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", UUIDType(binary=False), nullable=False),
            sa.Column("document_type", sa.String(length=16), nullable=False),
            sa.Column("version", sa.String(length=40), nullable=False),
            sa.Column("granted", sa.Boolean(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "document_type IN ('terms', 'privacy', 'ai')",
                name="ck_consent_record_document_type",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        )
    inspector = sa.inspect(bind)
    consent_indexes = {index["name"] for index in inspector.get_indexes("consent_record")}
    if "ix_consent_record_user_created" not in consent_indexes:
        op.create_index(
            "ix_consent_record_user_created", "consent_record", ["user_id", "created_at"]
        )

    inspector = sa.inspect(bind)
    relationship_columns = {
        column["name"]: column
        for column in inspector.get_columns("professional_student_relationship")
    }
    relationship_needs_change = (
        "data_sharing_consent_version" not in relationship_columns
        or "data_sharing_consented_at" not in relationship_columns
        or not relationship_columns["professional_user_id"]["nullable"]
    )
    if relationship_needs_change:
        with op.batch_alter_table("professional_student_relationship", schema=None) as batch_op:
            if "data_sharing_consent_version" not in relationship_columns:
                batch_op.add_column(sa.Column("data_sharing_consent_version", sa.String(length=40), nullable=True))
            if "data_sharing_consented_at" not in relationship_columns:
                batch_op.add_column(sa.Column("data_sharing_consented_at", sa.DateTime(), nullable=True))
            if not relationship_columns["professional_user_id"]["nullable"]:
                batch_op.alter_column(
                    "professional_user_id", existing_type=UUIDType(binary=False), nullable=True
                )

    for table_name, column_names in (
        ("delegated_action_audit", ("actor_user_id", "subject_user_id")),
        ("subscription", ("user_id",)),
        ("billing_checkout", ("user_id",)),
    ):
        columns = {column["name"]: column for column in sa.inspect(bind).get_columns(table_name)}
        required_changes = [name for name in column_names if not columns[name]["nullable"]]
        if required_changes:
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                for column_name in required_changes:
                    batch_op.alter_column(
                        column_name, existing_type=UUIDType(binary=False), nullable=True
                    )

    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade():
    op.execute(sa.text("DELETE FROM billing_checkout WHERE user_id IS NULL"))
    op.execute(sa.text("DELETE FROM subscription WHERE user_id IS NULL"))
    op.execute(sa.text(
        "DELETE FROM delegated_action_audit WHERE actor_user_id IS NULL OR subject_user_id IS NULL"
    ))
    op.execute(sa.text(
        "DELETE FROM professional_student_relationship WHERE professional_user_id IS NULL"
    ))

    with op.batch_alter_table("billing_checkout", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=UUIDType(binary=False), nullable=False)
    with op.batch_alter_table("subscription", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=UUIDType(binary=False), nullable=False)
    with op.batch_alter_table("delegated_action_audit", schema=None) as batch_op:
        batch_op.alter_column("subject_user_id", existing_type=UUIDType(binary=False), nullable=False)
        batch_op.alter_column("actor_user_id", existing_type=UUIDType(binary=False), nullable=False)
    with op.batch_alter_table("professional_student_relationship", schema=None) as batch_op:
        batch_op.alter_column(
            "professional_user_id", existing_type=UUIDType(binary=False), nullable=False
        )
        batch_op.drop_column("data_sharing_consented_at")
        batch_op.drop_column("data_sharing_consent_version")

    op.drop_index("ix_consent_record_user_created", table_name="consent_record")
    op.drop_table("consent_record")
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("ai_consent_at")
        batch_op.drop_column("ai_consent_version")
        batch_op.drop_column("privacy_accepted_at")
        batch_op.drop_column("privacy_version")
        batch_op.drop_column("terms_accepted_at")
        batch_op.drop_column("terms_version")
