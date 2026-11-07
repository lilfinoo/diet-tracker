"""Allow two professional links and record student plan decisions."""
from alembic import op
import sqlalchemy as sa

revision = "c8e3a1d5f902"
down_revision = "da71c4b83920"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("uq_professional_student_active_student", table_name="professional_student_relationship")
    for table in ("workout_plan", "diet_plan"):
        op.add_column(table, sa.Column("student_accepted_at", sa.DateTime(), nullable=True))
        op.add_column(table, sa.Column("student_declined_at", sa.DateTime(), nullable=True))
    # Existing active plans were selected explicitly by their owners.
    for table, field in (("workout_plan", "current_workout_plan_id"), ("diet_plan", "current_diet_plan_id")):
        op.execute(sa.text(f"UPDATE {table} SET student_accepted_at = CURRENT_TIMESTAMP WHERE id IN (SELECT {field} FROM user_profile WHERE {field} IS NOT NULL)"))

    op.execute(sa.text("UPDATE workout_plan SET student_accepted_at = CURRENT_TIMESTAMP "
                       "WHERE student_accepted_at IS NULL AND (id IN "
                       "(SELECT pending_workout_plan_id FROM user_profile WHERE pending_workout_plan_id IS NOT NULL) "
                       "OR id IN (SELECT workout_plan_id FROM workout_session WHERE workout_plan_id IS NOT NULL))"))


def downgrade():
    bind = op.get_bind()
    duplicates = bind.execute(sa.text("SELECT student_user_id FROM professional_student_relationship WHERE status = 'active' GROUP BY student_user_id HAVING COUNT(*) > 1")).first()
    if duplicates:
        raise RuntimeError("Encerre vínculos adicionais antes de restaurar o limite de um profissional.")
    for table in ("workout_plan", "diet_plan"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("student_declined_at")
            batch.drop_column("student_accepted_at")
    op.create_index("uq_professional_student_active_student", "professional_student_relationship", ["student_user_id"], unique=True,
                    postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
