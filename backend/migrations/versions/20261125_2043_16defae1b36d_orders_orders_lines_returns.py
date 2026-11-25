# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""orders: orders, lines, returns.

Revision ID: 16defae1b36d
Revises: 1aa43d0b657a
Create Date: 2026-11-25 20:43:41.945497+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "16defae1b36d"
down_revision: str | Sequence[str] | None = "1aa43d0b657a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA orders")
    _ = op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "channel",
            sa.Enum(
                "PHONE",
                "COUNTER",
                name="channel",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="orders",
            ),
            nullable=False,
        ),
        sa.Column(
            "fulfilment",
            sa.Enum(
                "DELIVERY",
                "PICKUP",
                name="fulfilment",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="orders",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "COMPLETED",
                "CANCELLED",
                name="order_status",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="orders",
            ),
            nullable=False,
        ),
        sa.Column(
            "payment_method",
            sa.Enum(
                "CASH",
                "CARD",
                "ON_ACCOUNT",
                "BANK_TRANSFER",
                name="payment_method",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="orders",
            ),
            nullable=False,
        ),
        sa.Column("address_id", sa.Uuid(), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("directions", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("override_reason", sa.String(length=500), nullable=True),
        sa.Column("exchange_id", sa.Uuid(), nullable=True),
        sa.Column("deposit_charged", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("deposit_refunded", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("deposit_currency", sa.String(length=3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "customer_id IS NOT NULL OR payment_method <> 'ON_ACCOUNT'",
            name=op.f("ck_orders_on_account_has_customer"),
        ),
        sa.CheckConstraint(
            "fulfilment <> 'DELIVERY' OR address IS NOT NULL",
            name=op.f("ck_orders_delivery_has_address"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("number", name=op.f("uq_orders_number")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_orders_customer_id"),
        "orders",
        ["customer_id"],
        unique=False,
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_orders_status"),
        "orders",
        ["status"],
        unique=False,
        schema="orders",
    )
    _ = op.create_table(
        "lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("container_type_id", sa.Uuid(), nullable=True),
        sa.Column("container_quantity", sa.Integer(), nullable=True),
        sa.Column("ordered_quantity", sa.Integer(), nullable=False),
        sa.Column("delivered_quantity", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "delivered_quantity >= 0", name=op.f("ck_lines_delivered_not_negative")
        ),
        sa.CheckConstraint(
            "ordered_quantity > 0 OR delivered_quantity > 0",
            name=op.f("ck_lines_not_empty"),
        ),
        sa.CheckConstraint(
            "ordered_quantity >= 0", name=op.f("ck_lines_ordered_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.orders.id"], name=op.f("fk_lines_order_id_orders")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lines")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_lines_order_id"),
        "lines",
        ["order_id"],
        unique=False,
        schema="orders",
    )
    _ = op.create_table(
        "returns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("container_type_id", sa.Uuid(), nullable=False),
        sa.Column("expected_quantity", sa.Integer(), nullable=False),
        sa.Column("returned_quantity", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "expected_quantity >= 0", name=op.f("ck_returns_expected_not_negative")
        ),
        sa.CheckConstraint(
            "returned_quantity >= 0", name=op.f("ck_returns_returned_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.orders.id"], name=op.f("fk_returns_order_id_orders")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_returns")),
        sa.UniqueConstraint(
            "order_id",
            "container_type_id",
            name=op.f("uq_returns_order_id_container_type_id"),
        ),
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_returns_order_id"),
        "returns",
        ["order_id"],
        unique=False,
        schema="orders",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_orders_returns_order_id"), table_name="returns", schema="orders"
    )
    op.drop_table("returns", schema="orders")
    op.drop_index(op.f("ix_orders_lines_order_id"), table_name="lines", schema="orders")
    op.drop_table("lines", schema="orders")
    op.drop_index(op.f("ix_orders_orders_status"), table_name="orders", schema="orders")
    op.drop_index(
        op.f("ix_orders_orders_customer_id"), table_name="orders", schema="orders"
    )
    op.drop_table("orders", schema="orders")
    op.execute("DROP SCHEMA orders")
