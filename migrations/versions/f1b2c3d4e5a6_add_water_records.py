"""Add water records and bottle capacity for the native app."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

revision = "f1b2c3d4e5a6"
down_revision = "e1f9a7b5c3d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_profile", sa.Column("bottle_capacity_ml", sa.Integer(), nullable=True))
    op.create_table(
        "water_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_ml", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.CheckConstraint("amount_ml > 0 AND amount_ml <= 10000", name="ck_water_entry_amount"),
    )
    op.create_index("ix_water_entry_user_date", "water_entry", ["user_id", "local_date"])


def downgrade():
    op.drop_table("water_entry")
    op.drop_column("user_profile", "bottle_capacity_ml")
