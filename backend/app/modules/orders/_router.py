# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the orders module. Private to this module."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.identity import api as identity
from app.modules.orders import _service
from app.modules.orders._schemas import (
    OrderCancel,
    OrderCompletion,
    OrderCreate,
    OrderSearch,
    OrderUpdate,
    Release,
    TakeBack,
)
from app.modules.orders._views import ClaimEventView, OrderAlerts, OrderView

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    dependencies=[Depends(identity.current_actor)],
)


@router.post("", status_code=HTTPStatus.CREATED)
async def create_order(
    session: SessionDep, actor: identity.CurrentActor, data: OrderCreate
) -> OrderView:
    """Take a new order (phone or counter, delivery or pickup).

    Returns:
        The open order.
    """
    return await _service.create_order(session, data, actor.id)


@router.get("")
async def list_orders(
    session: SessionDep, search: Annotated[OrderSearch, Query()]
) -> list[OrderView]:
    """List orders, newest first, optionally filtered.

    Returns:
        The matching orders.
    """
    return await _service.list_orders(session, search)


@router.get("/pool")
async def pool(session: SessionDep) -> list[OrderView]:
    """Deliveries waiting for a driver, longest-waiting first.

    Returns:
        The unclaimed open deliveries.
    """
    return await _service.pool(session)


@router.get("/mine")
async def mine(session: SessionDep, actor: identity.CurrentActor) -> list[OrderView]:
    """The deliveries you hold, in the order you claimed them.

    Returns:
        Your open deliveries.
    """
    return await _service.held(session, actor.id)


@router.get("/alerts")
async def alerts(session: SessionDep) -> OrderAlerts:
    """Deliveries waiting or held too long, for the POS to flag.

    Returns:
        The late deliveries; thresholds are company settings.
    """
    return await _service.alerts(session)


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
    session: SessionDep,
    actor: identity.CurrentActor,
    order_id: EntityId,
    data: OrderCompletion,
) -> OrderView:
    """Record what was handed over: final quantities, empties and payment.

    Returns:
        The completed order with final totals. A 409 with code
        ``override_required`` means empties of another brand were returned;
        repeat with ``override_reason`` to accept them.
    """
    return await _service.complete_as(session, order_id, data, actor)


@router.post("/{order_id}/cancel")
async def cancel_order(
    session: SessionDep,
    actor: identity.CurrentActor,
    order_id: EntityId,
    data: OrderCancel,
) -> OrderView:
    """Cancel an open order.

    Returns:
        The cancelled order.
    """
    return await _service.cancel_order(session, order_id, data, actor.id)


@router.post("/{order_id}/claim")
async def claim(
    session: SessionDep, actor: identity.CurrentActor, order_id: EntityId
) -> OrderView:
    """Take a delivery from the pool. Drivers on shift only.

    Returns:
        The order, now yours. A 409 means another driver got it first.
    """
    return await _service.claim(session, order_id, actor)


@router.post("/{order_id}/release")
async def release(
    session: SessionDep,
    actor: identity.CurrentActor,
    order_id: EntityId,
    data: Release,
) -> OrderView:
    """Put a delivery you hold back in the pool.

    Returns:
        The order, back in the pool.
    """
    return await _service.release(session, order_id, data, actor)


@router.post("/{order_id}/take-back")
async def take_back(
    session: SessionDep,
    actor: identity.CurrentActor,
    order_id: EntityId,
    data: TakeBack,
) -> OrderView:
    """Take a delivery away from its driver, back into the pool. Staff only.

    Returns:
        The order, back in the pool.
    """
    return await _service.take_back(session, order_id, data, actor)


@router.get("/{order_id}/claims")
async def claims(session: SessionDep, order_id: EntityId) -> list[ClaimEventView]:
    """Who has held a delivery, oldest first.

    Returns:
        The claim history.
    """
    return await _service.claim_history(session, order_id)
