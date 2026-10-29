"""Friend rewards and affiliate attribution must coexist without losing history."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def migration(filename):
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_independent_attribution_upgrade_preserves_history_and_rejects_lossy_downgrade(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'independent.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE user (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO user VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'), ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'), ('cccccccccccccccccccccccccccccccc')")
        with Operations.context(MigrationContext.configure(connection)):
            migration("a2c4e6f8b0d1_add_monthly_referrals.py").upgrade()
            connection.exec_driver_sql("UPDATE referral_code SET code='FRIEND12' WHERE user_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'")
            connection.exec_driver_sql("INSERT INTO referral VALUES (1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', CURRENT_TIMESTAMP)")
            connection.exec_driver_sql("INSERT INTO referral_reward VALUES (1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '2026-10', CURRENT_TIMESTAMP, '2026-11-28')")
            migration("a7c9e1f3b5d8_add_affiliate_attribution.py").upgrade()
            connection.exec_driver_sql("INSERT INTO affiliate(id, name, public_name) VALUES (1, 'Ana', 'Ana')")
            connection.exec_driver_sql("INSERT INTO referral_code(code, affiliate_id, kind) VALUES ('ANA10', 1, 'affiliate')")
            expected_indexes = sa.inspect(connection).get_indexes("referral")
            independent = migration("b8d0f2a4c6e9_allow_independent_referral_attribution.py")
            assert independent.down_revision == "a7c9e1f3b5d8"
            independent.upgrade()
            assert sa.inspect(connection).get_indexes("referral") == expected_indexes
            connection.exec_driver_sql("INSERT INTO referral(id, invitee_user_id, affiliate_id, code, kind, created_at) VALUES (2, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 1, 'ANA10', 'affiliate', CURRENT_TIMESTAMP)")
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral WHERE kind='user_referral'").scalar_one() == 1
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral WHERE kind='affiliate'").scalar_one() == 1
            assert connection.exec_driver_sql("SELECT code FROM referral WHERE id=1").scalar_one() == "FRIEND12"
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral_reward").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            for query in (
                "INSERT INTO referral(id, inviter_user_id, invitee_user_id, kind, created_at) VALUES (3, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'user_referral', CURRENT_TIMESTAMP)",
                "INSERT INTO referral(id, invitee_user_id, affiliate_id, code, kind, created_at) VALUES (3, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 1, 'ANA10', 'affiliate', CURRENT_TIMESTAMP)",
            ):
                with connection.begin_nested() as savepoint:
                    with pytest.raises(sa.exc.IntegrityError):
                        connection.exec_driver_sql(query)
                    savepoint.rollback()
            with pytest.raises(RuntimeError, match="downgrade would lose attribution history"):
                independent.downgrade()
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral").scalar_one() == 2
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral_reward").scalar_one() == 1
            with connection.begin_nested() as savepoint:
                # Test safe downgrade only when each account has one attribution.
                connection.exec_driver_sql("UPDATE referral SET invitee_user_id='cccccccccccccccccccccccccccccccc' WHERE id=2")
                independent.downgrade()
                uniques = sa.inspect(connection).get_unique_constraints("referral")
                assert any(item["name"] == "uq_referral_invitee" and item["column_names"] == ["invitee_user_id"] for item in uniques)
                assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral").scalar_one() == 2
                assert connection.exec_driver_sql("SELECT COUNT(*) FROM referral_reward").scalar_one() == 1
                savepoint.rollback()
    engine.dispose()
