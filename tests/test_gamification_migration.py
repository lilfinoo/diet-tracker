import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_upgrade_downgrade_preserve_existing_users_and_enforce_daily_uniqueness():
    path = Path(__file__).parents[1] / 'migrations/versions/c1d8f4a6b2e9_add_gamification_progress.py'
    spec = importlib.util.spec_from_file_location('gamification_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.exec_driver_sql('CREATE TABLE "user" (id CHAR(32) PRIMARY KEY)')
        connection.exec_driver_sql("INSERT INTO user VALUES ('12345678123456781234567812345678')")
        connection.commit()
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        user = "'12345678123456781234567812345678'"
        connection.exec_driver_sql(f'INSERT INTO gamification_profile (user_id) VALUES ({user})')
        assert connection.exec_driver_sql('SELECT current_streak FROM gamification_profile').scalar() == 0
        sql = f"INSERT INTO gamification_day (user_id, local_date, timezone) VALUES ({user}, '2026-11-04', 'UTC')"
        connection.exec_driver_sql(sql)
        with pytest.raises(sa.exc.IntegrityError):
            connection.exec_driver_sql(sql)
        with pytest.raises(sa.exc.IntegrityError):
            connection.exec_driver_sql('UPDATE gamification_profile SET available_protections=3')
        connection.exec_driver_sql('DELETE FROM user')
        assert connection.exec_driver_sql('SELECT count(*) FROM gamification_day').scalar() == 0
        connection.exec_driver_sql(f'INSERT INTO user VALUES ({user})')
        migration.downgrade()
        assert connection.exec_driver_sql('SELECT count(*) FROM user').scalar() == 1
        assert 'gamification_day' not in sa.inspect(connection).get_table_names()
    engine.dispose()
