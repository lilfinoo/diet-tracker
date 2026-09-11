"""add social profiles professional reviews and diet adherence

Revision ID: a4e8c1f7b9d2
Revises: d3f8a1c5e7b2
Create Date: 2026-09-03 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "a4e8c1f7b9d2"
down_revision = "d3f8a1c5e7b2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
        bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_professional_student_relationship")

    with op.batch_alter_table("user_profile") as batch_op:
        batch_op.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("avatar_object_key", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("avatar_updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("accepts_external_workout_reviews", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("accepts_external_diet_reviews", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("workout_plan") as batch_op:
        batch_op.add_column(sa.Column("professional_verified_fingerprint", sa.String(length=64), nullable=True))
    with op.batch_alter_table("diet_plan") as batch_op:
        batch_op.add_column(sa.Column("professional_verified_fingerprint", sa.String(length=64), nullable=True))

    with op.batch_alter_table("profile_highlight") as batch_op:
        batch_op.drop_constraint("ck_profile_highlight_target_present", type_="check")
        batch_op.drop_constraint("ck_profile_highlight_target_kind", type_="check")
        batch_op.add_column(sa.Column("personal_record_event_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_profile_highlight_personal_record_event",
            "personal_record_event",
            ["personal_record_event_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_profile_highlight_user_record", ["user_id", "personal_record_event_id"]
        )
        batch_op.create_check_constraint(
            "ck_profile_highlight_target_present",
            "achievement_unlock_id IS NOT NULL OR user_badge_id IS NOT NULL OR personal_record_event_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_profile_highlight_target_kind",
            "target_kind IN ('achievement', 'badge', 'personal_record')",
        )

    with op.batch_alter_table("professional_student_relationship") as batch_op:
        batch_op.alter_column("invite_token_hash", existing_type=sa.String(length=64), nullable=True)
        batch_op.add_column(sa.Column("initiated_by_user_id", UUIDType(binary=False), nullable=True))
        batch_op.add_column(sa.Column("request_message", sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(
            "fk_professional_relationship_initiated_by",
            "user",
            ["initiated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "uq_professional_student_open_pair",
        "professional_student_relationship",
        ["professional_user_id", "student_user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'active') AND student_user_id IS NOT NULL"),
        sqlite_where=sa.text("status IN ('pending', 'active') AND student_user_id IS NOT NULL"),
    )

    op.create_table(
        "diet_adherence_day",
        sa.Column("id", UUIDType(binary=False), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("diet_plan_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("plan_day", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('in_progress', 'completed')", name="ck_diet_adherence_day_status"),
        sa.CheckConstraint("(status = 'completed' AND completed_at IS NOT NULL) OR (status = 'in_progress' AND completed_at IS NULL)", name="ck_diet_adherence_completion"),
        sa.ForeignKeyConstraint(["diet_plan_id"], ["diet_plan.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_diet_adherence_user_date"),
    )
    op.create_index("ix_diet_adherence_user_date", "diet_adherence_day", ["user_id", "local_date"])
    op.create_table(
        "diet_meal_check_in",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("adherence_day_id", UUIDType(binary=False), nullable=False),
        sa.Column("diet_plan_meal_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'substituted', 'skipped')", name="ck_diet_meal_checkin_status"),
        sa.ForeignKeyConstraint(["adherence_day_id"], ["diet_adherence_day.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["diet_plan_meal_id"], ["diet_plan_meal.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adherence_day_id", "diet_plan_meal_id", name="uq_diet_checkin_day_meal"),
    )

    op.create_table(
        "professional_review_request",
        sa.Column("id", UUIDType(binary=False), nullable=False),
        sa.Column("student_user_id", UUIDType(binary=False), nullable=False),
        sa.Column("requested_professional_user_id", UUIDType(binary=False), nullable=True),
        sa.Column("assigned_professional_user_id", UUIDType(binary=False), nullable=True),
        sa.Column("relationship_id", sa.Integer(), nullable=True),
        sa.Column("plan_type", sa.String(length=16), nullable=False),
        sa.Column("source_workout_plan_id", sa.Integer(), nullable=True),
        sa.Column("source_diet_plan_id", sa.Integer(), nullable=True),
        sa.Column("proposal_workout_plan_id", sa.Integer(), nullable=True),
        sa.Column("proposal_diet_plan_id", sa.Integer(), nullable=True),
        sa.Column("target_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("review_focus", sa.JSON(), nullable=False),
        sa.Column("student_note", sa.String(length=2000), nullable=True),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sharing_consent_version", sa.String(length=64), nullable=False),
        sa.Column("sharing_consented_at", sa.DateTime(), nullable=False),
        sa.Column("proposal_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("evaluation", sa.Text(), nullable=True),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("student_decision", sa.String(length=16), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("plan_type IN ('workout', 'diet')", name="ck_professional_review_plan_type"),
        sa.CheckConstraint("target_mode IN ('linked', 'specific', 'open')", name="ck_professional_review_target_mode"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'in_review', 'completed', 'declined', 'cancelled', 'expired')", name="ck_professional_review_status"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('approved_as_is', 'changes_proposed')", name="ck_professional_review_outcome"),
        sa.CheckConstraint("student_decision IN ('pending', 'applied', 'rejected')", name="ck_professional_review_student_decision"),
        sa.CheckConstraint("(plan_type = 'workout' AND source_workout_plan_id IS NOT NULL AND source_diet_plan_id IS NULL) OR (plan_type = 'diet' AND source_diet_plan_id IS NOT NULL AND source_workout_plan_id IS NULL)", name="ck_professional_review_source_type"),
        sa.CheckConstraint("student_user_id != requested_professional_user_id AND student_user_id != assigned_professional_user_id", name="ck_professional_review_distinct_users"),
        sa.ForeignKeyConstraint(["assigned_professional_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposal_diet_plan_id"], ["diet_plan.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposal_workout_plan_id"], ["workout_plan.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["relationship_id"], ["professional_student_relationship.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_professional_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_diet_plan_id"], ["diet_plan.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_workout_plan_id"], ["workout_plan.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_professional_review_student_status", "professional_review_request", ["student_user_id", "status"])
    op.create_index("ix_professional_review_assigned_status", "professional_review_request", ["assigned_professional_user_id", "status"])
    op.create_index("ix_professional_review_open", "professional_review_request", ["target_mode", "status", "created_at"])
    op.create_index("uq_professional_review_active_workout", "professional_review_request", ["source_workout_plan_id"], unique=True, postgresql_where=sa.text("status IN ('pending', 'accepted', 'in_review')"), sqlite_where=sa.text("status IN ('pending', 'accepted', 'in_review')"))
    op.create_index("uq_professional_review_active_diet", "professional_review_request", ["source_diet_plan_id"], unique=True, postgresql_where=sa.text("status IN ('pending', 'accepted', 'in_review')"), sqlite_where=sa.text("status IN ('pending', 'accepted', 'in_review')"))
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
        bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_professional_student_relationship")

    op.drop_index("uq_professional_review_active_diet", table_name="professional_review_request")
    op.drop_index("uq_professional_review_active_workout", table_name="professional_review_request")
    op.drop_index("ix_professional_review_open", table_name="professional_review_request")
    op.drop_index("ix_professional_review_assigned_status", table_name="professional_review_request")
    op.drop_index("ix_professional_review_student_status", table_name="professional_review_request")
    op.drop_table("professional_review_request")
    op.drop_table("diet_meal_check_in")
    op.drop_index("ix_diet_adherence_user_date", table_name="diet_adherence_day")
    op.drop_table("diet_adherence_day")
    op.drop_index("uq_professional_student_open_pair", table_name="professional_student_relationship")
    op.execute(sa.text(
        "UPDATE delegated_action_audit SET relationship_id = NULL WHERE relationship_id IN "
        "(SELECT id FROM professional_student_relationship WHERE invite_token_hash IS NULL)"
    ))
    op.execute(sa.text("DELETE FROM professional_student_relationship WHERE invite_token_hash IS NULL"))
    with op.batch_alter_table("professional_student_relationship") as batch_op:
        batch_op.drop_constraint("fk_professional_relationship_initiated_by", type_="foreignkey")
        batch_op.drop_column("request_message")
        batch_op.drop_column("initiated_by_user_id")
        batch_op.alter_column("invite_token_hash", existing_type=sa.String(length=64), nullable=False)
    op.execute(sa.text("DELETE FROM profile_highlight WHERE target_kind = 'personal_record'"))
    with op.batch_alter_table("profile_highlight") as batch_op:
        batch_op.drop_constraint("ck_profile_highlight_target_kind", type_="check")
        batch_op.drop_constraint("ck_profile_highlight_target_present", type_="check")
        batch_op.drop_constraint("uq_profile_highlight_user_record", type_="unique")
        batch_op.drop_constraint("fk_profile_highlight_personal_record_event", type_="foreignkey")
        batch_op.drop_column("personal_record_event_id")
        batch_op.create_check_constraint("ck_profile_highlight_target_present", "achievement_unlock_id IS NOT NULL OR user_badge_id IS NOT NULL")
        batch_op.create_check_constraint("ck_profile_highlight_target_kind", "target_kind IN ('achievement', 'badge')")
    with op.batch_alter_table("diet_plan") as batch_op:
        batch_op.drop_column("professional_verified_fingerprint")
    with op.batch_alter_table("workout_plan") as batch_op:
        batch_op.drop_column("professional_verified_fingerprint")
    with op.batch_alter_table("user_profile") as batch_op:
        batch_op.drop_column("accepts_external_diet_reviews")
        batch_op.drop_column("accepts_external_workout_reviews")
        batch_op.drop_column("avatar_updated_at")
        batch_op.drop_column("avatar_object_key")
        batch_op.drop_column("is_public")
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")
