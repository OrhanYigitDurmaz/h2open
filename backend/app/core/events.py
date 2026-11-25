# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain events and the in-process event bus.

Modules announce facts ("order confirmed", "delivery completed") as events,
and other modules react to them without the publisher knowing who listens.

Delivery is in-process for now. Once the database exists, events will be
written to an outbox table in the same transaction as the change and
dispatched through this bus after commit, so none are lost on a crash.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.ids import EntityId, new_id

type EventHandler[E: DomainEvent] = Callable[[E], Awaitable[None]]


def _now() -> datetime:
    return datetime.now(UTC)


class DomainEvent(BaseModel):
    """Base class for events. Subclass it in a module's ``events.py``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    event_id: EntityId = Field(default_factory=new_id)
    occurred_at: datetime = Field(default_factory=_now)


class EventBus:
    """Routes published events to the handlers subscribed to their type."""

    def __init__(self) -> None:
        """Create a bus with no subscribers."""
        self._handlers: list[EventHandler[DomainEvent]] = []

    def subscribe[E: DomainEvent](
        self, event_type: type[E], handler: EventHandler[E]
    ) -> None:
        """Call ``handler`` for every published event of ``event_type``.

        Subclasses of ``event_type`` are delivered too.

        Args:
            event_type: The event class to listen for.
            handler: An async function that takes the event.
        """

        async def dispatch(event: DomainEvent) -> None:
            if isinstance(event, event_type):
                await handler(event)

        self._handlers.append(dispatch)

    async def publish(self, event: DomainEvent) -> None:
        """Deliver an event to its handlers, in subscription order.

        A handler's exception propagates to the publisher.

        Args:
            event: The event to deliver.
        """
        for handler in self._handlers:
            await handler(event)
