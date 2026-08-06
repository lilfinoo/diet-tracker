"""Add plan tables and indexes used by filtered history queries.

Revision ID: 9e8f1c6d2a10
Revises: 4942b33c3674
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "9e8f1c6d2a10"
down_revision = "4942b33c3674"
branch_labels = None
depends_on = None


def _has_table(name):
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table, name):
    return any(index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade():
    if not _has_table("workout_plan"):
        op.create_table("workout_plan", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id"), nullable=False), sa.Column("title", sa.String(length=100), nullable=False), sa.Column("description", sa.Text()), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()))
    if not _has_table("workout_exercise"):
        op.create_table("workout_exercise", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("workout_plan_id", sa.Integer(), sa.ForeignKey("workout_plan.id"), nullable=False), sa.Column("name", sa.String(length=100), nullable=False), sa.Column("sets", sa.Integer()), sa.Column("reps", sa.String(length=50)), sa.Column("weight", sa.String(length=50)), sa.Column("notes", sa.Text()), sa.Column("order", sa.Integer()))
    if not _has_table("diet_plan"):
        op.create_table("diet_plan", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id"), nullable=False), sa.Column("title", sa.String(length=100), nullable=False), sa.Column("description", sa.Text()), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()))
    if not _has_table("diet_plan_meal"):
        op.create_table("diet_plan_meal", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("diet_plan_id", sa.Integer(), sa.ForeignKey("diet_plan.id"), nullable=False), sa.Column("day_of_week", sa.String(length=20)), sa.Column("meal_type", sa.String(length=50), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("calories", sa.Float()), sa.Column("protein", sa.Float()), sa.Column("carbs", sa.Float()), sa.Column("fat", sa.Float()), sa.Column("notes", sa.Text()), sa.Column("order", sa.Integer()))

    indexes = (("diet_entry", "ix_diet_entry_user_date", ["user_id", "date"]), ("measurement", "ix_measurement_user_date", ["user_id", "date"]), ("chat_message", "ix_chat_message_user_created_at", ["user_id", "created_at"]), ("diet_plan", "ix_diet_plan_user_created_at", ["user_id", "created_at"]), ("workout_plan", "ix_workout_plan_user_created_at", ["user_id", "created_at"]))
    for table, name, columns in indexes:
        if _has_table(table) and not _has_index(table, name):
            op.create_index(name, table, columns)


def downgrade():
    for table, name in (("workout_plan", "ix_workout_plan_user_created_at"), ("diet_plan", "ix_diet_plan_user_created_at"), ("chat_message", "ix_chat_message_user_created_at"), ("measurement", "ix_measurement_user_date"), ("diet_entry", "ix_diet_entry_user_date")):
        if _has_table(table) and _has_index(table, name):
            op.drop_index(name, table_name=table)
