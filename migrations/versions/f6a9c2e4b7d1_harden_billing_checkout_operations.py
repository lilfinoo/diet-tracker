"""harden billing checkout operations

Revision ID: f6a9c2e4b7d1
Revises: 8c2a1f7b9d03
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a9c2e4b7d1"
down_revision = "8c2a1f7b9d03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("billing_checkout", schema=None) as batch_op:
        batch_op.add_column(sa.Column("external_reference", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("checkout_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))

    op.execute(sa.text(
        "UPDATE billing_checkout "
        "SET external_reference = 'dt-checkout-legacy-' || CAST(id AS VARCHAR) "
        "WHERE external_reference IS NULL"
    ))
    with op.batch_alter_table("billing_checkout", schema=None) as batch_op:
        batch_op.alter_column(
            "external_reference",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_billing_checkout_provider_external_reference",
            ["provider", "external_reference"],
        )

    op.create_index(
        "uq_billing_checkout_open_user",
        "billing_checkout",
        ["user_id", "provider"],
        unique=True,
        sqlite_where=sa.text("status IN ('creating', 'pending')"),
        postgresql_where=sa.text("status IN ('creating', 'pending')"),
    )


def downgrade():
    op.drop_index("uq_billing_checkout_open_user", table_name="billing_checkout")
    with op.batch_alter_table("billing_checkout", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_billing_checkout_provider_external_reference",
            type_="unique",
        )
        batch_op.drop_column("expires_at")
        batch_op.drop_column("checkout_url")
        batch_op.drop_column("external_reference")
