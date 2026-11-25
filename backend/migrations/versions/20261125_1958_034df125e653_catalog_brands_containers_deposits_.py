# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""catalog: brands, containers, deposits, products, prices.

Revision ID: 034df125e653
Revises:
Create Date: 2026-11-25 19:58:23.068399+00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "034df125e653"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("CREATE SCHEMA catalog")
    _ = op.create_table(
        "brands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brands")),
        sa.UniqueConstraint("name", name=op.f("uq_brands_name")),
        schema="catalog",
    )
    _ = op.create_table(
        "container_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["catalog.brands.id"],
            name=op.f("fk_container_types_brand_id_brands"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_container_types")),
        sa.UniqueConstraint(
            "brand_id", "name", name=op.f("uq_container_types_brand_id_name")
        ),
        schema="catalog",
    )
    _ = op.create_table(
        "deposit_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("container_type_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount >= 0", name=op.f("ck_deposit_prices_amount_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["container_type_id"],
            ["catalog.container_types.id"],
            name=op.f("fk_deposit_prices_container_type_id_container_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_prices")),
        sa.UniqueConstraint(
            "container_type_id",
            "valid_from",
            name=op.f("uq_deposit_prices_container_type_id_valid_from"),
        ),
        schema="catalog",
    )
    _ = op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("barcode", sa.String(length=50), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("container_type_id", sa.Uuid(), nullable=True),
        sa.Column("container_quantity", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "(container_type_id IS NULL) = (container_quantity IS NULL)",
            name=op.f("ck_products_container_complete"),
        ),
        sa.CheckConstraint(
            "container_quantity > 0",
            name=op.f("ck_products_container_quantity_positive"),
        ),
        sa.CheckConstraint(
            "vat_rate >= 0 AND vat_rate <= 100", name=op.f("ck_products_vat_rate_range")
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["catalog.brands.id"],
            name=op.f("fk_products_brand_id_brands"),
        ),
        sa.ForeignKeyConstraint(
            ["container_type_id"],
            ["catalog.container_types.id"],
            name=op.f("fk_products_container_type_id_container_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("barcode", name=op.f("uq_products_barcode")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
        schema="catalog",
    )
    _ = op.create_table(
        "product_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount >= 0", name=op.f("ck_product_prices_amount_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["catalog.products.id"],
            name=op.f("fk_product_prices_product_id_products"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_prices")),
        sa.UniqueConstraint(
            "product_id",
            "valid_from",
            name=op.f("uq_product_prices_product_id_valid_from"),
        ),
        schema="catalog",
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("product_prices", schema="catalog")
    op.drop_table("products", schema="catalog")
    op.drop_table("deposit_prices", schema="catalog")
    op.drop_table("container_types", schema="catalog")
    op.drop_table("brands", schema="catalog")
    op.execute("DROP SCHEMA catalog")
