# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for orders: taking, changing, completing and cancelling them."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from app.core.ids import new_id
from app.modules.customers.api import CustomerView
from app.modules.identity.api import Actor
from app.modules.orders import api
from app.modules.orders.api import OrderCompletion, OrderStatus, OrderView
from tests.modules.catalog.helpers import (
    create_brand,
    create_container_type,
    create_product,
    try_,
)
from tests.modules.orders.helpers import (
    Shop,
    error,
    lines_json,
    ok,
    returns_json,
    tl,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

ORDERS = TypeAdapter(list[OrderView])
TWO, THREE = 2, 3


def test_phone_order_for_a_new_customer(shop: Shop) -> None:
    """A first delivery charges deposits for the carboys the customer keeps."""
    order = shop.delivery({shop.water: 2, shop.pack: 1}, expected_returns=[])
    assert order.status is OrderStatus.OPEN
    assert order.number > 0
    assert order.address is not None
    assert (order.address.address, order.address.directions) == (
        "Atatürk Cd. 1",
        "3rd floor",
    )
    assert order.goods_total == tl("260")
    assert order.vat_total == tl("7.43")  # 200 at 1 % (1.98) + 60 at 10 % (5.45)
    assert order.returns == []
    assert (order.deposit_charged, order.total) == (None, tl("260"))

    done = ok(shop.complete(order))
    assert done.status is OrderStatus.COMPLETED
    assert done.completed_at is not None
    assert [line.delivered_quantity for line in done.lines] == [2, 1]
    assert done.deposit_charged == tl("400")
    assert done.total == tl("660")
    assert done.exchange_id is not None


def test_regular_refill_is_a_swap(shop: Shop) -> None:
    """By default an empty comes back for every carboy delivered."""
    shop.give_carboys(2)
    order = shop.delivery({shop.water: 2})
    assert [(r.container_type_id, r.expected_quantity) for r in order.returns] == [
        (shop.carboy, 2)
    ]
    done = ok(shop.complete(order))
    assert done.returns[0].returned_quantity == TWO
    assert (done.deposit_charged, done.deposit_refunded) == (None, None)
    assert done.total == tl("200")


def test_driver_adjusts_at_the_door(shop: Shop) -> None:
    """Actual quantities replace ordered ones; added items get today's price."""
    shop.give_carboys(2)
    order = shop.delivery({shop.water: 2, shop.pack: 1})
    done = ok(
        shop.complete(
            order,
            lines=lines_json({shop.water: 3, shop.cups: 1}),
            returned=returns_json({shop.carboy: 2}),
            payment_method="card",
        )
    )
    by_sku = {line.sku: line for line in done.lines}
    assert (by_sku["A-19L"].ordered_quantity, by_sku["A-19L"].delivered_quantity) == (
        2,
        3,
    )
    assert (by_sku["A-12"].ordered_quantity, by_sku["A-12"].delivered_quantity) == (
        1,
        0,
    )
    assert (by_sku["CUP"].ordered_quantity, by_sku["CUP"].delivered_quantity) == (0, 1)
    assert done.payment_method == "card"
    assert done.goods_total == tl("320")
    assert done.deposit_charged == tl("200")  # 3 delivered, 2 back: one new carboy
    assert done.total == tl("520")


def test_returning_fewer_empties_than_expected(shop: Shop) -> None:
    """A customer who keeps an extra carboy pays its deposit."""
    shop.give_carboys(1)
    order = shop.delivery({shop.water: 2})
    done = ok(shop.complete(order, returned=returns_json({shop.carboy: 1})))
    assert done.returns[0].expected_quantity == TWO
    assert done.returns[0].returned_quantity == 1
    assert done.deposit_charged == tl("200")


def test_refund_only_visit(shop: Shop) -> None:
    """A customer can hand back carboys for good; the total is negative."""
    shop.give_carboys(1)
    order = shop.delivery({}, expected_returns=returns_json({shop.carboy: 1}))
    done = ok(shop.complete(order))
    assert done.goods_total is None
    assert done.deposit_refunded == tl("200")
    assert done.total == tl("-200")


def test_other_brand_empty_needs_override(client: TestClient, shop: Shop) -> None:
    """Completing with another brand's empty asks for a staff override."""
    other = create_container_type(client, create_brand(client, "Brand B"))
    _ = client.post(
        f"/catalog/container-types/{other.id}/deposits", json={"price": try_("150")}
    )
    seeded = client.post(
        "/containers/exchanges",
        json={
            "customer_id": str(shop.customer.id),
            "delivered": returns_json({other.id: 1}),
        },
    )
    assert seeded.status_code == HTTPStatus.CREATED
    order = shop.delivery({shop.water: 1})
    body = {"returned": returns_json({other.id: 1})}
    assert (
        error(shop.complete(order, **body), HTTPStatus.CONFLICT) == "override_required"
    )
    done = ok(shop.complete(order, override_reason="Out of Brand B", **body))
    assert done.override_reason == "Out of Brand B"
    returns = {
        r.container_type_id: (r.expected_quantity, r.returned_quantity)
        for r in done.returns
    }
    assert returns == {shop.carboy: (1, 0), other.id: (0, 1)}
    assert done.deposit_charged is None


def test_walk_in_counter_sales(shop: Shop) -> None:
    """Walk-ins buy packs and swap same-brand carboys; deposits follow settings."""
    sale = ok(shop.walk_in({shop.pack: 2, shop.cups: 1}))
    assert sale.customer_id is None
    assert sale.address is None
    assert ok(shop.complete(sale)).total == tl("140")

    swap = ok(shop.walk_in({shop.water: 1}))
    assert ok(shop.complete(swap)).deposit_charged is None

    new_carboy = ok(shop.walk_in({shop.water: 1}, expected_returns=[]))
    response = shop.complete(new_carboy)
    assert error(response, HTTPStatus.UNPROCESSABLE_CONTENT) == "business_rule_violated"
    assert "register them" in response.json()["detail"]

    shop.settings(walk_in_deposits_allowed=True)
    assert ok(shop.complete(new_carboy)).deposit_charged == tl("200")

    refund = ok(shop.walk_in({}, expected_returns=returns_json({shop.carboy: 1})))
    response = shop.complete(refund)
    assert "deposit refund" in response.json()["detail"]


def test_walk_in_limits(shop: Shop) -> None:
    """Walk-ins can be switched off, and never buy on account."""
    response = shop.walk_in({shop.pack: 1}, payment_method="on_account")
    assert "veresiye" in response.json()["detail"]
    sale = ok(shop.walk_in({shop.pack: 1}))
    response = shop.complete(sale, payment_method="on_account")
    assert error(response, HTTPStatus.UNPROCESSABLE_CONTENT) == "business_rule_violated"

    shop.settings(walk_in_sales_enabled=False)
    response = shop.walk_in({shop.pack: 1})
    assert "walk-in sales are disabled" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"fulfilment": "delivery"},
        {"customer_id": None, "address_id": str(new_id())},
        {"lines": []},
        {
            "lines": [
                {"product_id": "00000000-0000-7000-8000-000000000001", "quantity": 1}
            ]
            * 2
        },
        {
            "expected_returns": [
                {
                    "container_type_id": "00000000-0000-7000-8000-000000000001",
                    "quantity": 1,
                }
            ]
            * 2
        },
        {"lines": [{"product_id": str(new_id()), "quantity": 0}]},
    ],
)
def test_invalid_orders(shop: Shop, body: dict[str, object]) -> None:
    """Deliveries need an address; orders need content; no duplicates."""
    base: dict[str, object] = {
        "customer_id": str(shop.customer.id),
        "channel": "phone",
        "fulfilment": "pickup",
        "lines": lines_json({shop.pack: 1}),
        "payment_method": "cash",
    }
    assert error(shop.order(**{**base, **body}), HTTPStatus.UNPROCESSABLE_CONTENT) == (
        "validation"
    )


