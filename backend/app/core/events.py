# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain events and the in-process event bus.

Modules announce facts ("order placed", "delivery claimed") as events, and
other modules react to them without the publisher knowing who listens.

Services never call the bus directly: they write events to the outbox
(:mod:`app.core.outbox`) in the same transaction as the change. After
commit, the outbox dispatcher hands each event to the bus, so handlers
only ever see changes that really happened, and none are lost on a crash.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, override

from pydantic import BaseModel, ConfigDict, Field

from app.core.ids import EntityId, new_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

type EventHandler[E: DomainEvent] = Callable[[E, AsyncSession], Awaitable[None]]
"""Handles one event. The session is the dispatcher's transaction: whatever
the handler writes commits together with marking the event as handled."""


def _now() -> datetime:
    return datetime.now(UTC)


class DuplicateEventTypeError(TypeError):
    """Two event classes claim the same ``event_type`` name."""

    def __init__(self, name: str) -> None:
        """Build the error message.

        Args:
            name: The name used twice.
        """
        super().__init__(f"event type {name!r} is defined twice")


class DomainEvent(BaseModel):
    """Base class for events.

    Concrete events set ``event_type`` to a stable name such as
    ``"orders.delivery_claimed"``. It is stored in the outbox, so renaming
    the class later does not break events that are still waiting.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    event_type: ClassVar[str]
    _registry: ClassVar[dict[str, type[DomainEvent]]] = {}

    event_id: EntityId = Field(default_factory=new_id)
    occurred_at: datetime = Field(default_factory=_now)

    @classmethod
    @override
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        name = cls.__dict__.get("event_type")
        if isinstance(name, str):
            if name in DomainEvent._registry:
                raise DuplicateEventTypeError(name)
            DomainEvent._registry[name] = cls

    @staticmethod
    def type_named(name: str) -> type[DomainEvent] | None:
        """Find the event class for a stored ``event_type`` name.

        Args:
            name: The name.

        Returns:
            The class, or ``None`` if no loaded module defines it.
        """
        return DomainEvent._registry.get(name)


class EventBus:
    """Routes events to the handlers subscribed to their type."""

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
            handler: An async function that takes the event and a session.
        """

        async def dispatch(event: DomainEvent, session: AsyncSession) -> None:
            if isinstance(event, event_type):
                await handler(event, session)

        self._handlers.append(dispatch)

    async def publish(self, event: DomainEvent, session: AsyncSession) -> None:
        """Deliver an event to its handlers, in subscription order.

        A handler's exception propagates to the publisher.

        Args:
            event: The event to deliver.
            session: The transaction the handlers work in.
        """
        for handler in self._handlers:
            await handler(event, session)
