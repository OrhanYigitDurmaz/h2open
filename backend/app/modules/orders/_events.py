# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Events the orders module publishes. Other modules get them via ``api``."""

from typing import ClassVar

from app.core.events import DomainEvent
from app.core.ids import EntityId
from app.modules.orders._views import Fulfilment


class OrderEvent(DomainEvent):
    """Something happened to an order."""

    order_id: EntityId
    number: int
    fulfilment: Fulfilment
    claimed_by: EntityId | None
    """The driver holding the delivery at the time, if any."""
    actor_id: EntityId
    """Who did it."""

    @property
    def in_pool(self) -> bool:
        """Whether the order is (or was, just before this) an unclaimed delivery.

        Returns:
            True for unclaimed deliveries.
        """
        return self.fulfilment is Fulfilment.DELIVERY and self.claimed_by is None


class OrderPlaced(OrderEvent):
    """A new order was taken."""

    event_type: ClassVar[str] = "orders.order_placed"


class OrderChanged(OrderEvent):
    """An open order's lines, address, payment or notes changed."""

    event_type: ClassVar[str] = "orders.order_changed"


class OrderCancelled(OrderEvent):
    """An open order was cancelled."""

    event_type: ClassVar[str] = "orders.order_cancelled"


class OrderCompleted(OrderEvent):
    """An order was handed over."""

    event_type: ClassVar[str] = "orders.order_completed"


class DeliveryClaimed(OrderEvent):
    """A driver took a delivery from the pool; ``claimed_by`` is them."""

    event_type: ClassVar[str] = "orders.delivery_claimed"


class DeliveryReturnedToPool(OrderEvent):
    """A delivery went back to the pool; ``claimed_by`` is now ``None``."""

    event_type: ClassVar[str] = "orders.delivery_returned_to_pool"

    previous_driver: EntityId
    taken_back: bool
    """True if staff took it away; False if the driver released it."""
    reason: str | None
