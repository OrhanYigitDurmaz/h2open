# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""inventory, purchasing and negative stock setting.

Revision ID: 2ec45d6b2654
Revises: 636553d3f8ff
Create Date: 2026-11-26 00:31:08.413169+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "2ec45d6b2654"
down_revision: str | Sequence[str] | None = "636553d3f8ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA inventory")
    op.execute("CREATE SCHEMA purchasing")
    _ = op.create_table(
        "levels",
        sa.Column(
            "kind",
            sa.Enum(
                "PRODUCT",
                "EMPTY",
                name="item_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="inventory",
            ),
            nullable=False,
        ),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("kind", "item_id", name=op.f("pk_levels")),
        schema="inventory",
    )
    _ = op.create_table(
        "movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "PRODUCT",
                "EMPTY",
                name="item_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="inventory",
            ),
            nullable=False,
        ),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("change", sa.Integer(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "PURCHASE",
                "PURCHASE_VOID",
                "SALE",
                "CUSTOMER_RETURN",
                "ADJUSTMENT",
                "COUNT",
                name="movement_reason",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="inventory",
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint("change <> 0", name=op.f("ck_movements_change_not_zero")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movements")),
        schema="inventory",
    )
    op.create_index(
        op.f("ix_inventory_movements_source_id"),
        "movements",
        ["source_id"],
        unique=False,
        schema="inventory",
    )
    op.create_index(
        "ix_movements_item",
        "movements",
        ["kind", "item_id"],
        unique=False,
        schema="inventory",
    )
    _ = op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tax_number", sa.String(length=20), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("name", name=op.f("uq_suppliers_name")),
        schema="purchasing",
    )
    _ = op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("document_number", sa.String(length=50), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("total >= 0", name=op.f("ck_receipts_total_not_negative")),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["purchasing.suppliers.id"],
            name=op.f("fk_receipts_supplier_id_suppliers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        schema="purchasing",
    )
    op.create_index(
        op.f("ix_purchasing_receipts_supplier_id"),
        "receipts",
        ["supplier_id"],
        unique=False,
        schema="purchasing",
    )
    op.create_index(
        "ux_receipts_live_document",
        "receipts",
        ["supplier_id", "document_number"],
        unique=True,
        schema="purchasing",
        postgresql_where=sa.text("voided_at IS NULL"),
    )
    _ = op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "method",
            sa.Enum(
                "CASH",
                "CARD",
                "BANK_TRANSFER",
                name="supplier_payment_method",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="purchasing",
            ),
            nullable=False,
        ),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["purchasing.receipts.id"],
            name=op.f("fk_payments_receipt_id_receipts"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["purchasing.suppliers.id"],
            name=op.f("fk_payments_supplier_id_suppliers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        schema="purchasing",
    )
    op.create_index(
        op.f("ix_purchasing_payments_receipt_id"),
        "payments",
        ["receipt_id"],
        unique=False,
        schema="purchasing",
    )
    op.create_index(
        op.f("ix_purchasing_payments_supplier_id"),
        "payments",
        ["supplier_id"],
        unique=False,
        schema="purchasing",
    )
    _ = op.create_table(
        "receipt_containers",
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("container_type_id", sa.Uuid(), nullable=False),
        sa.Column("full_in", sa.Integer(), nullable=False),
        sa.Column("empties_out", sa.Integer(), nullable=False),
        sa.Column("purchased", sa.Integer(), nullable=False),
        sa.Column("renewed", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "full_in >= 0 AND empties_out >= 0 AND purchased >= 0 AND renewed >= 0",
            name=op.f("ck_receipt_containers_counts_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["purchasing.receipts.id"],
            name=op.f("fk_receipt_containers_receipt_id_receipts"),
        ),
        sa.PrimaryKeyConstraint(
            "receipt_id", "container_type_id", name=op.f("pk_receipt_containers")
        ),
        schema="purchasing",
    )
    _ = op.create_table(
        "receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "GOODS",
                "CONTAINER_PURCHASE",
                "CONTAINER_RENEWAL",
                "OTHER",
                name="line_kind",
                native_enum=False,
                create_constraint=True,
                length=20,
                schema="purchasing",
            ),
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("container_type_id", sa.Uuid(), nullable=True),
        sa.Column("container_quantity", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("net_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint(
            "(kind = 'GOODS') = (product_id IS NOT NULL)",
            name=op.f("ck_receipt_lines_goods_have_product"),
        ),
        sa.CheckConstraint(
            "kind IN ('GOODS', 'OTHER') OR container_type_id IS NOT NULL",
            name=op.f("ck_receipt_lines_container_lines_have_type"),
        ),
        sa.CheckConstraint(
            "net_amount >= 0", name=op.f("ck_receipt_lines_net_amount_not_negative")
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_receipt_lines_quantity_positive")
        ),
        sa.CheckConstraint(
            "vat_rate >= 0 AND vat_rate <= 100",
            name=op.f("ck_receipt_lines_vat_rate_range"),
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["purchasing.receipts.id"],
            name=op.f("fk_receipt_lines_receipt_id_receipts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipt_lines")),
        schema="purchasing",
    )
    op.create_index(
        op.f("ix_purchasing_receipt_lines_receipt_id"),
        "receipt_lines",
        ["receipt_id"],
        unique=False,
        schema="purchasing",
    )
    op.add_column(
        "settings",
        sa.Column(
            "negative_stock_allowed",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        schema="company",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_column("settings", "negative_stock_allowed", schema="company")
    op.drop_index(
        op.f("ix_purchasing_receipt_lines_receipt_id"),
        table_name="receipt_lines",
        schema="purchasing",
    )
    op.drop_table("receipt_lines", schema="purchasing")
    op.drop_table("receipt_containers", schema="purchasing")
    op.drop_index(
        op.f("ix_purchasing_payments_supplier_id"),
        table_name="payments",
        schema="purchasing",
    )
    op.drop_index(
        op.f("ix_purchasing_payments_receipt_id"),
        table_name="payments",
        schema="purchasing",
    )
    op.drop_table("payments", schema="purchasing")
    op.drop_index(
        "ux_receipts_live_document",
        table_name="receipts",
        schema="purchasing",
        postgresql_where=sa.text("voided_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_purchasing_receipts_supplier_id"),
        table_name="receipts",
        schema="purchasing",
    )
    op.drop_table("receipts", schema="purchasing")
    op.drop_table("suppliers", schema="purchasing")
    op.drop_index("ix_movements_item", table_name="movements", schema="inventory")
    op.drop_index(
        op.f("ix_inventory_movements_source_id"),
        table_name="movements",
        schema="inventory",
    )
    op.drop_table("movements", schema="inventory")
    op.drop_table("levels", schema="inventory")
    op.execute("DROP SCHEMA purchasing")
    op.execute("DROP SCHEMA inventory")
