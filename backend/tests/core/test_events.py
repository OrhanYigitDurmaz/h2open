# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for domain events and the event bus."""

import asyncio
import types
from datetime import UTC
from typing import ClassVar

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import DomainEvent, DuplicateEventTypeError, EventBus

SESSION = AsyncSession()
"""Handlers get a session; these tests never use it."""


class OrderConfirmed(DomainEvent):
    """Example event."""

    order_number: str


class RushOrderConfirmed(OrderConfirmed):
    """Example event subclass."""


class DeliveryCompleted(DomainEvent):
    """Unrelated example event."""

    event_type: ClassVar[str] = "test.delivery_completed"


def test_event_has_id_and_utc_timestamp() -> None:
    """Events get a unique ID and an aware UTC timestamp."""
    first = OrderConfirmed(order_number="S-1")
    second = OrderConfirmed(order_number="S-1")
    assert first.event_id != second.event_id
    assert first.occurred_at.tzinfo is UTC


def test_handlers_receive_their_event_type_and_subclasses() -> None:
    """Handlers get matching events (including subclasses), in order."""
    bus = EventBus()
    received: asyncio.Queue[str] = asyncio.Queue()

    async def on_order(event: OrderConfirmed, _session: AsyncSession) -> None:
        await received.put(f"order:{event.order_number}")

    async def on_delivery(_event: DeliveryCompleted, _session: AsyncSession) -> None:
        await received.put("delivery")

    bus.subscribe(OrderConfirmed, on_order)
    bus.subscribe(DeliveryCompleted, on_delivery)

    async def scenario() -> None:
        await bus.publish(OrderConfirmed(order_number="S-1"), SESSION)
        await bus.publish(RushOrderConfirmed(order_number="S-2"), SESSION)
        await bus.publish(DeliveryCompleted(), SESSION)

    asyncio.run(scenario())
    assert [received.get_nowait() for _ in range(received.qsize())] == [
        "order:S-1",
        "order:S-2",
        "delivery",
    ]


def test_publish_without_subscribers_does_nothing() -> None:
    """Publishing to an empty bus is fine."""
    asyncio.run(EventBus().publish(DeliveryCompleted(), SESSION))


def test_handler_errors_propagate() -> None:
    """A failing handler's exception reaches the publisher."""
    bus = EventBus()

    async def fail(_event: DeliveryCompleted, _session: AsyncSession) -> None:
        await asyncio.sleep(0)
        msg = "boom"
        raise RuntimeError(msg)

    bus.subscribe(DeliveryCompleted, fail)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(bus.publish(DeliveryCompleted(), SESSION))


def test_event_types_are_found_by_name() -> None:
    """Stored events are parsed back into their class by ``event_type``."""
    assert DomainEvent.type_named("test.delivery_completed") is DeliveryCompleted
    assert DomainEvent.type_named("test.nothing") is None


def test_event_type_names_are_unique() -> None:
    """Two classes cannot claim the same name."""

    def body(namespace: dict[str, object]) -> None:
        namespace["event_type"] = "test.delivery_completed"

    with pytest.raises(DuplicateEventTypeError, match=r"test\.delivery_completed"):
        _ = types.new_class("Again", (DomainEvent,), exec_body=body)
