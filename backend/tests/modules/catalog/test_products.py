# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for products and prices."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.core.money import Money
from app.modules.catalog import api
from app.modules.catalog.api import ContainerLink, PriceView, ProductView
from tests.modules.catalog.helpers import (
    create_brand,
    create_container_type,
    create_product,
    try_,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

PRODUCTS = TypeAdapter(list[ProductView])
PRICES = TypeAdapter(list[PriceView])


def test_generic_product(client: TestClient) -> None:
    """Products need no brand and no container."""
    cups = create_product(
        client, {"sku": "CUP-50", "name": "Paper cups (50)", "vat_rate": "20"}
    )
    assert cups.brand_id is None
    assert cups.container is None
    assert cups.vat_rate == Decimal(20)
    assert cups.price is None


def test_pack_and_returnable_products(client: TestClient) -> None:
    """Packs are plain branded products; carboy water links its container."""
    brand = create_brand(client)
    carboy = create_container_type(client, brand)
    pack = create_product(
        client,
        {"sku": "A-500x12", "name": "Brand A 12 x 500 ml", "brand_id": str(brand.id)},
    )
    water = create_product(
        client,
        {
            "sku": "A-19L",
            "name": "Brand A 19 L",
            "brand_id": str(brand.id),
            "barcode": "8690000000001",
            "container": {"container_type_id": str(carboy.id), "quantity": 1},
        },
    )
    assert pack.container is None
    assert water.container == ContainerLink(container_type_id=carboy.id, quantity=1)
    assert water.barcode == "8690000000001"


def test_container_must_match_brand_and_be_active(client: TestClient) -> None:
    """Brand A water cannot go in Brand B carboys, nor in retired ones."""
    a = create_brand(client, "Brand A")
    b = create_brand(client, "Brand B")
    carboy_b = create_container_type(client, b)
    body: dict[str, object] = {
        "sku": "A-19L",
        "name": "Brand A 19 L",
        "vat_rate": "1",
        "container": {"container_type_id": str(carboy_b.id), "quantity": 1},
    }
    for brand_id in (str(a.id), None):
        response = client.post("/catalog/products", json={**body, "brand_id": brand_id})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "business_rule_violated"

    _ = client.patch(f"/catalog/container-types/{carboy_b.id}", json={"active": False})
    response = client.post("/catalog/products", json={**body, "brand_id": str(b.id)})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "inactive" in response.json()["detail"]


@pytest.mark.parametrize(
    "extra",
    [
        {"brand_id": str(new_id())},
        {"container": {"container_type_id": str(new_id()), "quantity": 1}},
    ],
)
def test_unknown_references(client: TestClient, extra: dict[str, object]) -> None:
    """Unknown brands or container types are not found."""
    body = {"sku": "X", "name": "X", "vat_rate": "1", **extra}
    assert client.post("/catalog/products", json=body).status_code == (
        HTTPStatus.NOT_FOUND
    )


@pytest.mark.parametrize(
    "invalid",
    [
        {"vat_rate": "101"},
        {"vat_rate": "-1"},
        {"vat_rate": "1.005"},
        {"sku": ""},
        {"container": {"container_type_id": str(new_id()), "quantity": 0}},
    ],
)
def test_invalid_products(client: TestClient, invalid: dict[str, object]) -> None:
    """Out-of-range VAT, blank SKUs and zero containers are rejected."""
    body = {"sku": "X", "name": "X", "vat_rate": "1", **invalid}
    assert client.post("/catalog/products", json=body).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )


def test_sku_and_barcode_are_unique(client: TestClient) -> None:
    """Two products cannot share a SKU or a barcode."""
    _ = create_product(client, {"sku": "A", "name": "A", "barcode": "111"})
    other = create_product(client, {"sku": "B", "name": "B"})
    same_sku = client.post(
        "/catalog/products", json={"sku": "A", "name": "A2", "vat_rate": "1"}
    )
    assert same_sku.status_code == HTTPStatus.CONFLICT
    same_barcode = client.patch(
        f"/catalog/products/{other.id}", json={"barcode": "111"}
    )
    assert same_barcode.status_code == HTTPStatus.CONFLICT


def test_update_product(client: TestClient) -> None:
    """Name, barcode, VAT and active flag change; omitted fields stay."""
    product = create_product(client, {"sku": "A", "name": "A", "barcode": "111"})
    url = f"/catalog/products/{product.id}"

    response = client.patch(url, json={"name": "A+", "vat_rate": "10", "active": False})
    updated = ProductView.model_validate_json(response.content)
    assert (updated.name, updated.vat_rate, updated.active, updated.barcode) == (
        "A+",
        Decimal(10),
        False,
        "111",
    )
    cleared = client.patch(url, json={"barcode": None})
    assert ProductView.model_validate_json(cleared.content).barcode is None
    assert client.patch(f"/catalog/products/{new_id()}", json={}).status_code == (
        HTTPStatus.NOT_FOUND
    )


def test_prices(client: TestClient) -> None:
    """Products show the price in effect now; history lists every change."""
    water = create_product(client, {"sku": "A-19L", "name": "Brand A 19 L"})
    cups = create_product(client, {"sku": "CUP", "name": "Cups"})
    url = f"/catalog/products/{water.id}/prices"
    now = datetime.now(UTC)
    for amount, valid_from in (
        ("90", now - timedelta(days=60)),
        ("100", now - timedelta(days=1)),
        ("120", now + timedelta(days=10)),
    ):
        body = {"price": try_(amount), "valid_from": valid_from.isoformat()}
        assert client.post(url, json=body).status_code == HTTPStatus.CREATED

    hundred = Money(amount=Decimal(100), currency="TRY")
    current = ProductView.model_validate_json(
        client.get(f"/catalog/products/{water.id}").content
    )
    assert current.price == hundred
    listed = PRODUCTS.validate_json(client.get("/catalog/products").content)
    assert {product.id: product.price for product in listed} == {
        water.id: hundred,
        cups.id: None,
    }
    history = PRICES.validate_json(client.get(url).content)
    assert [entry.price.amount for entry in history] == [120, 100, 90]

    starts_now = client.post(url, json={"price": try_("105")})
    assert starts_now.status_code == HTTPStatus.CREATED


def test_price_errors(client: TestClient) -> None:
    """Duplicate start moments conflict; unknown products are not found."""
    product = create_product(client, {"sku": "A", "name": "A"})
    url = f"/catalog/products/{product.id}/prices"
    body = {"price": try_("10"), "valid_from": "2026-01-01T00:00:00+00:00"}
    assert client.post(url, json=body).status_code == HTTPStatus.CREATED
    assert client.post(url, json=body).status_code == HTTPStatus.CONFLICT

    missing = f"/catalog/products/{new_id()}"
    assert client.get(missing).status_code == HTTPStatus.NOT_FOUND
    assert client.post(f"{missing}/prices", json=body).status_code == (
        HTTPStatus.NOT_FOUND
    )
    assert client.get(f"{missing}/prices").status_code == HTTPStatus.NOT_FOUND


def test_get_product_for_other_modules(client: TestClient, database: Database) -> None:
    """Other modules read products through the public api."""
    product = create_product(client, {"sku": "A", "name": "A"})

    async def get(product_id: object) -> ProductView:
        async with database.transaction() as session:
            return await api.get_product(
                session, product.id if product_id else new_id()
            )

    assert asyncio.run(get(product.id)) == product
    with pytest.raises(NotFoundError):
        _ = asyncio.run(get(None))
