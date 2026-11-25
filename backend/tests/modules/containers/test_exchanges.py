# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for container exchanges, balances and deposits."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from app.core.ids import new_id
from app.core.money import Money
from app.modules.containers import api
from app.modules.containers.api import (
    BalanceView,
    ContainerCount,
    ExchangeCreate,
    ExchangeResult,
    MovementKind,
    MovementView,
)
from app.modules.customers.api import CustomerView
from tests.modules.catalog.helpers import create_brand, create_container_type, try_

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response

    from app.core.db import Database
    from app.core.ids import EntityId

BALANCES = TypeAdapter(list[BalanceView])
MOVEMENTS = TypeAdapter(list[MovementView])


def tl(amount: int | str) -> Money:
    """An amount in TRY.

    Returns:
        The money.
    """
    return Money(amount=Decimal(amount), currency="TRY")


@dataclass(frozen=True)
class Shop:
    """Two brands' carboys, a customer, and a client to drive the API."""

    client: TestClient
    customer_id: EntityId
    carboy_a: EntityId
    carboy_b: EntityId

    def set_deposit(self, carboy: EntityId, amount: str, *, days_ago: int = 0) -> None:
        """Set a carboy's deposit, effective some days ago."""
        valid_from = datetime.now(UTC) - timedelta(days=days_ago, seconds=1)
        response = self.client.post(
            f"/catalog/container-types/{carboy}/deposits",
            json={"price": try_(amount), "valid_from": valid_from.isoformat()},
        )
        assert response.status_code == HTTPStatus.CREATED, response.text

    def post(
        self,
        delivered: dict[EntityId, int] | None = None,
        returned: dict[EntityId, int] | None = None,
        **extra: object,
    ) -> Response:
        """Send an exchange.

        Returns:
            The raw response.
        """

        def counts(items: dict[EntityId, int] | None) -> list[dict[str, object]]:
            return [
                {"container_type_id": str(type_id), "quantity": quantity}
                for type_id, quantity in (items or {}).items()
            ]

        body = {
            "customer_id": str(self.customer_id),
            "delivered": counts(delivered),
            "returned": counts(returned),
            **extra,
        }
        return self.client.post("/containers/exchanges", json=body)

    def exchange(
        self,
        delivered: dict[EntityId, int] | None = None,
        returned: dict[EntityId, int] | None = None,
        **extra: object,
    ) -> ExchangeResult:
        """Send an exchange that must succeed.

        Returns:
            The result.
        """
        response = self.post(delivered, returned, **extra)
        assert response.status_code == HTTPStatus.CREATED, response.text
        return ExchangeResult.model_validate_json(response.content)

    def balances(self) -> dict[EntityId, tuple[int, Money]]:
        """The customer's balances.

        Returns:
            Quantity and deposit held, per container type.
        """
        response = self.client.get(f"/containers/customers/{self.customer_id}/balances")
        return {
            balance.container_type_id: (balance.quantity, balance.deposit_held)
            for balance in BALANCES.validate_json(response.content)
        }

    def set_policy(self, policy: str) -> None:
        """Change the company's deposit refund policy."""
        response = self.client.patch(
            "/company/settings", json={"deposit_refund_policy": policy}
        )
        assert response.status_code == HTTPStatus.OK


@pytest.fixture
def shop(client: TestClient) -> Shop:
    """Brand A and Brand B carboys (deposits 200 and 150) and one customer.

    Returns:
        The shop.
    """
    carboy_a = create_container_type(client, create_brand(client, "Brand A"))
    carboy_b = create_container_type(client, create_brand(client, "Brand B"))
    response = client.post("/customers", json={"name": "Demir family"})
    customer_id = CustomerView.model_validate_json(response.content).id
    shop = Shop(client, customer_id, carboy_a.id, carboy_b.id)
    shop.set_deposit(carboy_a.id, "200")
    shop.set_deposit(carboy_b.id, "150")
    return shop


def test_first_delivery_charges_deposits(shop: Shop) -> None:
    """A new customer pays a deposit for every carboy they keep."""
    result = shop.exchange({shop.carboy_a: 2})
    assert result.deposit_charged == tl(400)
    assert result.deposit_refunded is None
    assert result.swapped == []
    [movement] = result.movements
    assert (movement.kind, movement.quantity, movement.balance_change) == (
        MovementKind.ISSUE,
        2,
        2,
    )
    assert movement.unit_deposit == tl(200)
    assert shop.balances() == {shop.carboy_a: (2, tl(400))}


