# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the transactional outbox and its dispatcher."""

import asyncio
import contextlib
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.app import Module, create_app
from app.core.db import Database
from app.core.events import DomainEvent, EventBus
from app.core.ids import new_id
from app.core.outbox import (
    Dispatcher,
    OutboxEvent,
    RetryPolicy,
    UnnamedEventError,
    publish,
    run_forever,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

NO_DELAY = RetryPolicy(max_attempts=2, first_delay=timedelta(0))
TWO = 2


class Ping(DomainEvent):
    """A test event."""

    event_type: ClassVar[str] = "test.outbox_ping"

    n: int


class Pong(DomainEvent):
    """Another test event, published by a handler."""

    event_type: ClassVar[str] = "test.outbox_pong"


class Unnamed(DomainEvent):
    """An event that forgot its name."""


class HandlerError(RuntimeError):
    """A handler failing."""


async def send(database: Database, *events: DomainEvent) -> None:
    """Publish events in one committed transaction."""
    async with database.transaction() as session:
        for event in events:
            await publish(session, event)


async def rows(database: Database) -> list[OutboxEvent]:
    """Every stored event, oldest first.

    Returns:
        The rows.
    """
    async with database.transaction() as session:
        return list(await session.scalars(select(OutboxEvent).order_by(OutboxEvent.id)))


def recording_bus() -> tuple[EventBus, list[int]]:
    """A bus that records the ``n`` of every Ping.

    Returns:
        The bus and the list it records into.
    """
    bus, seen = EventBus(), list[int]()

    async def on_ping(event: Ping, _session: AsyncSession) -> None:
        await asyncio.sleep(0)
        seen.append(event.n)

    bus.subscribe(Ping, on_ping)
    return bus, seen


def test_events_are_handled_once_after_commit(database: Database) -> None:
    """Committed events reach handlers in order, exactly once."""
    bus, seen = recording_bus()
    dispatcher = Dispatcher(database, bus)

    async def scenario() -> None:
        await send(database, Ping(n=1), Ping(n=2))
        assert await dispatcher.drain() == TWO
        assert await dispatcher.drain() == 0
        [first, second] = await rows(database)
        assert first.handled_at is not None
        assert (first.payload["n"], second.payload["n"]) == (1, 2)

    asyncio.run(scenario())
    assert seen == [1, 2]


def test_rolled_back_events_are_never_seen(database: Database) -> None:
    """An event published in a failed transaction disappears with it."""
    bus, seen = recording_bus()

    async def scenario() -> None:
        with contextlib.suppress(HandlerError):
            async with database.transaction() as session:
                await publish(session, Ping(n=1))
                raise HandlerError
        assert await Dispatcher(database, bus).drain() == 0

    asyncio.run(scenario())
    assert seen == []


def test_events_need_a_name(database: Database) -> None:
    """Only events with an ``event_type`` can be stored."""

    async def scenario() -> None:
        async with database.transaction() as session:
            await publish(session, Unnamed())

    with pytest.raises(UnnamedEventError, match="Unnamed has no event_type"):
        asyncio.run(scenario())


def test_failures_are_retried_then_parked(database: Database) -> None:
    """A failing handler's writes are undone; it is retried, then given up."""
    bus = EventBus()

    async def fail(_event: Ping, session: AsyncSession) -> None:
        await publish(session, Pong())
        msg = "FCM is down"
        raise HandlerError(msg)

    bus.subscribe(Ping, fail)
    dispatcher = Dispatcher(database, bus, retry=NO_DELAY)

    async def scenario() -> None:
        await send(database, Ping(n=1))
        assert await dispatcher.handle_next()
        [row] = await rows(database)
        assert (row.attempts, row.handled_at, row.failed_at) == (1, None, None)
        assert row.last_error == "HandlerError('FCM is down')"

        assert await dispatcher.handle_next()
        [row] = await rows(database)
        assert row.attempts == TWO
        assert row.failed_at is not None
        assert await dispatcher.drain() == 0

    asyncio.run(scenario())


def test_retries_wait_longer_each_time() -> None:
    """Delays double from two seconds up to five minutes."""
    policy = RetryPolicy()
    assert [policy.delay(n).total_seconds() for n in (1, 2, 3)] == [2, 4, 8]
    assert policy.delay(20) == timedelta(minutes=5)


def test_events_nobody_knows_are_just_marked(database: Database) -> None:
    """An event type no loaded module defines any more is skipped."""

    async def scenario() -> None:
        async with database.transaction() as session:
            now = datetime.now(UTC)
            session.add(
                OutboxEvent(
                    id=new_id(),
                    event_type="test.removed_long_ago",
                    payload={},
                    created_at=now,
                    next_attempt_at=now,
                )
            )
        assert await Dispatcher(database, EventBus()).drain() == 1
        [row] = await rows(database)
        assert row.handled_at is not None

    asyncio.run(scenario())


def test_notify_wakes_the_dispatcher(database: Database) -> None:
    """A running dispatcher handles new events at once, not at the next poll."""
    bus = EventBus()
    seen: asyncio.Queue[int] = asyncio.Queue()

    async def on_ping(event: Ping, _session: AsyncSession) -> None:
        await seen.put(event.n)

    bus.subscribe(Ping, on_ping)

    async def scenario() -> None:
        task = asyncio.create_task(Dispatcher(database, bus, poll_interval=60).run())
        await send(database, Ping(n=1))
        assert await asyncio.wait_for(seen.get(), timeout=5) == 1
        # Let it finish that pass and go back to waiting. Polling is a
        # minute away, so only the NOTIFY can wake it in time now.
        await asyncio.sleep(0.3)
        await send(database, Ping(n=2))
        assert await asyncio.wait_for(seen.get(), timeout=5) == TWO
        _ = task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_dispatcher_reconnects(
    database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    """When the database is unreachable, the dispatcher keeps trying."""
    unreachable = Database(
        create_async_engine(database.engine.url.set(host="127.0.0.1", port=1))
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            run_forever(Dispatcher(unreachable, EventBus()), pause=0.01)
        )
        await asyncio.sleep(0.2)
        _ = task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await unreachable.dispose()

    with caplog.at_level(logging.ERROR, logger="app.core.outbox"):
        asyncio.run(scenario())
    assert "lost the database" in caplog.text


def test_the_app_dispatches_while_running(database: Database) -> None:
    """By default the app runs the dispatcher for as long as it runs."""
    bus = EventBus()
    handled = threading.Event()

    async def on_ping(_event: Ping, _session: AsyncSession) -> None:
        await asyncio.sleep(0)
        handled.set()

    bus.subscribe(Ping, on_ping)
    app = create_app([Module(name="demo")], event_bus=bus, database=database)
    with TestClient(app):
        asyncio.run(send(database, Ping(n=1)))
        assert handled.wait(timeout=5)
