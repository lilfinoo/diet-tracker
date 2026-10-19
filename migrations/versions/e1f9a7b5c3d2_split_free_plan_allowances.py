"""Allow one free diet and one free workout generation per account."""
from alembic import op
import sqlalchemy as sa

revision = "e1f9a7b5c3d2"
down_revision = "d0e8f6a4c2b1"
branch_labels = None
depends_on = None


def upgrade():
    for kind, table in (("workout", "workout_plan"), ("diet", "diet_plan")):
        column = f"free_{kind}_plan_uses"
        op.add_column("user", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
        # Retained plans identify which allowance an earlier generation consumed.
        op.execute(sa.text(f'''UPDATE "user" SET {column} = 1 WHERE EXISTS
            (SELECT 1 FROM {table} p WHERE p.user_id = "user".id AND p.source = 'ai')'''))


def downgrade():
    op.drop_column("user", "free_diet_plan_uses")
    op.drop_column("user", "free_workout_plan_uses")
