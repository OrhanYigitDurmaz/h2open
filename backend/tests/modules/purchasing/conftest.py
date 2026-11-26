# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for the purchasing tests."""

from typing import TYPE_CHECKING

import pytest

from tests.modules.inventory.helpers import make_goods
from tests.modules.purchasing.helpers import Purchasing, create_supplier

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.fixture
def buy(client: TestClient) -> Purchasing:
    """Products and a supplier to buy them from.

    Returns:
        The purchasing helper.
    """
    goods = make_goods(client)
    return Purchasing(goods, create_supplier(goods))
