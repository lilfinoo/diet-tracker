"""Allow independent friend and affiliate attribution for the same account."""
from alembic import op
import sqlalchemy as sa

revision = "b8d0f2a4c6e9"
down_revision = "a7c9e1f3b5d8"
branch_labels = None
depends_on = None


def upgrade():
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("referral")
    legacy = next(item for item in constraints if item["column_names"] == ["invitee_user_id"])
    with op.batch_alter_table("referral") as batch:
        batch.drop_constraint(legacy["name"], type_="unique")
        batch.create_unique_constraint("uq_referral_invitee_kind", ["invitee_user_id", "kind"])


def downgrade():
    duplicate = op.get_bind().execute(sa.text(
        "SELECT invitee_user_id FROM referral WHERE invitee_user_id IS NOT NULL "
        "GROUP BY invitee_user_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            "Independent referral attributions exist; downgrade would lose attribution history."
        )
    with op.batch_alter_table("referral") as batch:
        batch.drop_constraint("uq_referral_invitee_kind", type_="unique")
        batch.create_unique_constraint("uq_referral_invitee", ["invitee_user_id"])
