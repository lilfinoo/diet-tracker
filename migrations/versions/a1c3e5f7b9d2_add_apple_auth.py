"""Add one-use Apple authentication challenges and encrypted revocation tokens."""
from alembic import op
import sqlalchemy as sa

revision = "a1c3e5f7b9d2"
down_revision = "d7b3f9a5c021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("oauth_identity", sa.Column("apple_refresh_token", sa.Text(), nullable=True))
    op.create_table("apple_auth_challenge", sa.Column("nonce_hash", sa.String(64), primary_key=True),
                    sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_apple_auth_challenge_expires_at", "apple_auth_challenge", ["expires_at"])


def downgrade():
    op.drop_table("apple_auth_challenge")
    op.drop_column("oauth_identity", "apple_refresh_token")
