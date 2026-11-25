# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the orders module. Private to this module."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.orders import _service
from app.modules.orders._schemas import (
    OrderCancel,
    OrderCompletion,
    OrderCreate,
    OrderSearch,
    OrderUpdate,
)
from app.modules.orders._views import OrderView

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", status_code=HTTPStatus.CREATED)
async def create_order(session: SessionDep, data: OrderCreate) -> OrderView:
    """Take a new order (phone or counter, delivery or pickup).

    Returns:
        The open order.
    """
    return await _service.create_order(session, data)


@router.get("")
async def list_orders(
    session: SessionDep, search: Annotated[OrderSearch, Query()]
) -> list[OrderView]:
    """List orders, newest first, optionally filtered.

    Returns:
        The matching orders.
    """
    return await _service.list_orders(session, search)


@router.get("/{order_id}")
async def get_order(session: SessionDep, order_id: EntityId) -> OrderView:
    """Get one order.

    Returns:
        The order.
    """
    return await _service.get_order(session, order_id)


@router.patch("/{order_id}")
async def update_order(
    session: SessionDep, order_id: EntityId, data: OrderUpdate
) -> OrderView:
    """Change an open order.

    Returns:
        The updated order.
    """
    return await _service.update_order(session, order_id, data)


@router.post("/{order_id}/complete")
async def complete_order(
    session: SessionDep, order_id: EntityId, data: OrderCompletion
) -> OrderView:
    """Record what was handed over: final quantities, empties and payment.

    Returns:
        The completed order with final totals. A 409 with code
        ``override_required`` means empties of another brand were returned;
        repeat with ``override_reason`` to accept them.
    """
    return await _service.complete_order(session, order_id, data)


@router.post("/{order_id}/cancel")
async def cancel_order(
    session: SessionDep, order_id: EntityId, data: OrderCancel
) -> OrderView:
    """Cancel an open order.

    Returns:
        The cancelled order.
    """
    return await _service.cancel_order(session, order_id, data)
