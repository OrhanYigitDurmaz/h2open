# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Order tables, in the ``orders`` schema. Private to this module.

Customers, products and container types belong to other modules, so they
are plain IDs, and everything an order needs later (names, prices, the
address) is copied onto it when it is taken.
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.db import enum_column, module_metadata
from app.core.ids import new_id
from app.modules.orders._views import (
    Channel,
    ClaimAction,
    Fulfilment,
    OrderStatus,
    PaymentMethod,
)

PRICE = Numeric(14, 4)


class Base(DeclarativeBase):
    """Base for order tables."""

    metadata: ClassVar[MetaData] = module_metadata("orders")


class Order(Base):
    """A sale, from taking it to handing it over."""

    __tablename__: str = "orders"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(
            "fulfilment <> 'DELIVERY' OR address IS NOT NULL",
            name="delivery_has_address",
        ),
        CheckConstraint(
            "customer_id IS NOT NULL OR payment_method <> 'ON_ACCOUNT'",
            name="on_account_has_customer",
        ),
        CheckConstraint(
            "fulfilment = 'DELIVERY' OR (claimed_by IS NULL AND pooled_at IS NULL)",
            name="only_deliveries_are_claimed",
        ),
    )
    # Read the database-generated order number back right after insert.
    __mapper_args__: Mapping[str, object] = MappingProxyType({"eager_defaults": True})

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    number: Mapped[int] = mapped_column(Identity(), unique=True)
    customer_id: Mapped[UUID | None] = mapped_column(index=True)
    channel: Mapped[Channel] = mapped_column(enum_column(Channel, "channel"))
    fulfilment: Mapped[Fulfilment] = mapped_column(
        enum_column(Fulfilment, "fulfilment")
    )
    status: Mapped[OrderStatus] = mapped_column(
        enum_column(OrderStatus, "order_status"), index=True
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        enum_column(PaymentMethod, "payment_method")
    )
    address_id: Mapped[UUID | None] = mapped_column()
    address: Mapped[str | None] = mapped_column(String(300))
    directions: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    notes: Mapped[str | None] = mapped_column(String(1000))
    override_reason: Mapped[str | None] = mapped_column(String(500))
    exchange_id: Mapped[UUID | None] = mapped_column()
    deposit_charged: Mapped[Decimal | None] = mapped_column(PRICE)
    deposit_refunded: Mapped[Decimal | None] = mapped_column(PRICE)
    deposit_currency: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column()
    completed_by: Mapped[UUID | None] = mapped_column()
    cancelled_by: Mapped[UUID | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    claimed_by: Mapped[UUID | None] = mapped_column(index=True)
    """The driver holding the delivery (identity module)."""
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pooled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When an open, unclaimed delivery entered the pool; ``None`` otherwise."""

    lines: Mapped[list[OrderLine]] = relationship(
        order_by="OrderLine.id", cascade="all, delete-orphan"
    )
    returns: Mapped[list[OrderReturn]] = relationship(
        order_by="OrderReturn.container_type_id", cascade="all, delete-orphan"
    )


class OrderLine(Base):
    """A product on an order, with name and price copied from the catalog."""

    __tablename__: str = "lines"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint("ordered_quantity >= 0", name="ordered_not_negative"),
        CheckConstraint("delivered_quantity >= 0", name="delivered_not_negative"),
        CheckConstraint(
            "ordered_quantity > 0 OR delivered_quantity > 0", name="not_empty"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    order_id: Mapped[UUID] = mapped_column(ForeignKey(Order.id), index=True)
    product_id: Mapped[UUID] = mapped_column()
    sku: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    unit_price: Mapped[Decimal] = mapped_column(PRICE)
    currency: Mapped[str] = mapped_column(String(3))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    container_type_id: Mapped[UUID | None] = mapped_column()
    container_quantity: Mapped[int | None] = mapped_column()
    ordered_quantity: Mapped[int] = mapped_column()
    delivered_quantity: Mapped[int | None] = mapped_column()


class OrderReturn(Base):
    """Empties of one container type expected back, and actually returned."""

    __tablename__: str = "returns"
    __table_args__: tuple[UniqueConstraint | CheckConstraint, ...] = (
        UniqueConstraint("order_id", "container_type_id"),
        CheckConstraint("expected_quantity >= 0", name="expected_not_negative"),
        CheckConstraint("returned_quantity >= 0", name="returned_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    order_id: Mapped[UUID] = mapped_column(ForeignKey(Order.id), index=True)
    container_type_id: Mapped[UUID] = mapped_column()
    expected_quantity: Mapped[int] = mapped_column()
    returned_quantity: Mapped[int | None] = mapped_column()


class ClaimEvent(Base):
    """One step in who has held a delivery. Append-only."""

    __tablename__: str = "claim_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    order_id: Mapped[UUID] = mapped_column(ForeignKey(Order.id), index=True)
    action: Mapped[ClaimAction] = mapped_column(
        enum_column(ClaimAction, "claim_action")
    )
    driver_id: Mapped[UUID] = mapped_column()
    recorded_by: Mapped[UUID] = mapped_column()
    reason: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
