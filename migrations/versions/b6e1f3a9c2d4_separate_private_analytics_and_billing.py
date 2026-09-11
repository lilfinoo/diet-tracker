"""separate account private analytics and billing data

Revision ID: b6e1f3a9c2d4
Revises: a4e8c1f7b9d2
Create Date: 2026-09-03 15:00:00.000000
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import UUIDType


revision = "b6e1f3a9c2d4"
down_revision = "a4e8c1f7b9d2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    with op.batch_alter_table("subscription") as batch_op:
        batch_op.add_column(sa.Column("last_payment_id", sa.String(length=255), nullable=True))
    bind.execute(sa.text(
        "UPDATE subscription SET status = 'pending', current_period_start = NULL, "
        "current_period_end = NULL WHERE provider = 'asaas' "
        "AND status IN ('active', 'trialing')"
    ))

    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("analytics_subject_id", UUIDType(binary=False), nullable=True))

    users = sa.table(
        "user",
        sa.column("id", UUIDType(binary=False)),
        sa.column("username", sa.String()),
        sa.column("name", sa.String()),
        sa.column("email", sa.String()),
        sa.column("analytics_subject_id", UUIDType(binary=False)),
    )
    identities = sa.table(
        "oauth_identity",
        sa.column("id", sa.Integer()),
        sa.column("user_id", UUIDType(binary=False)),
        sa.column("email", sa.String()),
        sa.column("email_verified", sa.Boolean()),
        sa.column("display_name", sa.String()),
    )
    identity_rows = bind.execute(
        sa.select(
            identities.c.user_id,
            identities.c.email,
            identities.c.email_verified,
            identities.c.display_name,
        ).order_by(identities.c.id)
    ).fetchall()
    identity_by_user = {}
    for row in identity_rows:
        identity_by_user.setdefault(str(row.user_id), row)
    for row in bind.execute(sa.select(users.c.id, users.c.username)).fetchall():
        identity = identity_by_user.get(str(row.id))
        bind.execute(
            users.update().where(users.c.id == row.id).values(
                name=(identity.display_name if identity and identity.display_name else row.username),
                email=(identity.email if identity and identity.email_verified else None),
                analytics_subject_id=uuid.uuid4(),
            )
        )

    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column("analytics_subject_id", nullable=False)
        batch_op.create_unique_constraint(
            "uq_user_analytics_subject_id", ["analytics_subject_id"]
        )

    with op.batch_alter_table("analytics_event") as batch_op:
        batch_op.add_column(sa.Column("subject_id", UUIDType(binary=False), nullable=True))

    bind.execute(sa.text(
        "UPDATE analytics_event SET subject_id = "
        "(SELECT analytics_subject_id FROM \"user\" WHERE \"user\".id = analytics_event.user_id) "
        "WHERE user_id IS NOT NULL"
    ))
    op.create_index(
        "ix_analytics_event_subject_created",
        "analytics_event",
        ["subject_id", "created_at"],
    )
    op.drop_index("ix_analytics_event_user_created", table_name="analytics_event")
    inspector = sa.inspect(bind)
    user_fk = next(
        (
            item
            for item in inspector.get_foreign_keys("analytics_event")
            if item.get("constrained_columns") == ["user_id"]
        ),
        None,
    )
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    }
    with op.batch_alter_table(
        "analytics_event", naming_convention=naming_convention
    ) as batch_op:
        batch_op.drop_constraint(
            (user_fk or {}).get("name") or "fk_analytics_event_user_id_user",
            type_="foreignkey",
        )
        batch_op.drop_column("user_id")

    with op.batch_alter_table("billing_event") as batch_op:
        batch_op.add_column(sa.Column("resource_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("processing_status", sa.String(length=16), nullable=False, server_default="processed"))
        batch_op.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("processed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.String(length=500), nullable=True))
        batch_op.create_check_constraint(
            "ck_billing_event_processing_status",
            "processing_status IN ('pending', 'processed', 'failed')",
        )
        batch_op.create_index(
            "ix_billing_event_status_received", ["processing_status", "received_at"]
        )
    bind.execute(sa.text(
        "UPDATE billing_event SET processed_at = received_at WHERE processed_at IS NULL"
    ))

    op.create_table(
        "admin_action_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", UUIDType(binary=False), nullable=True),
        sa.Column("subject_user_id", UUIDType(binary=False), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subject_user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_admin_audit_actor_created",
        "admin_action_audit",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_admin_audit_subject_created",
        "admin_action_audit",
        ["subject_user_id", "created_at"],
    )


def downgrade():
    bind = op.get_bind()
    op.drop_index("ix_admin_audit_subject_created", table_name="admin_action_audit")
    op.drop_index("ix_admin_audit_actor_created", table_name="admin_action_audit")
    op.drop_table("admin_action_audit")

    with op.batch_alter_table("billing_event") as batch_op:
        batch_op.drop_index("ix_billing_event_status_received")
        batch_op.drop_constraint("ck_billing_event_processing_status", type_="check")
        batch_op.drop_column("last_error")
        batch_op.drop_column("processed_at")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("processing_status")
        batch_op.drop_column("payload")
        batch_op.drop_column("resource_id")

    with op.batch_alter_table("analytics_event") as batch_op:
        batch_op.add_column(sa.Column("user_id", UUIDType(binary=False), nullable=True))
        batch_op.create_foreign_key(
            "fk_analytics_event_user_id_user", "user", ["user_id"], ["id"], ondelete="SET NULL"
        )
    bind.execute(sa.text(
        "UPDATE analytics_event SET user_id = "
        "(SELECT id FROM \"user\" WHERE \"user\".analytics_subject_id = analytics_event.subject_id) "
        "WHERE subject_id IS NOT NULL"
    ))
    op.create_index(
        "ix_analytics_event_user_created", "analytics_event", ["user_id", "created_at"]
    )
    op.drop_index("ix_analytics_event_subject_created", table_name="analytics_event")
    with op.batch_alter_table("analytics_event") as batch_op:
        batch_op.drop_column("subject_id")

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("uq_user_analytics_subject_id", type_="unique")
        batch_op.drop_column("analytics_subject_id")
        batch_op.drop_column("email")
        batch_op.drop_column("name")

    with op.batch_alter_table("subscription") as batch_op:
        batch_op.drop_column("last_payment_id")
