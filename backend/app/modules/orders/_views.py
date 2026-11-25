# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the orders module. Other modules get them via ``api``."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId
from app.core.money import Money


class Channel(StrEnum):
    """How the order reached us."""

    PHONE = "phone"
    COUNTER = "counter"


class Fulfilment(StrEnum):
    """How the customer gets the goods."""

    DELIVERY = "delivery"
    PICKUP = "pickup"


class OrderStatus(StrEnum):
    """Where an order is in its life."""

    OPEN = "open"
    """Taken, not yet handed over. Can still be changed."""
    COMPLETED = "completed"
    """Handed over; quantities, containers and totals are final."""
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    """How the customer pays."""

    CASH = "cash"
    CARD = "card"
    ON_ACCOUNT = "on_account"
    """Paid later (veresiye); needs a registered customer."""
    BANK_TRANSFER = "bank_transfer"


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class OrderLineView(_View):
    """One product on an order, priced as when it was ordered."""

    id: EntityId
    product_id: EntityId
    sku: str
    name: str
    unit_price: Money
    """VAT included."""
    vat_rate: Decimal
    container_type_id: EntityId | None
    container_quantity: int | None
    ordered_quantity: int
    """0 for products added at the door."""
    delivered_quantity: int | None
    """Set when the order is completed; may differ from what was ordered."""
    total: Money
    """Unit price x delivered (or, while open, ordered) quantity."""
    vat: Money
    """The VAT contained in ``total``."""


class ContainerReturnView(_View):
    """Empties of one container type expected back, and actually returned."""

    container_type_id: EntityId
    expected_quantity: int
    returned_quantity: int | None


class DeliveryAddressView(_View):
    """The delivery address, as it was when the order was taken."""

    address_id: EntityId | None
    address: str
    directions: str | None
    latitude: Decimal | None
    longitude: Decimal | None


class OrderView(_View):
    """An order with its lines, container returns and totals."""

    id: EntityId
    number: int
    customer_id: EntityId | None
    """``None`` for a walk-in sale."""
    channel: Channel
    fulfilment: Fulfilment
    status: OrderStatus
    payment_method: PaymentMethod
    address: DeliveryAddressView | None
    notes: str | None
    lines: list[OrderLineView]
    returns: list[ContainerReturnView]
    goods_total: Money | None
    vat_total: Money | None
    deposit_charged: Money | None
    """Set on completion: deposits for containers the customer keeps."""
    deposit_refunded: Money | None
    """Set on completion: deposits paid back for containers returned."""
    total: Money | None
    """Goods + deposit charged - deposit refunded: what to collect."""
    override_reason: str | None
    exchange_id: EntityId | None
    created_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
