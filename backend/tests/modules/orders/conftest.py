# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for the order tests."""

from typing import TYPE_CHECKING

import pytest

from tests.modules.orders.helpers import Shop, make_shop

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.fixture
def shop(client: TestClient) -> Shop:
    """The test shop.

    Returns:
        The shop.
    """
    return make_shop(client)