def test_order_rules(client: TestClient, shop: Shop) -> None:
    """Addresses must be the customer's; customers and products must be usable."""
    stranger = client.post(
        "/customers", json={"name": "Other", "addresses": [{"address": "X"}]}
    )
    foreign = CustomerView.model_validate_json(stranger.content).addresses[0].id
    response = shop.order(
        customer_id=str(shop.customer.id),
        channel="phone",
        fulfilment="delivery",
        address_id=str(foreign),
        lines=lines_json({shop.pack: 1}),
        payment_method="cash",
    )
    assert error(response, HTTPStatus.NOT_FOUND) == "not_found"

    unpriced = create_product(client, {"sku": "NEW", "name": "New"})
    response = shop.walk_in({unpriced.id: 1})
    assert "not for sale" in response.json()["detail"]

    _ = client.patch(f"/customers/{shop.customer.id}", json={"active": False})
    with pytest.raises(AssertionError):
        _ = shop.delivery({shop.pack: 1})
    assert error(client.get(f"/orders/{new_id()}"), HTTPStatus.NOT_FOUND) == "not_found"


def test_update_open_order(shop: Shop) -> None:
    """Open orders can change; changing lines resets the expected swap."""
    order = shop.delivery({shop.water: 1}, notes="Ring twice")
    url = f"/orders/{order.id}"

    changed = ok(shop.client.patch(url, json={"lines": lines_json({shop.water: 3})}))
    assert changed.returns[0].expected_quantity == THREE
    changed = ok(
        shop.client.patch(
            url, json={"expected_returns": returns_json({shop.carboy: 1})}
        )
    )
    assert changed.returns[0].expected_quantity == 1
    changed = ok(shop.client.patch(url, json={"expected_returns": []}))
    assert changed.returns == []
    changed = ok(
        shop.client.patch(
            url,
            json={
                "payment_method": "on_account",
                "address_id": str(shop.customer.addresses[1].id),
                "notes": None,
            },
        )
    )
    assert changed.payment_method == "on_account"
    assert changed.address is not None
    assert changed.address.address == "Sahil Yolu 7"
    assert changed.notes is None
    assert ok(shop.client.patch(url, json={})) == changed

    pickup = ok(shop.walk_in({shop.pack: 1}))
    response = shop.client.patch(
        f"/orders/{pickup.id}", json={"address_id": str(new_id())}
    )
    assert "no delivery address" in response.json()["detail"]


