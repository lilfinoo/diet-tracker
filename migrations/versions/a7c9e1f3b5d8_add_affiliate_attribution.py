"""Extend referral attribution and prepare disabled affiliate accounting."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

revision = "a7c9e1f3b5d8"
down_revision = "f2a0b8c6d4e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "affiliate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("public_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_rate", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("renewal_rate", sa.Numeric(5, 2), nullable=False, server_default="10"),
        sa.Column("recurring_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("annual_first_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("annual_renewal_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("first_rate BETWEEN 0 AND 100 AND renewal_rate BETWEEN 0 AND 100", name="ck_affiliate_rates"),
        sa.CheckConstraint("recurring_months >= 0", name="ck_affiliate_recurring_months"),
        sa.CheckConstraint("annual_first_rate IS NULL OR annual_first_rate BETWEEN 0 AND 100", name="ck_affiliate_annual_first_rate"),
        sa.CheckConstraint("annual_renewal_rate IS NULL OR annual_renewal_rate BETWEEN 0 AND 100", name="ck_affiliate_annual_renewal_rate"),
    )
    # Name reflected legacy constraints so SQLite can replace its original PK/FK.
    naming = {"pk": "pk_%(table_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    inspector = sa.inspect(op.get_bind())
    legacy_pk = inspector.get_pk_constraint("referral_code")["name"] or "pk_referral_code"
    inviter_fk = next(fk["name"] for fk in inspector.get_foreign_keys("referral") if fk["constrained_columns"] == ["inviter_user_id"]) or "fk_referral_inviter_user_id_user"
    with op.batch_alter_table("referral_code", naming_convention=naming) as batch:
        batch.drop_constraint(legacy_pk, type_="primary")
        batch.alter_column("user_id", existing_type=UUIDType(binary=False), nullable=True)
        batch.alter_column("code", existing_type=sa.String(12), type_=sa.String(32), nullable=False)
        batch.add_column(sa.Column("affiliate_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="user_referral"))
        batch.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch.create_primary_key("pk_referral_code", ["code"])
        batch.create_unique_constraint("uq_referral_code_user_id", ["user_id"])
        batch.create_foreign_key("fk_referral_code_affiliate_id", "affiliate", ["affiliate_id"], ["id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_referral_code_owner", "(kind = 'user_referral' AND user_id IS NOT NULL AND affiliate_id IS NULL) OR (kind = 'affiliate' AND user_id IS NULL AND affiliate_id IS NOT NULL)")
    op.create_index("ix_referral_code_affiliate", "referral_code", ["affiliate_id"])
    with op.batch_alter_table("referral", naming_convention=naming) as batch:
        batch.drop_constraint(inviter_fk, type_="foreignkey")
        batch.alter_column("inviter_user_id", existing_type=UUIDType(binary=False), nullable=True)
        batch.create_foreign_key("fk_referral_inviter_user_id_user", "user", ["inviter_user_id"], ["id"], ondelete="CASCADE")
        batch.add_column(sa.Column("affiliate_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("code", sa.String(32), nullable=True))
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="user_referral"))
        batch.add_column(sa.Column("source", sa.String(32), nullable=False, server_default="signup"))
        batch.add_column(sa.Column("validation_state", sa.String(16), nullable=False, server_default="valid"))
        batch.create_foreign_key("fk_referral_affiliate_id", "affiliate", ["affiliate_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_referral_code", "referral_code", ["code"], ["code"], ondelete="SET NULL")
        batch.create_check_constraint("ck_referral_owner", "(kind = 'user_referral' AND inviter_user_id IS NOT NULL AND affiliate_id IS NULL) OR (kind = 'affiliate' AND inviter_user_id IS NULL AND affiliate_id IS NOT NULL)")
        batch.create_check_constraint("ck_referral_validation_state", "validation_state IN ('valid', 'invalid', 'pending')")
        batch.create_index("ix_referral_affiliate_created", ["affiliate_id", "created_at"])
    op.execute("UPDATE referral SET code = (SELECT code FROM referral_code WHERE referral_code.user_id = referral.inviter_user_id)")
    op.create_table(
        "affiliate_payout",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("affiliate_id", sa.Integer(), sa.ForeignKey("affiliate.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount >= 0", name="ck_affiliate_payout_amount"),
        sa.CheckConstraint("status IN ('pending', 'paid')", name="ck_affiliate_payout_status"),
        sa.CheckConstraint("period_end >= period_start", name="ck_affiliate_payout_period"),
    )
    op.create_table(
        "affiliate_commission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("affiliate_id", sa.Integer(), sa.ForeignKey("affiliate.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("transaction_id", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("payout_id", sa.Integer(), sa.ForeignKey("affiliate_payout.id", ondelete="RESTRICT"), nullable=True),
        sa.UniqueConstraint("provider", "transaction_id", "environment", name="uq_affiliate_commission_transaction"),
        sa.CheckConstraint("kind IN ('initial', 'renewal')", name="ck_affiliate_commission_kind"),
        sa.CheckConstraint("status IN ('pending', 'released', 'paid', 'canceled', 'reversed')", name="ck_affiliate_commission_status"),
        sa.CheckConstraint("rate BETWEEN 0 AND 100", name="ck_affiliate_commission_rate"),
        sa.CheckConstraint("gross_amount IS NULL OR gross_amount >= 0", name="ck_affiliate_commission_gross"),
        sa.CheckConstraint("net_amount IS NULL OR net_amount >= 0", name="ck_affiliate_commission_net"),
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name="ck_affiliate_commission_amount"),
    )
    op.create_index("ix_affiliate_payout_created", "affiliate_payout", ["affiliate_id", "created_at"])
    op.create_index("ix_affiliate_commission_status", "affiliate_commission", ["affiliate_id", "environment", "status"])
    with op.batch_alter_table("affiliate_commission") as batch:
        batch.create_check_constraint("ck_affiliate_commission_environment", "environment IN ('production', 'sandbox')")
        batch.create_check_constraint("ck_affiliate_commission_released_net", "status NOT IN ('released', 'paid') OR (net_amount IS NOT NULL AND amount IS NOT NULL)")
    if op.get_bind().dialect.name == "postgresql":
        for table in ("affiliate", "referral_code", "referral", "referral_reward", "affiliate_payout", "affiliate_commission"):
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')
            op.execute(f'CREATE POLICY deny_client_access ON "{table}" FOR ALL TO PUBLIC USING (false) WITH CHECK (false)')
            for role in ("anon", "authenticated"):
                op.execute(f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN REVOKE ALL ON TABLE \"{table}\" FROM {role}; END IF; END $$")


def downgrade():
    # Do not silently destroy attribution or financial history on rollback.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM affiliate")).scalar():
        raise RuntimeError("Affiliate data exists; restore the previous app without downgrading this schema, or restore an approved database backup.")
    # Empty affiliate tables can be removed while retaining legacy referrals.
    op.drop_table("affiliate_commission")
    op.drop_table("affiliate_payout")
    op.execute("DELETE FROM referral WHERE kind = 'affiliate' OR inviter_user_id IS NULL")
    with op.batch_alter_table("referral") as batch:
        batch.drop_index("ix_referral_affiliate_created")
        batch.drop_constraint("ck_referral_owner", type_="check")
        batch.drop_constraint("ck_referral_validation_state", type_="check")
        batch.drop_constraint("fk_referral_affiliate_id", type_="foreignkey")
        batch.drop_constraint("fk_referral_code", type_="foreignkey")
        batch.drop_constraint("fk_referral_inviter_user_id_user", type_="foreignkey")
        batch.create_foreign_key("fk_referral_inviter_user_id_user", "user", ["inviter_user_id"], ["id"], ondelete="CASCADE")
        batch.alter_column("inviter_user_id", existing_type=UUIDType(binary=False), nullable=False)
        for column in ("affiliate_id", "code", "kind", "source", "validation_state"):
            batch.drop_column(column)
    op.execute("DELETE FROM referral_code WHERE kind = 'affiliate'")
    op.drop_index("ix_referral_code_affiliate", table_name="referral_code")
    with op.batch_alter_table("referral_code") as batch:
        batch.drop_constraint("ck_referral_code_owner", type_="check")
        batch.drop_constraint("fk_referral_code_affiliate_id", type_="foreignkey")
        batch.drop_constraint("pk_referral_code", type_="primary")
        batch.drop_constraint("uq_referral_code_user_id", type_="unique")
        batch.alter_column("user_id", existing_type=UUIDType(binary=False), nullable=False)
        batch.alter_column("code", existing_type=sa.String(32), type_=sa.String(12))
        batch.create_primary_key("pk_referral_code", ["user_id"])
        for column in ("affiliate_id", "kind", "active", "created_at"):
            batch.drop_column(column)
    op.drop_table("affiliate")