def test_refill_swap_moves_no_money(shop: Shop) -> None:
    """Full for empty of the same brand: no movements, no deposit."""
    _ = shop.exchange({shop.carboy_a: 1})
    result = shop.exchange({shop.carboy_a: 1}, {shop.carboy_a: 1})
    assert result.swapped == [
        ContainerCount(container_type_id=shop.carboy_a, quantity=1)
    ]
    assert result.movements == []
    assert (result.deposit_charged, result.deposit_refunded) == (None, None)
    assert shop.balances() == {shop.carboy_a: (1, tl(200))}


def test_paid_amount_refunds_oldest_deposit_first(shop: Shop) -> None:
    """Deposits keep what was paid; returns refund the oldest first."""
    _ = shop.exchange({shop.carboy_a: 1})  # paid 200
    shop.set_deposit(shop.carboy_a, "250")
    _ = shop.exchange({shop.carboy_a: 2})  # paid 250 each
    assert shop.balances() == {shop.carboy_a: (3, tl(700))}

    result = shop.exchange(returned={shop.carboy_a: 3})
    assert [(m.unit_deposit, m.quantity) for m in result.movements] == [
        (tl(200), 1),
        (tl(250), 2),
    ]
    assert result.deposit_refunded == tl(700)
    assert shop.balances() == {}


def test_current_price_and_no_refund_policies(shop: Shop) -> None:
    """The company setting decides what a return refunds."""
    _ = shop.exchange({shop.carboy_a: 2})  # paid 200 each
    shop.set_deposit(shop.carboy_a, "300")

    shop.set_policy("current_price")
    result = shop.exchange(returned={shop.carboy_a: 1})
    assert result.deposit_refunded == tl(300)

    shop.set_policy("none")
    result = shop.exchange(returned={shop.carboy_a: 1})
    assert result.deposit_refunded == tl(0)
    assert shop.balances() == {}


def test_brand_mismatch_needs_an_override(shop: Shop) -> None:
    """Brand B empty for Brand A water is refused until staff override it."""
    _ = shop.exchange({shop.carboy_b: 1})  # paid 150 for a Brand B carboy
    response = shop.post({shop.carboy_a: 1}, {shop.carboy_b: 1})
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["code"] == "override_required"

    result = shop.exchange(
        {shop.carboy_a: 1},
        {shop.carboy_b: 1},
        override_reason="Regular customer, Brand B out of stock",
        note="Driver: Ali",
    )
    assert [
        (m.kind, m.container_type_id, m.balance_change) for m in result.movements
    ] == [
        (MovementKind.TRANSFER_OUT, shop.carboy_b, -1),
        (MovementKind.TRANSFER_IN, shop.carboy_a, 1),
    ]
    assert all(
        m.override_reason == "Regular customer, Brand B out of stock"
        and m.note == "Driver: Ali"
        for m in result.movements
    )
    assert (result.deposit_charged, result.deposit_refunded) == (None, None)
    # The 150 paid for the Brand B carboy now backs the Brand A one.
    assert shop.balances() == {shop.carboy_a: (1, tl(150))}


def test_partial_mismatch_settles_the_rest(shop: Shop) -> None:
    """With an override, one B empty covers one of two A fulls."""
    _ = shop.exchange({shop.carboy_b: 1})
    result = shop.exchange({shop.carboy_a: 2}, {shop.carboy_b: 1}, override_reason="ok")
    assert result.deposit_charged == tl(200)
    assert shop.balances() == {shop.carboy_a: (2, tl(350))}