def test_cancel_and_finality(shop: Shop) -> None:
    """Cancelled and completed orders can no longer change."""
    order = shop.delivery({shop.pack: 1})
    url = f"/orders/{order.id}"
    cancelled = ok(
        shop.client.post(f"{url}/cancel", json={"reason": "Customer called back"})
    )
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.cancel_reason == "Customer called back"
    assert cancelled.cancelled_at is not None
    for response in (
        shop.client.post(f"{url}/cancel", json={"reason": "again"}),
        shop.complete(order),
        shop.client.patch(url, json={}),
    ):
        assert error(response, HTTPStatus.CONFLICT) == "conflict"

    empty = shop.delivery({shop.pack: 1})
    response = shop.complete(empty, lines=[], returned=[])
    assert "cancel the order instead" in response.json()["detail"]


def test_parallel_completions_complete_once(shop: Shop) -> None:
    """A double-tapped "complete" takes stock and empties only once."""
    shop.give_carboys(2)
    order = shop.delivery({shop.water: 2, shop.cups: 1})
    tries = 4
    with ThreadPoolExecutor(tries) as pool:
        sent = [pool.submit(shop.complete, order) for _ in range(tries)]
    statuses = sorted(s.result().status_code for s in sent)
    assert statuses == [HTTPStatus.OK] + [HTTPStatus.CONFLICT] * (tries - 1)


def test_list_orders(shop: Shop) -> None:
    """Orders are listed newest first and can be filtered."""
    first = shop.delivery({shop.pack: 1})
    second = ok(shop.walk_in({shop.pack: 1}))
    _ = ok(shop.complete(second))

    def numbers(query: str) -> list[int]:
        response = shop.client.get(f"/orders?{query}")
        return [order.number for order in ORDERS.validate_json(response.content)]

    assert numbers("") == [second.number, first.number]
    assert numbers("status=open") == [first.number]
    assert numbers("fulfilment=pickup") == [second.number]
    assert numbers(f"customer_id={shop.customer.id}") == [first.number]
    assert numbers("limit=1") == [second.number]


def test_public_api(shop: Shop, database: Database) -> None:
    """Deliveries will complete orders through the public api."""
    order = shop.delivery({shop.pack: 1})
    me = Actor.model_validate_json(shop.client.get("/auth/me").content).id
    assert order.created_by == me

    async def complete() -> OrderView:
        async with database.transaction() as session:
            _ = await api.get_order(session, order.id)
            return await api.complete_order(session, order.id, OrderCompletion(), me)

    done = asyncio.run(complete())
    assert (done.status, done.completed_by) == (OrderStatus.COMPLETED, me)
