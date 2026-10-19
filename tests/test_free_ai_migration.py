import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_upgrade_existing_accounts_preserves_foreign_keys_and_backfills_only_ai_plans():
    migration_path = Path(__file__).parents[1] / "migrations/versions/c8d5e3f1a207_add_lifetime_free_ai_allowances.py"
    spec = importlib.util.spec_from_file_location("free_ai_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql('CREATE TABLE "user" (id TEXT PRIMARY KEY, ai_trial_uses INTEGER NOT NULL DEFAULT 0)')
        for table in ("workout_plan", "diet_plan"):
            connection.exec_driver_sql(f'CREATE TABLE {table} (user_id TEXT NOT NULL REFERENCES "user"(id), source TEXT NOT NULL)')
        for user in ("workout", "diet", "manual", "unclassified"):
            connection.execute(sa.text('INSERT INTO "user" (id, ai_trial_uses) VALUES (:id, 3)'), {"id": user})
        connection.exec_driver_sql("INSERT INTO workout_plan VALUES ('workout', 'ai'), ('manual', 'manual')")
        connection.exec_driver_sql("INSERT INTO diet_plan VALUES ('diet', 'ai')")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.exec_driver_sql('SELECT id, free_plan_uses, free_photo_uses FROM "user"').all()
        assert {name: (plans, photos) for name, plans, photos in rows} == {
            "workout": (1, 0), "diet": (1, 0), "manual": (0, 0), "unclassified": (0, 0),
        }
        migration.downgrade()
        migration.upgrade()
        assert connection.exec_driver_sql('SELECT count(*) FROM workout_plan').scalar() == 2
        assert connection.exec_driver_sql('SELECT count(*) FROM diet_plan').scalar() == 1
    engine.dispose()


def test_split_allowances_preserve_type_and_photo_consumption():
    migration_path = Path(__file__).parents[1] / "migrations/versions/e1f9a7b5c3d2_split_free_plan_allowances.py"
    spec = importlib.util.spec_from_file_location("split_free_ai_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE "user" (id TEXT PRIMARY KEY, free_plan_uses INTEGER DEFAULT 1, free_photo_uses INTEGER DEFAULT 2)')
        for table in ("workout_plan", "diet_plan"):
            connection.exec_driver_sql(f'CREATE TABLE {table} (user_id TEXT, source TEXT)')
        for name in ("workout", "diet", "manual", "both"):
            connection.execute(sa.text('INSERT INTO "user" (id) VALUES (:id)'), {"id": name})
        connection.exec_driver_sql("INSERT INTO workout_plan VALUES ('workout', 'ai'), ('both', 'ai'), ('manual', 'manual')")
        connection.exec_driver_sql("INSERT INTO diet_plan VALUES ('diet', 'ai'), ('both', 'ai')")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.exec_driver_sql('SELECT id, free_workout_plan_uses, free_diet_plan_uses, free_photo_uses FROM "user"').all()
        assert {name: (workout, diet, photos) for name, workout, diet, photos in rows} == {
            "workout": (1, 0, 2), "diet": (0, 1, 2), "manual": (0, 0, 2), "both": (1, 1, 2),
        }
    engine.dispose()
