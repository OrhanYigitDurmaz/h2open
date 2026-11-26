# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers that set up catalog data through the API."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from app.modules.catalog.api import BrandView, ContainerTypeView, ProductView

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.ids import EntityId


def create_brand(client: TestClient, name: str = "Brand A") -> BrandView:
    """Create a brand through the API.

    Returns:
        The brand.
    """
    response = client.post("/catalog/brands", json={"name": name})
    assert response.status_code == HTTPStatus.CREATED, response.text
    return BrandView.model_validate_json(response.content)


def create_container_type(
    client: TestClient, brand: BrandView, name: str = "19 L carboy"
) -> ContainerTypeView:
    """Create a container type through the API.

    Returns:
        The container type.
    """
    response = client.post(
        "/catalog/container-types", json={"brand_id": str(brand.id), "name": name}
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    return ContainerTypeView.model_validate_json(response.content)


def create_product(client: TestClient, body: dict[str, object]) -> ProductView:
    """Create a product through the API.

    Returns:
        The product.
    """
    response = client.post("/catalog/products", json={"vat_rate": "1", **body})
    assert response.status_code == HTTPStatus.CREATED, response.text
    return ProductView.model_validate_json(response.content)


def create_priced_product(
    client: TestClient, body: dict[str, object], price: str
) -> EntityId:
    """Create a product through the API and give it a price in TRY.

    Returns:
        The product's ID.
    """
    product = create_product(client, body)
    response = client.post(
        f"/catalog/products/{product.id}/prices", json={"price": try_(price)}
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    return product.id


def create_carboy_water(client: TestClient) -> tuple[EntityId, EntityId]:
    """Brand A, its 19 L carboy, and "Brand A 19 L" water in it at 100 TRY.

    Returns:
        The carboy's container type ID and the water's product ID.
    """
    brand = create_brand(client)
    carboy = create_container_type(client, brand)
    water = create_priced_product(
        client,
        {
            "sku": "A-19L",
            "name": "Brand A 19 L",
            "brand_id": str(brand.id),
            "container": {"container_type_id": str(carboy.id), "quantity": 1},
        },
        "100",
    )
    return carboy.id, water


def try_(amount: str) -> dict[str, str]:
    """A money value in TRY as JSON.

    Returns:
        The JSON body for the amount.
    """
    return {"amount": amount, "currency": "TRY"}
