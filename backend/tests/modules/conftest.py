# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for module tests."""

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.core.app import create_app
from app.core.events import EventBus
from app.main import MODULES

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.core.db import Database


@pytest.fixture
def client(database: Database) -> Iterator[TestClient]:
    """An HTTP client for an app with every module, on the test database.

    Yields:
        The client.
    """
    app = create_app(MODULES, event_bus=EventBus(), database=database)
    with TestClient(app) as client:
        yield client
