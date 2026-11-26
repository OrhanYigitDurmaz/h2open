# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures for the order tests."""

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from app.modules.customers.api import CustomerView
from tests.modules.catalog.helpers import (
    create_brand,
    create_container_type,
    try_,
)
from tests.modules.orders.helpers import Shop, priced

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.fixture
def shop(client: TestClient) -> Shop:
    """The test shop.

    Returns:
        The shop.
    """
    brand = create_brand(client)
    carboy = create_container_type(client, brand)
    deposit = client.post(
        f"/catalog/container-types/{carboy.id}/deposits", json={"price": try_("200")}
    )
    assert deposit.status_code == HTTPStatus.CREATED
    container = {"container_type_id": str(carboy.id), "quantity": 1}
    water = priced(
        client,
        {
            "sku": "A-19L",
            "name": "Brand A 19 L",
            "brand_id": str(brand.id),
            "container": container,
        },
        "100",
    )
    pack = priced(
        client, {"sku": "A-12", "name": "12 x 500 ml", "vat_rate": "10"}, "60"
    )
    cups = priced(client, {"sku": "CUP", "name": "Cups", "vat_rate": "20"}, "20")
    response = client.post(
        "/customers",
        json={
            "name": "Demir family",
            "addresses": [
                {
                    "label": "Home",
                    "address": "Atatürk Cd. 1",
                    "directions": "3rd floor",
                },
                {"label": "Summer house", "address": "Sahil Yolu 7"},
            ],
        },
    )
    customer = CustomerView.model_validate_json(response.content)
    return Shop(client, carboy.id, water, pack, cups, customer)
