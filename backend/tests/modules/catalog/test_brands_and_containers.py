# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for brands, container types and deposits."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from app.core.ids import new_id
from app.core.money import Money
from app.modules.catalog import api
from app.modules.catalog.api import BrandView, ContainerTypeView, PriceView
from tests.modules.catalog.helpers import create_brand, create_container_type, try_

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

BRANDS = TypeAdapter(list[BrandView])
CONTAINER_TYPES = TypeAdapter(list[ContainerTypeView])
PRICES = TypeAdapter(list[PriceView])


def test_brands_are_created_listed_and_updated(client: TestClient) -> None:
    """Brands can be added, listed by name, renamed and deactivated."""
    b = create_brand(client, "Brand B")
    a = create_brand(client, "  Brand A  ")
    assert a.name == "Brand A"
    listed = BRANDS.validate_json(client.get("/catalog/brands").content)
    assert [brand.name for brand in listed] == ["Brand A", "Brand B"]

    response = client.patch(
        f"/catalog/brands/{b.id}", json={"name": "Brand C", "active": False}
    )
    assert response.status_code == HTTPStatus.OK
    assert BrandView.model_validate_json(response.content) == BrandView(
        id=b.id, name="Brand C", active=False
    )
    unchanged = client.patch(f"/catalog/brands/{b.id}", json={})
    assert BrandView.model_validate_json(unchanged.content).name == "Brand C"


def test_brand_names_are_unique(client: TestClient) -> None:
    """A second brand with a taken name is a conflict, on create and rename."""
    _ = create_brand(client, "Brand A")
    b = create_brand(client, "Brand B")
    response = client.post("/catalog/brands", json={"name": "Brand A"})
    assert response.status_code == HTTPStatus.CONFLICT
    response = client.patch(f"/catalog/brands/{b.id}", json={"name": "Brand A"})
    assert response.status_code == HTTPStatus.CONFLICT


def test_brand_validation_and_missing(client: TestClient) -> None:
    """Blank names are rejected and unknown brands are not found."""
    assert client.post("/catalog/brands", json={"name": " "}).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    response = client.patch(f"/catalog/brands/{new_id()}", json={"active": False})
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["code"] == "not_found"


def test_container_types_belong_to_brands(client: TestClient) -> None:
    """Names are unique per brand; another brand may reuse a name."""
    a = create_brand(client, "Brand A")
    b = create_brand(client, "Brand B")
    carboy_a = create_container_type(client, a)
    carboy_b = create_container_type(client, b)
    assert (carboy_a.brand_id, carboy_b.brand_id) == (a.id, b.id)
    assert carboy_a.deposit is None

    duplicate = client.post(
        "/catalog/container-types", json={"brand_id": str(a.id), "name": "19 L carboy"}
    )
    assert duplicate.status_code == HTTPStatus.CONFLICT
    unknown_brand = client.post(
        "/catalog/container-types", json={"brand_id": str(new_id()), "name": "x"}
    )
    assert unknown_brand.status_code == HTTPStatus.NOT_FOUND


def test_container_types_are_updated(client: TestClient) -> None:
    """Container types can be renamed and deactivated."""
    carboy = create_container_type(client, create_brand(client))
    response = client.patch(
        f"/catalog/container-types/{carboy.id}",
        json={"name": "19 L PC carboy", "active": False},
    )
    updated = ContainerTypeView.model_validate_json(response.content)
    assert (updated.name, updated.active) == ("19 L PC carboy", False)
    unchanged = client.patch(f"/catalog/container-types/{carboy.id}", json={})
    assert ContainerTypeView.model_validate_json(unchanged.content) == updated
    missing = client.patch(f"/catalog/container-types/{new_id()}", json={})
    assert missing.status_code == HTTPStatus.NOT_FOUND


def test_deposit_history_and_scheduled_changes(client: TestClient) -> None:
    """The current deposit is the latest one already in effect."""
    brand = create_brand(client)
    carboy = create_container_type(client, brand)
    other = create_container_type(client, brand, "10 L carboy")
    url = f"/catalog/container-types/{carboy.id}/deposits"

    now = datetime.now(UTC)
    old = {"price": try_("150"), "valid_from": (now - timedelta(days=30)).isoformat()}
    current = {"price": try_("200")}
    future = {"price": try_("250"), "valid_from": (now + timedelta(days=7)).isoformat()}
    for body in (old, current, future):
        assert client.post(url, json=body).status_code == HTTPStatus.CREATED

    listed = CONTAINER_TYPES.validate_json(
        client.get("/catalog/container-types").content
    )
    deposits = {container.id: container.deposit for container in listed}
    assert deposits == {
        carboy.id: Money(amount=Decimal(200), currency="TRY"),
        other.id: None,
    }

    history = PRICES.validate_json(client.get(url).content)
    assert [entry.price.amount for entry in history] == [250, 200, 150]

    renamed = client.patch(f"/catalog/container-types/{carboy.id}", json={})
    assert ContainerTypeView.model_validate_json(renamed.content).deposit == Money(
        amount=Decimal(200), currency="TRY"
    )


def test_deposit_errors(client: TestClient) -> None:
    """Two deposits cannot start at the same moment; unknown types are 404."""
    carboy = create_container_type(client, create_brand(client))
    url = f"/catalog/container-types/{carboy.id}/deposits"
    body = {"price": try_("200"), "valid_from": "2026-01-01T00:00:00+03:00"}
    assert client.post(url, json=body).status_code == HTTPStatus.CREATED
    assert client.post(url, json=body).status_code == HTTPStatus.CONFLICT

    naive = {"price": try_("200"), "valid_from": "2026-01-01T00:00:00"}
    assert client.post(url, json=naive).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    negative = {"price": try_("-1")}
    assert client.post(url, json=negative).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )

    missing = f"/catalog/container-types/{new_id()}/deposits"
    assert client.post(missing, json=body).status_code == HTTPStatus.NOT_FOUND
    assert client.get(missing).status_code == HTTPStatus.NOT_FOUND


def test_get_deposit_at_a_moment(client: TestClient, database: Database) -> None:
    """Other modules can look up the deposit in effect at any moment."""
    carboy = create_container_type(client, create_brand(client))
    url = f"/catalog/container-types/{carboy.id}/deposits"
    body = {"price": try_("200"), "valid_from": "2026-06-01T00:00:00+00:00"}
    assert client.post(url, json=body).status_code == HTTPStatus.CREATED

    async def deposit_at(moment: datetime) -> Money | None:
        async with database.transaction() as session:
            return await api.get_deposit(session, carboy.id, moment)

    assert asyncio.run(deposit_at(datetime(2026, 5, 31, tzinfo=UTC))) is None
    assert asyncio.run(deposit_at(datetime(2026, 6, 1, tzinfo=UTC))) == Money(
        amount=Decimal(200), currency="TRY"
    )
