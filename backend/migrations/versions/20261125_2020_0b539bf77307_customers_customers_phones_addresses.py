# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""customers: customers, phones, addresses.

Revision ID: 0b539bf77307
Revises: db80f44045ca
Create Date: 2026-11-25 20:20:20.729628+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0b539bf77307"
down_revision: str | Sequence[str] | None = "db80f44045ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA customers")
    _ = op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        schema="customers",
    )
    op.create_index(
        op.f("ix_customers_customers_name"),
        "customers",
        ["name"],
        unique=False,
        schema="customers",
    )
    _ = op.create_table(
        "addresses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("directions", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_addresses_coordinates_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customers.id"],
            name=op.f("fk_addresses_customer_id_customers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
        sa.UniqueConstraint(
            "customer_id", "id", name=op.f("uq_addresses_customer_id_id")
        ),
        schema="customers",
    )
    op.create_index(
        op.f("ix_customers_addresses_customer_id"),
        "addresses",
        ["customer_id"],
        unique=False,
        schema="customers",
    )
    _ = op.create_table(
        "phones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("match_key", sa.String(length=10), nullable=False),
        sa.Column("default_address_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id", "default_address_id"],
            ["customers.addresses.customer_id", "customers.addresses.id"],
            name=op.f("fk_phones_customer_id_default_address_id_addresses"),
            ondelete="SET NULL (default_address_id)",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customers.id"],
            name=op.f("fk_phones_customer_id_customers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phones")),
        sa.UniqueConstraint("match_key", name=op.f("uq_phones_match_key")),
        schema="customers",
    )
    op.create_index(
        op.f("ix_customers_phones_customer_id"),
        "phones",
        ["customer_id"],
        unique=False,
        schema="customers",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_customers_phones_customer_id"), table_name="phones", schema="customers"
    )
    op.drop_table("phones", schema="customers")
    op.drop_index(
        op.f("ix_customers_addresses_customer_id"),
        table_name="addresses",
        schema="customers",
    )
    op.drop_table("addresses", schema="customers")
    op.drop_index(
        op.f("ix_customers_customers_name"), table_name="customers", schema="customers"
    )
    op.drop_table("customers", schema="customers")
    op.execute("DROP SCHEMA customers")
