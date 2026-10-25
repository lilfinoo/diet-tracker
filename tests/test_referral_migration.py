import importlib.util
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


def test_referral_migration_backfills_preserves_users_and_enforces_monthly_constraints():
    path = Path(__file__).parents[1] / "migrations/versions/a2c4e6f8b0d1_add_monthly_referrals.py"
    spec = importlib.util.spec_from_file_location("referral_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "f1b2c3d4e5a6"
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        users = sa.Table(
            "user", sa.MetaData(), sa.Column("id", UUIDType(binary=False), primary_key=True)
        )
        users.create(connection)
        ids = [uuid.uuid4(), uuid.uuid4()]
        connection.execute(users.insert(), [{"id": item} for item in ids])
        connection.commit()
        context = MigrationContext.configure(connection, opts={"transactional_ddl": True})
        migration.op = Operations(context)
        with context.begin_transaction():
            migration.upgrade()
        codes = connection.exec_driver_sql("SELECT code FROM referral_code").scalars().all()
        assert len(set(codes)) == 2 and all(len(code) == 12 for code in codes)
        connection.exec_driver_sql(
            "INSERT INTO referral (inviter_user_id, invitee_user_id, created_at) VALUES (?, ?, ?)",
            (ids[0].hex, ids[1].hex, "2026-10-25"),
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO referral (inviter_user_id, invitee_user_id, created_at) VALUES (?, ?, ?)",
                (ids[0].hex, ids[0].hex, "2026-10-25"),
            )
        connection.exec_driver_sql(
            "INSERT INTO referral_reward (inviter_user_id, period, granted_at, expires_at) VALUES (?, ?, ?, ?)",
            (ids[0].hex, "2026-10", "2026-10-25", "2026-11-25"),
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.exec_driver_sql(
                "INSERT INTO referral_reward (inviter_user_id, period, granted_at, expires_at) VALUES (?, ?, ?, ?)",
                (ids[0].hex, "2026-10", "2026-10-25", "2026-11-25"),
            )
        connection.execute(users.delete().where(users.c.id == ids[1]))
        assert connection.exec_driver_sql("SELECT invitee_user_id FROM referral").scalar() is None
        assert connection.exec_driver_sql("SELECT count(*) FROM referral_reward").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        connection.commit()
        with context.begin_transaction():
            migration.downgrade()
        assert connection.execute(sa.select(sa.func.count()).select_from(users)).scalar() == 1
        assert "referral_code" not in sa.inspect(connection).get_table_names()
    engine.dispose()
