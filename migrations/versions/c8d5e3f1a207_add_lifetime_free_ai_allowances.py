"""Separate the lifetime free plan and photo allowances.

Legacy trial totals mixed chat, descriptions, photos and plans. Only stored AI
plans establish a trustworthy past generation; photos cannot be inferred.
"""
from alembic import op
import sqlalchemy as sa

revision = "c8d5e3f1a207"
down_revision = "b7c4d2e9f106"
branch_labels = None
depends_on = None


def upgrade():
    # Add columns directly: rebuilding User on SQLite would violate its many
    # incoming foreign keys when upgrading an existing account database.
    op.add_column("user", sa.Column("free_plan_uses", sa.Integer(),
                                   sa.CheckConstraint("free_plan_uses >= 0", name="ck_user_free_plan_uses_nonnegative"),
                                   nullable=False, server_default="0"))
    op.add_column("user", sa.Column("free_photo_uses", sa.Integer(),
                                   sa.CheckConstraint("free_photo_uses >= 0", name="ck_user_free_photo_uses_nonnegative"),
                                   nullable=False, server_default="0"))
    op.execute(sa.text('''UPDATE "user" SET free_plan_uses = 1 WHERE
        EXISTS (SELECT 1 FROM workout_plan p WHERE p.user_id = "user".id AND p.source = 'ai')
        OR EXISTS (SELECT 1 FROM diet_plan p WHERE p.user_id = "user".id AND p.source = 'ai')'''))


def downgrade():
    op.drop_column("user", "free_photo_uses")
    op.drop_column("user", "free_plan_uses")
