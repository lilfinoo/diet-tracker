"""Add template workout sources and confirmed energy snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "f2a0b8c6d4e1"
down_revision = "a2c4e6f8b0d1"
branch_labels = None
depends_on = None


def _plan_sources(values):
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    # SQLite rebuilds the parent table to change a CHECK. Disable FK cascades
    # outside its transaction so existing workout days/sessions remain intact.
    if sqlite:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("workout_plan") as batch:
            batch.drop_constraint("ck_workout_plan_source", type_="check")
            batch.create_check_constraint("ck_workout_plan_source", f"source IN ({values})")
    finally:
        if sqlite:
            with op.get_context().autocommit_block():
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def upgrade():
    _plan_sources("'manual', 'ai', 'legacy', 'template'")
    op.add_column("workout_session", sa.Column("duration_seconds_confirmed", sa.Integer(), nullable=True))
    op.add_column("workout_session", sa.Column("energy_estimate", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("workout_session", "energy_estimate")
    op.drop_column("workout_session", "duration_seconds_confirmed")
    op.execute("UPDATE workout_plan SET source = 'manual' WHERE source = 'template'")
    _plan_sources("'manual', 'ai', 'legacy'")
