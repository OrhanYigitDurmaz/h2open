# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The transactional outbox: events are stored with the change, sent after.

A service calls :func:`publish` inside its transaction. The event is a row
in ``outbox.events`` and becomes visible only if the transaction commits;
a ``NOTIFY`` sent in the same transaction wakes the dispatcher right after
commit. The dispatcher hands each event to the bus in a transaction of its
own and marks it handled there, so:

- an event whose change rolled back is never seen;
- a crash before an event is handled just means it is handled after restart;
- a failing handler is retried with growing delays, then parked as failed.

Delivery is at least once: a handler that talks to the outside world (a
push message) may run again after a failure, so it must tolerate repeats.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

import psycopg
from sqlalchemy import DateTime, Index, MetaData, String, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import module_metadata
from app.core.events import DomainEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db import Database
    from app.core.events import EventBus

CHANNEL = "outbox"
"""The Postgres NOTIFY channel that wakes the dispatcher."""

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base for the outbox table."""

    metadata: ClassVar[MetaData] = module_metadata("outbox")


class OutboxEvent(Base):
    """An event waiting to be handled, handled, or given up on."""

    __tablename__: str = "events"
    __table_args__: tuple[Index] = (
        Index(
            "ix_events_pending",
            "next_attempt_at",
            postgresql_where=text("handled_at IS NULL AND failed_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    """The event's own ID; UUIDv7, so ordering by it is ordering by time."""
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Set when retries ran out; the event stays for someone to look at."""
    last_error: Mapped[str | None] = mapped_column(String(2000))


METADATA = Base.metadata


class UnnamedEventError(TypeError):
    """An event without an ``event_type`` cannot be stored."""

    def __init__(self, event: DomainEvent) -> None:
        """Build the error message.

        Args:
            event: The event.
        """
        super().__init__(f"{type(event).__name__} has no event_type")


async def publish(session: AsyncSession, event: DomainEvent) -> None:
    """Store an event to be handled once the caller's transaction commits.

    Args:
        session: The caller's session; the event commits or rolls back
            with the caller's changes.
        event: The event.

    Raises:
        UnnamedEventError: The event class has no ``event_type``.
    """
    name = type(event).__dict__.get("event_type")
    if not isinstance(name, str):
        raise UnnamedEventError(event)
    session.add(
        OutboxEvent(
            id=event.event_id,
            event_type=name,
            payload=event.model_dump(mode="json"),
            created_at=event.occurred_at,
            next_attempt_at=event.occurred_at,
        )
    )
    _ = await session.execute(select(func.pg_notify(CHANNEL, "")))


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How often and how patiently a failing event is retried."""

    max_attempts: int = 10
    first_delay: timedelta = timedelta(seconds=2)
    max_delay: timedelta = timedelta(minutes=5)

    def delay(self, attempts: int) -> timedelta:
        """The wait before the next try, doubling each time.

        Args:
            attempts: Tries made so far.

        Returns:
            The delay.
        """
        return min(self.first_delay * (1 << (attempts - 1)), self.max_delay)


class Dispatcher:
    """Hands stored events to the bus, one transaction per event."""

    def __init__(
        self,
        database: Database,
        bus: EventBus,
        *,
        retry: RetryPolicy | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        """Set up a dispatcher. Nothing runs until :meth:`run` or :meth:`drain`.

        Args:
            database: Where the outbox is.
            bus: Where events are delivered.
            retry: How failures are retried.
            poll_interval: Seconds between checks when no NOTIFY arrives,
                which also picks up retries that have come due.
        """
        self._database: Database = database
        self._bus: EventBus = bus
        self._retry: RetryPolicy = retry or RetryPolicy()
        self._poll_interval: float = poll_interval

    async def handle_next(self) -> bool:
        """Handle the oldest event that is due, if any.

        Several dispatchers may run at once: each locks the row it works on
        and skips rows others have locked.

        Returns:
            Whether there was an event to handle.
        """
        async with self._database.transaction() as session:
            row = await session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.handled_at.is_(None),
                    OutboxEvent.failed_at.is_(None),
                    OutboxEvent.next_attempt_at <= _now(),
                )
                .order_by(OutboxEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return False
            await self._handle(session, row)
            return True

    async def _handle(self, session: AsyncSession, row: OutboxEvent) -> None:
        event_class = DomainEvent.type_named(row.event_type)
        try:
            # A savepoint: a failing handler's writes are undone, but the
            # retry bookkeeping below still commits.
            async with session.begin_nested():
                if event_class is not None:
                    event = event_class.model_validate(row.payload)
                    await self._bus.publish(event, session)
        except Exception as error:
            logger.exception("handling event %s (%s) failed", row.id, row.event_type)
            row.attempts += 1
            row.last_error = repr(error)[:2000]
            if row.attempts >= self._retry.max_attempts:
                row.failed_at = _now()
            else:
                row.next_attempt_at = _now() + self._retry.delay(row.attempts)
        else:
            row.handled_at = _now()

    async def drain(self) -> int:
        """Handle every event that is due now.

        Returns:
            How many events were handled (or tried).
        """
        count = 0
        while await self.handle_next():
            count += 1
        return count

    async def run(self) -> None:
        """Dispatch until cancelled, woken by NOTIFY or the poll interval."""
        url = self._database.engine.url.set(drivername="postgresql")
        conninfo = url.render_as_string(hide_password=False)
        async with await psycopg.AsyncConnection.connect(
            conninfo, autocommit=True
        ) as listener:
            _ = await listener.execute(f"LISTEN {CHANNEL}")
            while True:
                _ = await self.drain()
                async for _notify in listener.notifies(
                    timeout=self._poll_interval, stop_after=1
                ):
                    pass


async def run_forever(dispatcher: Dispatcher, *, pause: float = 5.0) -> None:
    """Keep a dispatcher running, restarting it if the database goes away.

    Args:
        dispatcher: The dispatcher.
        pause: Seconds to wait before reconnecting.
    """
    while True:
        try:
            await dispatcher.run()
        except OSError, psycopg.Error:
            logger.exception("outbox dispatcher lost the database; retrying")
            await asyncio.sleep(pause)
