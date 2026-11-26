# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Products and stock helpers shared by the inventory and purchasing tests."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from app.modules.inventory.api import ItemKind, MovementView, StockLevelView
from tests.modules.catalog.helpers import (
    create_brand,
    create_container_type,
    create_product,
    try_,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.ids import EntityId

LEVELS = TypeAdapter(list[StockLevelView])
MOVEMENTS = TypeAdapter(list[MovementView])


@dataclass(frozen=True)
class Goods:
    """A Brand A carboy and two priced products."""

    client: TestClient
    carboy: EntityId
    water: EntityId
    """Brand A 19 L in a returnable carboy, 100 TRY, 1 % VAT."""
    cups: EntityId
    """Paper cups, 20 TRY, 20 % VAT; no container."""

    def level(self, kind: ItemKind, item_id: EntityId) -> int:
        """Stock on hand of one item; zero if it never had any.

        Returns:
            The quantity.
        """
        levels = LEVELS.validate_json(self.client.get("/inventory/stock").content)
        for level in levels:
            if (level.kind, level.item_id) == (kind, item_id):
                return level.quantity
        return 0

    def water_level(self) -> int:
        """Full Brand A carboys on hand.

        Returns:
            The quantity.
        """
        return self.level(ItemKind.PRODUCT, self.water)

    def empties_level(self) -> int:
        """Empty Brand A carboys on hand.

        Returns:
            The quantity.
        """
        return self.level(ItemKind.EMPTY, self.carboy)

    def movements(self, **params: str) -> list[MovementView]:
        """The stock ledger, filtered.

        Returns:
            The ledger lines, newest first.
        """
        response = self.client.get("/inventory/movements", params=params)
        assert response.status_code == HTTPStatus.OK, response.text
        return MOVEMENTS.validate_json(response.content)

    def settings(self, **changes: object) -> None:
        """Change company settings."""
        response = self.client.patch("/company/settings", json=changes)
        assert response.status_code == HTTPStatus.OK


def _priced(client: TestClient, body: dict[str, object], price: str) -> EntityId:
    product = create_product(client, body)
    response = client.post(
        f"/catalog/products/{product.id}/prices", json={"price": try_(price)}
    )
    assert response.status_code == HTTPStatus.CREATED
    return product.id


def make_goods(client: TestClient) -> Goods:
    """Set up the products.

    Returns:
        The goods.
    """
    brand = create_brand(client)
    carboy = create_container_type(client, brand)
    container = {"container_type_id": str(carboy.id), "quantity": 1}
    water = _priced(
        client,
        {
            "sku": "A-19L",
            "name": "Brand A 19 L",
            "brand_id": str(brand.id),
            "container": container,
        },
        "100",
    )
    cups = _priced(client, {"sku": "CUP", "name": "Cups", "vat_rate": "20"}, "20")
    return Goods(client, carboy.id, water, cups)
