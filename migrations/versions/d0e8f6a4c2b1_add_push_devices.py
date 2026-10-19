"""Store account-owned APNs registrations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

revision = "d0e8f6a4c2b1"
down_revision = "c8d5e3f1a207"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("push_device",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", UUIDType(binary=False), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("installation_id", sa.String(36), nullable=False, unique=True),
        sa.Column("token", sa.String(512), nullable=False, unique=True),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_index("ix_push_device_user_id", "push_device", ["user_id"])


def downgrade():
    op.drop_index("ix_push_device_user_id", table_name="push_device")
    op.drop_table("push_device")