def test_mismatch_across_several_types(client: TestClient, shop: Shop) -> None:
    """Empties of two other types can cover a single full; the rest is refunded."""
    carboy_c = create_container_type(client, create_brand(client, "Brand C")).id
    shop.set_deposit(carboy_c, "100")
    _ = shop.exchange({shop.carboy_b: 1, carboy_c: 1})
    result = shop.exchange(
        {shop.carboy_a: 1}, {shop.carboy_b: 1, carboy_c: 1}, override_reason="ok"
    )
    kinds = [(m.kind, m.container_type_id) for m in result.movements]
    first_empty, second_empty = sorted([shop.carboy_b, carboy_c])
    assert kinds == [
        (MovementKind.TRANSFER_OUT, first_empty),
        (MovementKind.TRANSFER_IN, shop.carboy_a),
        (MovementKind.RETURN, second_empty),
    ]
    assert result.deposit_charged is None
    assert shop.balances()[shop.carboy_a][0] == 1


def test_current_price_refund_needs_a_price(client: TestClient, shop: Shop) -> None:
    """A carboy type without a deposit price cannot be refunded at current price."""
    priceless = create_container_type(client, create_brand(client, "Brand C"))
    _ = shop.exchange({shop.carboy_b: 1})
    _ = shop.exchange({priceless.id: 1}, {shop.carboy_b: 1}, override_reason="ok")
    shop.set_policy("current_price")
    response = shop.post(returned={priceless.id: 1})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "no deposit price" in response.json()["detail"]


def test_business_rule_errors(client: TestClient, shop: Shop) -> None:
    """Unpriced or retired carboys can't be issued; you can't return more than held."""
    priceless = create_container_type(client, create_brand(client, "Brand C"))
    response = shop.post({priceless.id: 1})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "no deposit price" in response.json()["detail"]

    response = shop.post(returned={shop.carboy_a: 1})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "holds 0" in response.json()["detail"]

    _ = client.patch(
        f"/catalog/container-types/{shop.carboy_a}", json={"active": False}
    )
    response = shop.post({shop.carboy_a: 1})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "inactive" in response.json()["detail"]

    assert shop.post({new_id(): 1}).status_code == HTTPStatus.NOT_FOUND


def test_customer_must_exist_and_be_active(client: TestClient, shop: Shop) -> None:
    """Exchanges need an active customer; balances need an existing one."""
    _ = client.patch(f"/customers/{shop.customer_id}", json={"active": False})
    response = shop.post({shop.carboy_a: 1})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "inactive" in response.json()["detail"]

    unknown = f"/containers/customers/{new_id()}"
    assert client.get(f"{unknown}/balances").status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"{unknown}/movements").status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    "body",
    [
        {"delivered": [], "returned": []},
        {"delivered": [{"container_type_id": "X", "quantity": 1}]},
        {"returned": [{"container_type_id": str(new_id()), "quantity": 0}]},
        {
            "delivered": [
                {
                    "container_type_id": "00000000-0000-7000-8000-000000000001",
                    "quantity": 1,
                },
                {
                    "container_type_id": "00000000-0000-7000-8000-000000000001",
                    "quantity": 2,
                },
            ]
        },
        {
            "returned": [{"container_type_id": str(new_id()), "quantity": 1}],
            "override_reason": " ",
        },
    ],
)
def test_invalid_exchanges(shop: Shop, body: dict[str, object]) -> None:
    """Empty, malformed or duplicated lines and blank reasons are rejected."""
    response = shop.client.post(
        "/containers/exchanges", json={"customer_id": str(shop.customer_id), **body}
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_movement_history(shop: Shop) -> None:
    """The ledger lists every movement, newest first."""
    first = shop.exchange({shop.carboy_a: 1})
    second = shop.exchange(returned={shop.carboy_a: 1})
    response = shop.client.get(f"/containers/customers/{shop.customer_id}/movements")
    history = MOVEMENTS.validate_json(response.content)
    assert [m.exchange_id for m in history] == [second.exchange_id, first.exchange_id]
    assert [m.kind for m in history] == [MovementKind.RETURN, MovementKind.ISSUE]


def test_public_api(shop: Shop, database: Database) -> None:
    """Orders and deliveries will call the containers api directly."""

    async def deliver() -> list[BalanceView]:
        async with database.transaction() as session:
            data = ExchangeCreate(
                customer_id=shop.customer_id,
                delivered=[ContainerCount(container_type_id=shop.carboy_a, quantity=1)],
            )
            _ = await api.exchange(session, data)
            return await api.balances(session, shop.customer_id)

    [balance] = asyncio.run(deliver())
    assert (balance.container_type_id, balance.quantity) == (shop.carboy_a, 1)
