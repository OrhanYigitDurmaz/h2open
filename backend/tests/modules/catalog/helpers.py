# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers that set up catalog data through the API."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from app.modules.catalog.api import BrandView, ContainerTypeView, ProductView

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


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


def try_(amount: str) -> dict[str, str]:
    """A money value in TRY as JSON.

    Returns:
        The JSON body for the amount.
    """
    return {"amount": amount, "currency": "TRY"}
