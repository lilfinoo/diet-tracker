import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_migration_preserves_existing_workouts_and_foreign_keys():
    path = Path(__file__).parents[1] / "migrations/versions/f2a0b8c6d4e1_add_water_and_workout_energy.py"
    spec = importlib.util.spec_from_file_location("water_energy_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql('CREATE TABLE "user" (id CHAR(32) PRIMARY KEY)')
        connection.exec_driver_sql('CREATE TABLE user_profile (id INTEGER PRIMARY KEY, user_id CHAR(32) REFERENCES "user"(id))')
        connection.exec_driver_sql("CREATE TABLE workout_plan (id INTEGER PRIMARY KEY, source VARCHAR(20), CONSTRAINT ck_workout_plan_source CHECK (source IN ('manual', 'ai', 'legacy')))")
        connection.exec_driver_sql('CREATE TABLE workout_day (id INTEGER PRIMARY KEY, workout_plan_id INTEGER REFERENCES workout_plan(id) ON DELETE CASCADE)')
        connection.exec_driver_sql('CREATE TABLE workout_session (id INTEGER PRIMARY KEY, workout_plan_id INTEGER REFERENCES workout_plan(id) ON DELETE CASCADE)')
        connection.exec_driver_sql("INSERT INTO workout_plan VALUES (1, 'ai')")
        connection.exec_driver_sql("INSERT INTO workout_day VALUES (1, 1)")
        connection.exec_driver_sql("INSERT INTO workout_session VALUES (1, 1)")
        connection.commit()
        context = MigrationContext.configure(connection, opts={"transactional_ddl": True})
        migration.op = Operations(context)
        with context.begin_transaction():
            migration.upgrade()
        assert connection.exec_driver_sql("SELECT count(*) FROM workout_session").scalar() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM workout_day").scalar() == 1
        connection.exec_driver_sql("INSERT INTO workout_plan VALUES (2, 'template')")
        connection.commit()
        with context.begin_transaction():
            migration.downgrade()
        assert connection.exec_driver_sql("SELECT source FROM workout_plan WHERE id=2").scalar() == "manual"
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
