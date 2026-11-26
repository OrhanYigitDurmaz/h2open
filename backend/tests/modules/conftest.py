# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for module tests."""

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.core.app import create_app
from app.core.events import EventBus
from app.core.outbox import Dispatcher, RetryPolicy
from app.main import MODULES
from app.modules.identity.api import Role
from tests.modules.auth import bearer, login, make_user

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.core.db import Database


@pytest.fixture
def event_bus() -> EventBus:
    """The bus the app's modules subscribe to.

    Returns:
        A new bus.
    """
    return EventBus()


@pytest.fixture
def dispatcher(database: Database, event_bus: EventBus) -> Dispatcher:
    """Hands outbox events to the app's bus when a test calls ``drain``.

    Returns:
        The dispatcher; failed events are retried right away.
    """
    return Dispatcher(database, event_bus, retry=RetryPolicy(first_delay=timedelta(0)))


@pytest.fixture
def client(database: Database, event_bus: EventBus) -> Iterator[TestClient]:
    """An HTTP client for the whole app, logged in as an admin.

    Events are not dispatched in the background; use ``dispatcher``.

    Yields:
        The client.
    """
    app = create_app(
        MODULES, event_bus=event_bus, database=database, dispatch_events=False
    )
    with TestClient(app) as client:
        _ = make_user(database, "admin", {Role.ADMIN})
        client.headers.update(bearer(login(client, "admin")))
        yield client
