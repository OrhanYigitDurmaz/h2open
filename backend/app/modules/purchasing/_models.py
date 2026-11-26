# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Purchasing tables, in the ``purchasing`` schema. Private to this module.

Receipts are never edited: a mistake is fixed by voiding the receipt and
entering it again. Products and container types belong to the catalog, so
they are plain IDs.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.db import module_metadata
from app.core.ids import new_id
from app.modules.purchasing._views import LineKind, SupplierPaymentMethod

if TYPE_CHECKING:
    from enum import StrEnum

AMOUNT = Numeric(14, 2)


def _enum(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, native_enum=False, create_constraint=True, length=20)


class Base(DeclarativeBase):
    """Base for purchasing tables."""

    metadata: ClassVar[MetaData] = module_metadata("purchasing")


class Supplier(Base):
    """Someone we buy from."""

    __tablename__: str = "suppliers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    tax_number: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(String(1000))
    active: Mapped[bool] = mapped_column(default=True)


class Receipt(Base):
    """A supplier's official receipt (invoice)."""

    __tablename__: str = "receipts"
    __table_args__: tuple[CheckConstraint | Index, ...] = (
        CheckConstraint("total >= 0", name="total_not_negative"),
        # The same document cannot be entered twice, unless voided first.
        Index(
            "ux_receipts_live_document",
            "supplier_id",
            "document_number",
            unique=True,
            postgresql_where=text("voided_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey(Supplier.id), index=True)
    document_number: Mapped[str] = mapped_column(String(50))
    issued_on: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    total: Mapped[Decimal] = mapped_column(AMOUNT)
    notes: Mapped[str | None] = mapped_column(String(1000))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[UUID] = mapped_column()
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[UUID | None] = mapped_column()
    void_reason: Mapped[str | None] = mapped_column(String(500))

    lines: Mapped[list[ReceiptLine]] = relationship(
        order_by="ReceiptLine.id", cascade="all, delete-orphan"
    )
    containers: Mapped[list[ReceiptContainer]] = relationship(
        order_by="ReceiptContainer.container_type_id", cascade="all, delete-orphan"
    )


class ReceiptLine(Base):
    """One line of a receipt."""

    __tablename__: str = "receipt_lines"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("net_amount >= 0", name="net_amount_not_negative"),
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100", name="vat_rate_range"),
        CheckConstraint(
            "(kind = 'GOODS') = (product_id IS NOT NULL)", name="goods_have_product"
        ),
        CheckConstraint(
            "kind IN ('GOODS', 'OTHER') OR container_type_id IS NOT NULL",
            name="container_lines_have_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    receipt_id: Mapped[UUID] = mapped_column(ForeignKey(Receipt.id), index=True)
    kind: Mapped[LineKind] = mapped_column(_enum(LineKind, "line_kind"))
    product_id: Mapped[UUID | None] = mapped_column()
    container_type_id: Mapped[UUID | None] = mapped_column()
    """For goods: the product's container type at the time, if returnable."""
    container_quantity: Mapped[int | None] = mapped_column()
    """For goods: containers per unit at the time."""
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column()
    net_amount: Mapped[Decimal] = mapped_column(AMOUNT)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    vat_amount: Mapped[Decimal] = mapped_column(AMOUNT)


class ReceiptContainer(Base):
    """Container flows of one type on a receipt, worked out when entered."""

    __tablename__: str = "receipt_containers"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(
            "full_in >= 0 AND empties_out >= 0 AND purchased >= 0 AND renewed >= 0",
            name="counts_not_negative",
        ),
    )

    receipt_id: Mapped[UUID] = mapped_column(ForeignKey(Receipt.id), primary_key=True)
    container_type_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_in: Mapped[int] = mapped_column()
    empties_out: Mapped[int] = mapped_column()
    purchased: Mapped[int] = mapped_column()
    renewed: Mapped[int] = mapped_column()


class Payment(Base):
    """Money we paid a supplier, optionally against one receipt."""

    __tablename__: str = "payments"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey(Supplier.id), index=True)
    receipt_id: Mapped[UUID | None] = mapped_column(ForeignKey(Receipt.id), index=True)
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
    currency: Mapped[str] = mapped_column(String(3))
    method: Mapped[SupplierPaymentMethod] = mapped_column(
        _enum(SupplierPaymentMethod, "supplier_payment_method")
    )
    paid_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[UUID] = mapped_column()
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[UUID | None] = mapped_column()
    void_reason: Mapped[str | None] = mapped_column(String(500))
