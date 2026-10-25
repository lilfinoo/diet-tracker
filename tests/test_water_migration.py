import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_water_migration_preserves_profiles_and_enforces_entry_constraints():
    path = Path(__file__).parents[1] / "migrations/versions/f1b2c3d4e5a6_add_water_records.py"
    spec = importlib.util.spec_from_file_location("water_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql('CREATE TABLE "user" (id CHAR(32) PRIMARY KEY)')
        connection.exec_driver_sql('CREATE TABLE user_profile (id INTEGER PRIMARY KEY, user_id CHAR(32) REFERENCES "user"(id))')
        connection.exec_driver_sql("INSERT INTO user VALUES ('12345678123456781234567812345678')")
        connection.exec_driver_sql("INSERT INTO user_profile VALUES (1, '12345678123456781234567812345678')")
        connection.commit()
        context = MigrationContext.configure(connection, opts={"transactional_ddl": True})
        migration.op = Operations(context)
        with context.begin_transaction():
            migration.upgrade()
        assert connection.exec_driver_sql("SELECT bottle_capacity_ml FROM user_profile").scalar() is None
        values = "('12345678123456781234567812345678', 250, '2026-01-02 02:30:00', '2026-01-01', 'America/Sao_Paulo')"
        connection.exec_driver_sql("INSERT INTO water_entry (user_id, amount_ml, occurred_at, local_date, timezone) VALUES " + values)
        with pytest.raises(sa.exc.IntegrityError):
            connection.exec_driver_sql("UPDATE water_entry SET amount_ml=0")
        connection.exec_driver_sql("DELETE FROM user_profile")
        connection.exec_driver_sql("DELETE FROM user")
        assert connection.exec_driver_sql("SELECT count(*) FROM water_entry").scalar() == 0
        connection.commit()
        with context.begin_transaction():
            migration.downgrade()
        assert "water_entry" not in sa.inspect(connection).get_table_names()
        assert "bottle_capacity_ml" not in {column["name"] for column in sa.inspect(connection).get_columns("user_profile")}
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
