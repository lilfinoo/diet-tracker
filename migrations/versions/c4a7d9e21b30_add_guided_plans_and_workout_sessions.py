"""Add guided plan fields, workout days and temporary sessions.

Revision ID: c4a7d9e21b30
Revises: 9e8f1c6d2a10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "c4a7d9e21b30"
down_revision = "9e8f1c6d2a10"
branch_labels = None
depends_on = None


def _has_table(name):
    return name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(table, name):
    return any(index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade():
    for temporary_table in (
        "_alembic_tmp_workout_plan",
        "_alembic_tmp_workout_exercise",
        "_alembic_tmp_diet_plan",
        "_alembic_tmp_diet_plan_meal",
    ):
        if _has_table(temporary_table):
            op.drop_table(temporary_table)

    workout_plan_columns = _columns("workout_plan")
    workout_plan_additions = (
        sa.Column("split_type", sa.String(length=32)),
        sa.Column("days_per_week", sa.Integer()),
        sa.Column("goal", sa.String(length=50)),
        sa.Column("experience_level", sa.String(length=20)),
        sa.Column("session_duration", sa.Integer()),
        sa.Column("questionnaire_data", sa.JSON()),
    )
    with op.batch_alter_table("workout_plan") as batch_op:
        for column in workout_plan_additions:
            if column.name not in workout_plan_columns:
                batch_op.add_column(column)

    if not _has_table("workout_day"):
        op.create_table(
            "workout_day",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workout_plan_id", sa.Integer(), sa.ForeignKey("workout_plan.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=100), nullable=False),
            sa.Column("focus", sa.String(length=200)),
            sa.Column("order", sa.Integer(), nullable=False),
            sa.UniqueConstraint("workout_plan_id", "order", name="uq_workout_day_plan_order"),
        )
    if not _has_index("workout_day", "ix_workout_day_plan_order"):
        op.create_index("ix_workout_day_plan_order", "workout_day", ["workout_plan_id", "order"])

    workout_exercise_columns = _columns("workout_exercise")
    workout_exercise_additions = (
        sa.Column("workout_day_id", sa.Integer(), sa.ForeignKey("workout_day.id", name="fk_workout_exercise_day", ondelete="CASCADE")),
        sa.Column("catalog_key", sa.String(length=80)),
        sa.Column("movement_pattern", sa.String(length=50)),
        sa.Column("primary_muscle", sa.String(length=50)),
        sa.Column("equipment", sa.String(length=50)),
        sa.Column("difficulty", sa.String(length=20)),
        sa.Column("rest_seconds", sa.Integer()),
        sa.Column("effort_guidance", sa.String(length=100)),
    )
    with op.batch_alter_table("workout_exercise") as batch_op:
        for column in workout_exercise_additions:
            if column.name not in workout_exercise_columns:
                batch_op.add_column(column)
    if not _has_index("workout_exercise", "ix_workout_exercise_day_order"):
        op.create_index("ix_workout_exercise_day_order", "workout_exercise", ["workout_day_id", "order"])

    bind = op.get_bind()
    metadata = sa.MetaData()
    plan_table = sa.Table("workout_plan", metadata, autoload_with=bind)
    day_table = sa.Table("workout_day", metadata, autoload_with=bind)
    exercise_table = sa.Table("workout_exercise", metadata, autoload_with=bind)
    existing_day_plans = set(bind.execute(sa.select(day_table.c.workout_plan_id)).scalars())
    for plan_id, in bind.execute(sa.select(plan_table.c.id)):
        if plan_id in existing_day_plans:
            continue
        result = bind.execute(day_table.insert().values(
            workout_plan_id=plan_id,
            code="A",
            title="Treino A",
            focus="Plano anterior",
            order=1,
        ))
        day_id = result.inserted_primary_key[0]
        bind.execute(
            exercise_table.update()
            .where(exercise_table.c.workout_plan_id == plan_id)
            .values(workout_day_id=day_id)
        )

    if not _has_table("workout_session"):
        op.create_table(
            "workout_session",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("workout_plan_id", sa.Integer(), sa.ForeignKey("workout_plan.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workout_day_id", sa.Integer(), sa.ForeignKey("workout_day.id", ondelete="CASCADE"), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime()),
        )
    if not _has_index("workout_session", "ix_workout_session_user_active"):
        op.create_index("ix_workout_session_user_active", "workout_session", ["user_id", "completed_at"])

    if not _has_table("workout_session_exercise_override"):
        op.create_table(
            "workout_session_exercise_override",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workout_session_id", sa.Integer(), sa.ForeignKey("workout_session.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workout_exercise_id", sa.Integer(), sa.ForeignKey("workout_exercise.id", ondelete="CASCADE"), nullable=False),
            sa.Column("catalog_key", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("sets", sa.Integer()),
            sa.Column("reps", sa.String(length=50)),
            sa.Column("weight", sa.String(length=50)),
            sa.Column("rest_seconds", sa.Integer()),
            sa.Column("effort_guidance", sa.String(length=100)),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workout_session_id", "workout_exercise_id", name="uq_session_exercise_override"),
        )

    diet_plan_columns = _columns("diet_plan")
    diet_plan_additions = (
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plan_mode", sa.String(length=24)),
        sa.Column("goal_code", sa.String(length=32)),
        sa.Column("meals_per_day", sa.Integer()),
        sa.Column("generation_context", sa.JSON()),
    )
    with op.batch_alter_table("diet_plan") as batch_op:
        for column in diet_plan_additions:
            if column.name not in diet_plan_columns:
                batch_op.add_column(column)

    meal_columns = _columns("diet_plan_meal")
    meal_additions = (
        sa.Column("items", sa.JSON()),
        sa.Column("prep_instructions", sa.Text()),
        sa.Column("prep_minutes", sa.Integer()),
        sa.Column("substitutions", sa.JSON()),
    )
    with op.batch_alter_table("diet_plan_meal") as batch_op:
        for column in meal_additions:
            if column.name not in meal_columns:
                batch_op.add_column(column)


def downgrade():
    with op.batch_alter_table("diet_plan_meal") as batch_op:
        batch_op.drop_column("substitutions")
        batch_op.drop_column("prep_minutes")
        batch_op.drop_column("prep_instructions")
        batch_op.drop_column("items")

    with op.batch_alter_table("diet_plan") as batch_op:
        batch_op.drop_column("generation_context")
        batch_op.drop_column("meals_per_day")
        batch_op.drop_column("goal_code")
        batch_op.drop_column("plan_mode")
        batch_op.drop_column("schema_version")

    op.drop_table("workout_session_exercise_override")
    op.drop_index("ix_workout_session_user_active", table_name="workout_session")
    op.drop_table("workout_session")

    with op.batch_alter_table("workout_exercise") as batch_op:
        batch_op.drop_index("ix_workout_exercise_day_order")
        batch_op.drop_column("effort_guidance")
        batch_op.drop_column("rest_seconds")
        batch_op.drop_column("difficulty")
        batch_op.drop_column("equipment")
        batch_op.drop_column("primary_muscle")
        batch_op.drop_column("movement_pattern")
        batch_op.drop_column("catalog_key")
        batch_op.drop_column("workout_day_id")

    op.drop_index("ix_workout_day_plan_order", table_name="workout_day")
    op.drop_table("workout_day")

    with op.batch_alter_table("workout_plan") as batch_op:
        batch_op.drop_column("questionnaire_data")
        batch_op.drop_column("session_duration")
        batch_op.drop_column("experience_level")
        batch_op.drop_column("goal")
        batch_op.drop_column("days_per_week")
        batch_op.drop_column("split_type")
