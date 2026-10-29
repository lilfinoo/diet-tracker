"""Exercise the actual referral migrations against persisted legacy records."""
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


def test_legacy_referrals_survive_affiliate_upgrade_and_account_deletion(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(sa.text("CREATE TABLE user (id CHAR(32) PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO user VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'), ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration("a2c4e6f8b0d1_add_monthly_referrals.py").upgrade()
        connection.execute(sa.text("UPDATE referral_code SET code='LEGACYCODE12' WHERE user_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'"))
        connection.execute(sa.text("INSERT INTO referral VALUES (1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("INSERT INTO referral_reward VALUES (1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '2026-10', CURRENT_TIMESTAMP, '2026-11-28')"))
        upgrade = migration("a7c9e1f3b5d8_add_affiliate_attribution.py")
        with Operations.context(MigrationContext.configure(connection)):
            upgrade.upgrade()
            assert connection.execute(sa.text("SELECT code, kind, validation_state FROM referral")).one() == ("LEGACYCODE12", "user_referral", "valid")
            assert connection.execute(sa.text("SELECT COUNT(*) FROM referral_reward")).scalar_one() == 1
            assert sa.inspect(connection).get_pk_constraint("referral_code")["constrained_columns"] == ["code"]
            with connection.begin_nested() as savepoint:
                connection.execute(sa.text("INSERT INTO user VALUES ('cccccccccccccccccccccccccccccccc')"))
                connection.execute(sa.text("INSERT INTO affiliate(id, name, public_name) VALUES (1, 'Ana', 'Ana')"))
                connection.execute(sa.text("INSERT INTO referral_code(code, affiliate_id, kind) VALUES ('ANA10', 1, 'affiliate')"))
                connection.execute(sa.text("INSERT INTO referral(id, invitee_user_id, affiliate_id, code, kind, created_at) VALUES (2, 'cccccccccccccccccccccccccccccccc', 1, 'ANA10', 'affiliate', CURRENT_TIMESTAMP)"))
                connection.execute(sa.text("DELETE FROM user WHERE id='cccccccccccccccccccccccccccccccc'"))
                assert connection.execute(sa.text("SELECT invitee_user_id, affiliate_id, code FROM referral WHERE id=2")).one() == (None, 1, "ANA10")
                with pytest.raises(RuntimeError, match="Affiliate data exists"):
                    upgrade.downgrade()
                assert connection.execute(sa.text("SELECT COUNT(*) FROM affiliate")).scalar_one() == 1
                savepoint.rollback()
            with connection.begin_nested() as savepoint:
                connection.execute(sa.text("DELETE FROM user WHERE id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'"))
                assert connection.execute(sa.text("SELECT COUNT(*) FROM referral")).scalar_one() == 0
                savepoint.rollback()
            upgrade.downgrade()
            assert connection.execute(sa.text("SELECT COUNT(*) FROM referral")).scalar_one() == 1
            assert connection.execute(sa.text("SELECT COUNT(*) FROM referral_reward")).scalar_one() == 1
            assert sa.inspect(connection).get_pk_constraint("referral_code")["constrained_columns"] == ["user_id"]
    engine.dispose()
