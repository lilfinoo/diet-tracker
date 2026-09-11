"""add daily diet state

Revision ID: f4d7a2c8e1b5
Revises: b6e1f3a9c2d4, c9f2a1b4d6e8
Create Date: 2026-09-07 12:00:00.000000
"""

import re
import unicodedata

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "f4d7a2c8e1b5"
down_revision = ("b6e1f3a9c2d4", "c9f2a1b4d6e8")
branch_labels = None
depends_on = None


def _normalized(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).lower().split())


def _slot_key(meal_type, order):
    label = _normalized(meal_type)
    if "cafe" in label and "manha" in label:
        return "breakfast"
    if "almoco" in label:
        return "lunch"
    if "jantar" in label:
        return "dinner"
    if "ceia" in label:
        return "supper"
    if "lanche" in label:
        base = "snack"
        if "manha" in label:
            base = "morning_snack"
        elif "tarde" in label:
            base = "afternoon_snack"
        elif "noite" in label:
            base = "evening_snack"
        return f"{base}_{int(order)}" if order is not None else base
    return (re.sub(r"[^a-z0-9]+", "_", label).strip("_") or "meal")[:64]


def upgrade():
    with op.batch_alter_table("diet_plan_meal") as batch_op:
        batch_op.add_column(sa.Column("slot_key", sa.String(length=64), nullable=True))

    meal = sa.table(
        "diet_plan_meal",
        sa.column("id", sa.Integer()),
        sa.column("diet_plan_id", sa.Integer()),
        sa.column("day_of_week", sa.String()),
        sa.column("meal_type", sa.String()),
        sa.column("order", sa.Integer()),
        sa.column("slot_key", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(
        meal.c.id,
        meal.c.diet_plan_id,
        meal.c.day_of_week,
        meal.c.meal_type,
        meal.c.order,
    ).order_by(meal.c.diet_plan_id, meal.c.day_of_week, meal.c.order, meal.c.id)).all()
    positions = {}
    for row in rows:
        group = (row.diet_plan_id, row.day_of_week)
        positions[group] = positions.get(group, 0) + 1
        structural_order = row.order if row.order is not None else positions[group]
        connection.execute(
            meal.update().where(meal.c.id == row.id).values(slot_key=_slot_key(row.meal_type, structural_order))
        )

    with op.batch_alter_table("diet_plan_meal") as batch_op:
        batch_op.alter_column("slot_key", existing_type=sa.String(length=64), nullable=False)

    op.create_table(
        "diet_meal_daily_state",
        sa.Column("id", UUIDType(binary=False), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("slot_key", sa.String(length=64), nullable=False),
        sa.Column("diet_plan_id", sa.Integer(), nullable=False),
        sa.Column("selected_plan_meal_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("planned_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "result IN ('pending', 'consumed_planned', 'consumed_different', 'skipped')",
            name="ck_diet_daily_state_result",
        ),
        sa.ForeignKeyConstraint(["diet_plan_id"], ["diet_plan.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["selected_plan_meal_id"], ["diet_plan_meal.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "local_date", "slot_key", name="uq_diet_daily_state_user_date_slot"),
    )
    op.create_index(
        "ix_diet_daily_state_user_date",
        "diet_meal_daily_state",
        ["user_id", "local_date"],
    )

    with op.batch_alter_table("diet_entry") as batch_op:
        batch_op.add_column(sa.Column("daily_meal_state_id", UUIDType(binary=False), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=16), nullable=True))
        batch_op.create_foreign_key(
            "fk_diet_entry_daily_meal_state",
            "diet_meal_daily_state",
            ["daily_meal_state_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint("uq_diet_entry_daily_meal_state", ["daily_meal_state_id"])
        batch_op.create_check_constraint(
            "ck_diet_entry_source",
            "source IS NULL OR source IN ('planned', 'different', 'manual')",
        )


def downgrade():
    with op.batch_alter_table("diet_entry") as batch_op:
        batch_op.drop_constraint("ck_diet_entry_source", type_="check")
        batch_op.drop_constraint("uq_diet_entry_daily_meal_state", type_="unique")
        batch_op.drop_constraint("fk_diet_entry_daily_meal_state", type_="foreignkey")
        batch_op.drop_column("source")
        batch_op.drop_column("daily_meal_state_id")

    op.drop_index("ix_diet_daily_state_user_date", table_name="diet_meal_daily_state")
    op.drop_table("diet_meal_daily_state")
    with op.batch_alter_table("diet_plan_meal") as batch_op:
        batch_op.drop_column("slot_key")
