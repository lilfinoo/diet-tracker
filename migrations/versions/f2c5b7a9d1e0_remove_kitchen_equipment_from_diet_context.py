"""Remove kitchen_equipment from stored DietPlan generation contexts.

The "O que há na cozinha?" field was replaced by an optional ingredient
selector (available_ingredients). This data migration cleans up the JSON
already persisted in diet_plan.generation_context so the field no longer
leaks into AI suggestions. No schema changes are required.

Revision ID: f2c5b7a9d1e0
Revises: f1b7c3d9e520
"""

from alembic import op
import sqlalchemy as sa


revision = "f2c5b7a9d1e0"
down_revision = "f1b7c3d9e520"
branch_labels = None
depends_on = None


def _clean_context(context):
    if not isinstance(context, dict):
        return context
    keys = [key for key in ("kitchen_equipment", "KITCHEN_EQUIPMENT") if key in context]
    result = dict(context)
    for key in keys:
        result.pop(key, None)
    return result


def _rows():
    metadata = sa.MetaData()
    table = sa.Table("diet_plan", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("generation_context", sa.JSON))
    return table


def upgrade():
    connection = op.get_bind()
    table = _rows()
    for row in connection.execute(sa.select(table.c.id, table.c.generation_context)):
        cleaned = _clean_context(row.generation_context)
        if cleaned != row.generation_context:
            connection.execute(table.update().where(table.c.id == row.id).values(generation_context=cleaned))


def downgrade():
    # Pure data cleanup; nothing to restore.
    pass