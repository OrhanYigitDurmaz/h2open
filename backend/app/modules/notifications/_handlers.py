# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Push messages sent when orders change. Private to this module.

Messages are data-only; the app decides what to show. Every message has
``type``, ``order_id`` and ``number``:

- ``pool_changed`` to drivers on shift: the pool gained or lost a delivery.
- ``order_changed`` / ``order_cancelled`` / ``order_completed`` to the
  driver holding a delivery, when someone else changed it.
- ``order_taken_back`` to a driver whose delivery staff took back.

And for calls the shop did not answer, ``incoming_call`` to drivers on
shift, with ``call_id``, ``number`` and ``customer`` (empty if unknown).
"""

from typing import TYPE_CHECKING

from app.core.push import PushError
from app.modules.identity import api as identity
from app.modules.notifications._push import PushReport, push
from app.modules.orders import api as orders
from app.modules.telephony import api as telephony

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.events import EventBus
    from app.core.ids import EntityId

CALL_TTL = 30
"""An incoming-call push is useless once the call stopped ringing."""
POOL_TTL = 300
"""Seconds a pool update is worth delivering; after that the app has
refreshed anyway."""
HOLDER_TTL = 3600

_FOR_HOLDER: dict[type[orders.OrderEvent], str] = {
    orders.OrderChanged: "order_changed",
    orders.OrderCancelled: "order_cancelled",
    orders.OrderCompleted: "order_completed",
}


def _data(kind: str, event: orders.OrderEvent) -> dict[str, str]:
    return {"type": kind, "order_id": str(event.order_id), "number": str(event.number)}


async def _to_drivers_on_shift(
    session: AsyncSession, data: dict[str, str]
) -> PushReport:
    targets = await identity.push_targets(
        session, identity.Role.DRIVER, on_shift_only=True
    )
    return await push(session, targets, data, ttl_seconds=POOL_TTL)


async def _to_user(
    session: AsyncSession, user_id: EntityId, data: dict[str, str]
) -> PushReport:
    targets = await identity.user_push_targets(session, user_id)
    return await push(session, targets, data, ttl_seconds=HOLDER_TTL)


def _changes_pool(event: orders.OrderEvent) -> bool:
    claims = (orders.DeliveryClaimed, orders.DeliveryReturnedToPool)
    return isinstance(event, claims) or event.in_pool


async def on_order_event(event: orders.OrderEvent, session: AsyncSession) -> None:
    """Tell the right phones about an order event.

    Raises:
        PushError: Some messages failed; the outbox retries the event.
    """
    reports: list[PushReport] = []
    if _changes_pool(event):
        reports.append(
            await _to_drivers_on_shift(session, _data("pool_changed", event))
        )
    kind = _FOR_HOLDER.get(type(event))
    holder = event.claimed_by
    if kind is not None and holder is not None and holder != event.actor_id:
        reports.append(await _to_user(session, holder, _data(kind, event)))
    if isinstance(event, orders.DeliveryReturnedToPool) and event.taken_back:
        data = _data("order_taken_back", event)
        reports.append(await _to_user(session, event.previous_driver, data))
    errors = [report.error for report in reports if report.failed]
    if errors:
        raise PushError("; ".join(error or "push failed" for error in errors))


async def on_drivers_rung(event: telephony.DriversRung, session: AsyncSession) -> None:
    """Wake the drivers' phones so the app can take the call.

    Raises:
        PushError: Some messages failed; the outbox retries the event.
    """
    targets = await identity.push_targets(
        session, identity.Role.DRIVER, on_shift_only=True
    )
    data = {
        "type": "incoming_call",
        "call_id": str(event.call_id),
        "number": event.caller_number or "",
        "customer": event.customer_name or "",
    }
    report = await push(session, targets, data, ttl_seconds=CALL_TTL)
    if report.failed:
        raise PushError(report.error or "push failed")


def subscribe(bus: EventBus) -> None:
    """Listen for order and call events."""
    bus.subscribe(orders.OrderEvent, on_order_event)
    bus.subscribe(telephony.DriversRung, on_drivers_rung)
