# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Catalog tables, in the ``catalog`` schema. Private to this module."""

from datetime import datetime
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import module_metadata
from app.core.ids import new_id

# Prices keep 4 decimals so unit prices can be more precise than totals.
PRICE = Numeric(14, 4)


class Base(DeclarativeBase):
    """Base for catalog tables."""

    metadata: ClassVar[MetaData] = module_metadata("catalog")


class Brand(Base):
    """A water brand, ours or one we resell."""

    __tablename__: str = "brands"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool] = mapped_column(default=True)


class ContainerType(Base):
    """A returnable container of one brand, e.g. Brand A's 19 L carboy.

    Containers of different brands are different types, even when they are
    physically identical, because each brand only takes back its own.
    """

    __tablename__: str = "container_types"
    __table_args__: tuple[UniqueConstraint] = (UniqueConstraint("brand_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey(Brand.id))
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(default=True)


class DepositPrice(Base):
    """The deposit for a container type from ``valid_from`` on.

    Rows are never updated: a price change adds a row, so history is kept
    and future price changes can be scheduled in advance.
    """

    __tablename__: str = "deposit_prices"
    __table_args__: tuple[UniqueConstraint, CheckConstraint] = (
        UniqueConstraint("container_type_id", "valid_from"),
        CheckConstraint("amount >= 0", name="amount_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    container_type_id: Mapped[UUID] = mapped_column(ForeignKey(ContainerType.id))
    amount: Mapped[Decimal] = mapped_column(PRICE)
    currency: Mapped[str] = mapped_column(String(3))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Product(Base):
    """Anything we sell: water, packs, dispensers, cups.

    A product delivered in returnable containers links to its container
    type and says how many containers one unit uses.
    """

    __tablename__: str = "products"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(
            "(container_type_id IS NULL) = (container_quantity IS NULL)",
            name="container_complete",
        ),
        CheckConstraint("container_quantity > 0", name="container_quantity_positive"),
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100", name="vat_rate_range"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    barcode: Mapped[str | None] = mapped_column(String(50), unique=True)
    brand_id: Mapped[UUID | None] = mapped_column(ForeignKey(Brand.id))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    container_type_id: Mapped[UUID | None] = mapped_column(ForeignKey(ContainerType.id))
    container_quantity: Mapped[int | None] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)


class ProductPrice(Base):
    """A product's sale price (VAT included) from ``valid_from`` on."""

    __tablename__: str = "product_prices"
    __table_args__: tuple[UniqueConstraint, CheckConstraint] = (
        UniqueConstraint("product_id", "valid_from"),
        CheckConstraint("amount >= 0", name="amount_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    product_id: Mapped[UUID] = mapped_column(ForeignKey(Product.id))
    amount: Mapped[Decimal] = mapped_column(PRICE)
    currency: Mapped[str] = mapped_column(String(3))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
