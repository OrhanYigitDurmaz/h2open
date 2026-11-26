# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the orders module.

Deliveries will read orders through here and complete them via
:func:`complete_order` when the driver hands them over.
"""

from typing import TYPE_CHECKING

from app.modules.orders import _service
from app.modules.orders._schemas import LineIn, OrderCompletion
from app.modules.orders._views import (
    Channel,
    ClaimAction,
    ClaimEventView,
    ContainerReturnView,
    DeliveryAddressView,
    Fulfilment,
    OrderAlerts,
    OrderLineView,
    OrderStatus,
    OrderView,
    PaymentMethod,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId

__all__ = [
    "Channel",
    "ClaimAction",
    "ClaimEventView",
    "ContainerReturnView",
    "DeliveryAddressView",
    "Fulfilment",
    "LineIn",
    "OrderAlerts",
    "OrderCompletion",
    "OrderLineView",
    "OrderStatus",
    "OrderView",
    "PaymentMethod",
    "complete_order",
    "get_order",
]


async def get_order(session: AsyncSession, order_id: EntityId) -> OrderView:
    """Look up one order.

    Args:
        session: The caller's database session.
        order_id: The order.

    Returns:
        The order.
    """
    return await _service.get_order(session, order_id)


async def complete_order(
    session: AsyncSession, order_id: EntityId, data: OrderCompletion, actor_id: EntityId
) -> OrderView:
    """Record what was handed over and finalise the order.

    Args:
        session: The caller's database session.
        order_id: The order.
        data: What was actually delivered, returned and paid.
        actor_id: The user handing it over (usually the driver).

    Returns:
        The completed order.
    """
    return await _service.complete_order(session, order_id, data, actor_id)
