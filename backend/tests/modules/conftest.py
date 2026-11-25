# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for module tests."""

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.core.app import create_app
from app.core.events import EventBus
from app.main import MODULES
from app.modules.identity.api import Role
from tests.modules.auth import bearer, login, make_user

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.core.db import Database


@pytest.fixture
def client(database: Database) -> Iterator[TestClient]:
    """An HTTP client for the whole app, logged in as an admin.

    Yields:
        The client.
    """
    app = create_app(MODULES, event_bus=EventBus(), database=database)
    with TestClient(app) as client:
        _ = make_user(database, "admin", {Role.ADMIN})
        client.headers.update(bearer(login(client, "admin")))
        yield client
