"""derive profile ages from birth year

Revision ID: e3c6a8f1b5d2
Revises: e2b7c4d9f610
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "e3c6a8f1b5d2"
down_revision = "e2b7c4d9f610"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    op.add_column("user_profile", sa.Column("birth_year", sa.Integer(), nullable=True))
    current_year = "CAST(strftime('%Y', 'now') AS INTEGER)" if bind.dialect.name == "sqlite" else "EXTRACT(YEAR FROM CURRENT_DATE)"
    op.execute(sa.text(
        f"UPDATE user_profile SET birth_year = {current_year} - age WHERE age IS NOT NULL"
    ))

    with op.batch_alter_table("professional_student_relationship") as batch_op:
        batch_op.drop_constraint("ck_professional_student_status", type_="check")
        batch_op.create_check_constraint(
            "ck_professional_student_status",
            "status IN ('offline', 'pending', 'active', 'declined', 'revoked', 'expired')",
        )
        batch_op.add_column(sa.Column("student_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("student_profile", sa.JSON(), nullable=True))

    for table_name in ("workout_plan", "diet_plan"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("user_id", existing_type=UUIDType(binary=False), nullable=True)
            batch_op.add_column(sa.Column("professional_student_relationship_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table_name}_professional_student",
                "professional_student_relationship",
                ["professional_student_relationship_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_check_constraint(
                f"ck_{table_name}_owner",
                "(user_id IS NOT NULL AND professional_student_relationship_id IS NULL) OR "
                "(user_id IS NULL AND professional_student_relationship_id IS NOT NULL)",
            )
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade():
    for table_name in ("workout_plan", "diet_plan"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(f"ck_{table_name}_owner", type_="check")
            batch_op.drop_constraint(f"fk_{table_name}_professional_student", type_="foreignkey")
            batch_op.drop_column("professional_student_relationship_id")
            batch_op.alter_column("user_id", existing_type=UUIDType(binary=False), nullable=False)
    with op.batch_alter_table("professional_student_relationship") as batch_op:
        batch_op.drop_column("student_name")
        batch_op.drop_column("student_profile")
        batch_op.drop_constraint("ck_professional_student_status", type_="check")
        batch_op.create_check_constraint(
            "ck_professional_student_status",
            "status IN ('pending', 'active', 'declined', 'revoked', 'expired')",
        )
    op.drop_column("user_profile", "birth_year")
