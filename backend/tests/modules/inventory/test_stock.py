# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for stock levels: sales, empties, adjustments and counts."""

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from app.core.ids import new_id
from app.modules.identity.api import Role
from app.modules.inventory.api import ItemKind, MovementReason, MovementView
from app.modules.orders.api import OrderView
from tests.modules.auth import bearer, login, make_user
from tests.modules.inventory.helpers import LEVELS, MOVEMENTS, Goods, make_goods

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response

    from app.core.db import Database
    from app.core.ids import EntityId

TWO, THREE, FIVE = 2, 3, 5


@pytest.fixture
def goods(client: TestClient) -> Goods:
    """The test products.

    Returns:
        The goods.
    """
    return make_goods(client)


def sell(goods: Goods, lines: dict[EntityId, int]) -> Response:
    """Ring up and complete a walk-in sale; carboys are swapped for empties.

    Returns:
        The completion response.
    """
    response = goods.client.post(
        "/orders",
        json={
            "channel": "counter",
            "fulfilment": "pickup",
            "lines": [{"product_id": str(p), "quantity": q} for p, q in lines.items()],
            "payment_method": "cash",
        },
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    order = OrderView.model_validate_json(response.content)
    return goods.client.post(f"/orders/{order.id}/complete", json={})


def adjust(goods: Goods, change: int, **extra: object) -> Response:
    """Adjust the water stock.

    Returns:
        The raw response.
    """
    body = {
        "kind": "product",
        "item_id": str(goods.water),
        "change": change,
        "reason": "two leaking",
        **extra,
    }
    return goods.client.post("/inventory/adjustments", json=body)


def count(goods: Goods, *items: tuple[ItemKind, EntityId, int]) -> Response:
    """Record a stock count.

    Returns:
        The raw response.
    """
    return goods.client.post(
        "/inventory/counts",
        json={
            "items": [
                {"kind": kind, "item_id": str(item_id), "counted": counted}
                for kind, item_id, counted in items
            ],
            "note": "Monday count",
        },
    )


def test_a_sale_moves_goods_out_and_empties_in(goods: Goods) -> None:
    """Completing an order takes goods out; the swapped empties come in."""
    assert goods.client.get("/inventory/stock").json() == []
    response = sell(goods, {goods.water: TWO, goods.cups: 1})
    assert response.status_code == HTTPStatus.OK, response.text
    order = OrderView.model_validate_json(response.content)

    assert goods.water_level() == -TWO
    assert goods.level(ItemKind.PRODUCT, goods.cups) == -1
    assert goods.empties_level() == TWO

    sale = goods.movements(source_id=str(order.id))
    assert {(m.item_id, m.change) for m in sale} == {
        (goods.water, -TWO),
        (goods.cups, -1),
    }
    assert {m.reason for m in sale} == {MovementReason.SALE}
    assert sale[0].note == f"Order #{order.number}"
    [empties] = goods.movements(reason="customer_return")
    assert (empties.kind, empties.item_id, empties.change) == (
        ItemKind.EMPTY,
        goods.carboy,
        TWO,
    )
    assert empties.source_id == order.exchange_id


def test_stock_filters(goods: Goods) -> None:
    """Stock and the ledger can be narrowed down."""
    _ = sell(goods, {goods.water: 1})
    empties = LEVELS.validate_json(
        goods.client.get("/inventory/stock", params={"kind": "empty"}).content
    )
    assert [(level.item_id, level.quantity) for level in empties] == [(goods.carboy, 1)]
    assert [m.kind for m in goods.movements(kind="empty")] == [ItemKind.EMPTY]
    assert [m.change for m in goods.movements(item_id=str(goods.water))] == [-1]
    assert len(goods.movements(limit="1")) == 1


def test_negative_stock_can_be_forbidden(goods: Goods) -> None:
    """With the setting off, a sale beyond stock is refused and nothing moves."""
    goods.settings(negative_stock_allowed=False)
    response = sell(goods, {goods.water: TWO})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == (
        "not enough stock of 'Brand A 19 L': 0 on hand, 2 needed"
    )
    assert goods.movements() == []

    assert count(goods, (ItemKind.PRODUCT, goods.water, TWO)).status_code == (
        HTTPStatus.CREATED
    )
    assert sell(goods, {goods.water: TWO}).status_code == HTTPStatus.OK
    assert goods.water_level() == 0


def test_adjustments(goods: Goods) -> None:
    """Admins correct stock with a reason; the setting applies to removals."""
    response = adjust(goods, -TWO)
    assert response.status_code == HTTPStatus.CREATED
    movement = MovementView.model_validate_json(response.content)
    assert (movement.reason, movement.change, movement.note) == (
        MovementReason.ADJUSTMENT,
        -TWO,
        "two leaking",
    )
    assert goods.water_level() == -TWO

    goods.settings(negative_stock_allowed=False)
    assert adjust(goods, FIVE).status_code == HTTPStatus.CREATED
    refused = adjust(goods, -FIVE)
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "3 on hand, 5 needed" in refused.json()["detail"]
    empties = adjust(goods, -1, kind="empty", item_id=str(goods.carboy))
    assert empties.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "'empty 19 L carboy'" in empties.json()["detail"]
    assert goods.water_level() == THREE


def test_bad_adjustments(goods: Goods) -> None:
    """Zero changes, missing reasons and unknown items are refused."""
    assert adjust(goods, 0).status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert adjust(goods, 1, reason=" ").status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    assert adjust(goods, 1, item_id=str(new_id())).status_code == (HTTPStatus.NOT_FOUND)


def test_counts_record_only_differences(goods: Goods) -> None:
    """A count sets each level and logs the difference; matches log nothing."""
    _ = sell(goods, {goods.water: TWO})
    response = count(
        goods,
        (ItemKind.PRODUCT, goods.water, FIVE),
        (ItemKind.EMPTY, goods.carboy, TWO),
        (ItemKind.PRODUCT, goods.cups, 0),
    )
    assert response.status_code == HTTPStatus.CREATED
    [movement] = MOVEMENTS.validate_json(response.content)
    assert (movement.item_id, movement.change, movement.note) == (
        goods.water,
        FIVE + TWO,
        "Monday count",
    )
    assert (goods.water_level(), goods.empties_level()) == (FIVE, TWO)
    assert goods.level(ItemKind.PRODUCT, goods.cups) == 0


def test_bad_counts(goods: Goods) -> None:
    """Counts are whole, non-negative, listed once, of known items."""
    water = (ItemKind.PRODUCT, goods.water, 1)
    assert count(goods, water, water).status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert count(goods, (ItemKind.PRODUCT, goods.water, -1)).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    assert count(goods).status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert count(goods, (ItemKind.EMPTY, new_id(), 1)).status_code == (
        HTTPStatus.NOT_FOUND
    )


def test_only_admins_correct_stock(goods: Goods, database: Database) -> None:
    """Staff can see stock but not adjust or count it."""
    _ = make_user(database, "ayse", {Role.STAFF})
    headers = bearer(login(goods.client, "ayse"))
    assert goods.client.get("/inventory/stock", headers=headers).status_code == (
        HTTPStatus.OK
    )
    for url in ("/inventory/adjustments", "/inventory/counts"):
        response = goods.client.post(url, json={}, headers=headers)
        assert response.status_code == HTTPStatus.FORBIDDEN, url
