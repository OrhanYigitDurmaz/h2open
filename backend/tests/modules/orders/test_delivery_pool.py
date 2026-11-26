# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the delivery pool: shifts, claiming, releasing and alerts."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter
from sqlalchemy import text

from app.modules.identity.api import Role, UserView
from app.modules.orders.api import (
    ClaimAction,
    ClaimEventView,
    OrderAlerts,
    OrderStatus,
    OrderView,
)
from tests.modules.auth import bearer, login, make_user
from tests.modules.orders.helpers import Shop, ok

if TYPE_CHECKING:
    from httpx2 import Response

    from app.core.db import Database
    from app.core.ids import EntityId

ORDERS = TypeAdapter(list[OrderView])
CLAIMS = TypeAdapter(list[ClaimEventView])
POOLED_AGO = "UPDATE orders.orders SET pooled_at = now() - :age WHERE id = :id"
CLAIMED_AGO = "UPDATE orders.orders SET claimed_at = now() - :age WHERE id = :id"


@dataclass(frozen=True)
class Crew:
    """Two drivers and a staff member, logged in."""

    shop: Shop
    database: Database
    ali: dict[str, str]
    veli: dict[str, str]
    staff: dict[str, str]
    ali_id: EntityId

    def post(self, url: str, headers: dict[str, str], **body: object) -> Response:
        """Send a POST as someone.

        Returns:
            The raw response.
        """
        return self.shop.client.post(url, json=body, headers=headers)

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        """Send a GET, as the admin unless headers are given.

        Returns:
            The raw response.
        """
        return self.shop.client.get(url, headers=headers)

    def shift(self, headers: dict[str, str], *, on: bool) -> Response:
        """Start or end a shift.

        Returns:
            The raw response.
        """
        return self.shop.client.put(
            "/auth/me/shift", json={"on_shift": on}, headers=headers
        )

    def claim(self, order: OrderView, headers: dict[str, str]) -> Response:
        """Claim an order.

        Returns:
            The raw response.
        """
        return self.post(f"/orders/{order.id}/claim", headers)

    def pool(self) -> list[OrderView]:
        """The pool.

        Returns:
            The orders in it.
        """
        return ORDERS.validate_json(self.get("/orders/pool").content)

    def mine(self, headers: dict[str, str]) -> list[OrderView]:
        """A driver's orders.

        Returns:
            The orders they hold.
        """
        return ORDERS.validate_json(self.get("/orders/mine", headers).content)

    def sql(self, statement: str, **params: object) -> None:
        """Run SQL against the test database, e.g. to age orders."""

        async def run() -> None:
            async with self.database.transaction() as session:
                _ = await session.execute(text(statement), params)

        asyncio.run(run())


@pytest.fixture
def crew(shop: Shop, database: Database) -> Crew:
    """Drivers Ali and Veli (on shift) and staff member Ayşe.

    Returns:
        The crew.
    """
    ali = make_user(database, "ali", {Role.DRIVER})
    _ = make_user(database, "veli", {Role.DRIVER})
    _ = make_user(database, "ayse", {Role.STAFF})
    client = shop.client
    crew = Crew(
        shop,
        database,
        ali=bearer(login(client, "ali")),
        veli=bearer(login(client, "veli")),
        staff=bearer(login(client, "ayse")),
        ali_id=ali.id,
    )
    for driver in (crew.ali, crew.veli):
        assert crew.shift(driver, on=True).status_code == HTTPStatus.OK
    return crew


def test_shifts(crew: Crew) -> None:
    """Drivers start and end shifts; others have none."""
    response = crew.shift(crew.ali, on=False)
    assert UserView.model_validate_json(response.content).on_shift is False
    assert crew.shift(crew.staff, on=True).status_code == HTTPStatus.FORBIDDEN

    off_shift = crew.claim(crew.shop.delivery({crew.shop.water: 1}), crew.ali)
    assert off_shift.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert off_shift.json()["detail"] == "start your shift to claim deliveries"


def test_admins_end_forgotten_shifts(crew: Crew) -> None:
    """Admins end shifts; losing the driver role or deactivation ends one too."""
    users = TypeAdapter(list[UserView]).validate_json(crew.get("/users").content)
    ids = {user.username: user.id for user in users}
    client = crew.shop.client

    ended = client.patch(f"/users/{ids['veli']}", json={"on_shift": False})
    assert UserView.model_validate_json(ended.content).on_shift is False
    started = client.patch(f"/users/{ids['veli']}", json={"on_shift": True})
    assert UserView.model_validate_json(started.content).on_shift is True
    staff = client.patch(f"/users/{ids['ayse']}", json={"on_shift": True})
    assert staff.status_code == HTTPStatus.UNPROCESSABLE_CONTENT

    demoted = client.patch(f"/users/{ids['veli']}", json={"roles": ["staff"]})
    assert UserView.model_validate_json(demoted.content).on_shift is False
    gone = client.patch(f"/users/{ids['ali']}", json={"active": False})
    assert UserView.model_validate_json(gone.content).on_shift is False


def test_claim_and_deliver(crew: Crew) -> None:
    """A delivery waits in the pool, a driver claims it and delivers it."""
    shop = crew.shop
    order = shop.delivery({shop.pack: 1})
    assert order.waiting_since == order.created_at
    assert [o.id for o in crew.pool()] == [order.id]

    claimed = ok(crew.claim(order, crew.ali))
    assert (claimed.claimed_by, claimed.waiting_since) == (crew.ali_id, None)
    assert claimed.claimed_at is not None
    assert crew.pool() == []
    assert [o.id for o in crew.mine(crew.ali)] == [order.id]
    assert crew.mine(crew.veli) == []
    response = crew.shop.client.get("/orders", params={"claimed_by": str(crew.ali_id)})
    assert [o.id for o in ORDERS.validate_json(response.content)] == [order.id]

    others = crew.post(f"/orders/{order.id}/complete", crew.veli)
    assert others.status_code == HTTPStatus.FORBIDDEN
    assert (
        others.json()["detail"] == f"claim order #{order.number} before completing it"
    )
    done = ok(crew.post(f"/orders/{order.id}/complete", crew.ali))
    assert (done.status, done.completed_by, done.claimed_by) == (
        OrderStatus.COMPLETED,
        crew.ali_id,
        crew.ali_id,
    )
    assert crew.mine(crew.ali) == []


def test_one_driver_holds_several(crew: Crew) -> None:
    """Drivers take as many deliveries as they like, oldest shown first."""
    shop = crew.shop
    first, second = shop.delivery({shop.water: 1}), shop.delivery({shop.pack: 1})
    assert [o.id for o in crew.pool()] == [first.id, second.id]
    _ = ok(crew.claim(second, crew.ali))
    _ = ok(crew.claim(first, crew.ali))
    assert [o.id for o in crew.mine(crew.ali)] == [second.id, first.id]


def test_claims_that_fail(crew: Crew) -> None:
    """Taken, closed, pickup and unknown orders cannot be claimed."""
    shop = crew.shop
    order = shop.delivery({shop.water: 1})
    _ = ok(crew.claim(order, crew.ali))
    mine = crew.claim(order, crew.ali)
    assert mine.status_code == HTTPStatus.CONFLICT
    assert mine.json()["detail"] == f"order #{order.number} is already held by you"
    theirs = crew.claim(order, crew.veli)
    assert theirs.status_code == HTTPStatus.CONFLICT
    assert "held by another driver" in theirs.json()["detail"]

    pickup = ok(shop.walk_in({shop.cups: 1}))
    response = crew.claim(pickup, crew.ali)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "is a pickup" in response.json()["detail"]

    cancelled = shop.delivery({shop.pack: 1})
    _ = ok(
        crew.post(f"/orders/{cancelled.id}/cancel", crew.staff, reason="no one home")
    )
    assert crew.claim(cancelled, crew.ali).status_code == HTTPStatus.CONFLICT
    assert crew.claim(cancelled, crew.staff).status_code == HTTPStatus.FORBIDDEN
    missing = crew.post(f"/orders/{shop.customer.id}/claim", crew.ali)
    assert missing.status_code == HTTPStatus.NOT_FOUND


def test_release_and_take_back(crew: Crew) -> None:
    """Drivers put deliveries back; staff take them back; all is logged."""
    shop = crew.shop
    order = shop.delivery({shop.water: 1})
    _ = ok(crew.claim(order, crew.ali))
    url = f"/orders/{order.id}"

    assert crew.post(f"{url}/release", crew.veli).status_code == HTTPStatus.FORBIDDEN
    released = ok(crew.post(f"{url}/release", crew.ali, reason="van is full"))
    assert (released.claimed_by, released.claimed_at) == (None, None)
    assert released.waiting_since is not None
    assert [o.id for o in crew.pool()] == [order.id]

    _ = ok(crew.claim(order, crew.veli))
    assert crew.post(f"{url}/take-back", crew.veli, reason="x").status_code == (
        HTTPStatus.FORBIDDEN
    )
    assert crew.post(f"{url}/take-back", crew.staff).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    back = ok(crew.post(f"{url}/take-back", crew.staff, reason="Veli went home"))
    assert back.claimed_by is None
    again = crew.post(f"{url}/take-back", crew.staff, reason="again")
    assert again.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert again.json()["detail"] == f"no driver holds order #{order.number}"

    history = CLAIMS.validate_json(crew.get(f"{url}/claims").content)
    assert [(e.action, e.reason) for e in history] == [
        (ClaimAction.CLAIMED, None),
        (ClaimAction.RELEASED, "van is full"),
        (ClaimAction.CLAIMED, None),
        (ClaimAction.TAKEN_BACK, "Veli went home"),
    ]
    assert history[0].driver_id == history[1].driver_id == crew.ali_id
    assert history[3].driver_id == history[2].driver_id != history[3].recorded_by
    assert crew.get(f"/orders/{shop.customer.id}/claims").status_code == (
        HTTPStatus.NOT_FOUND
    )


def test_staff_complete_any_order(crew: Crew) -> None:
    """Staff can complete a delivery nobody claimed, e.g. picked up after all."""
    order = crew.shop.delivery({crew.shop.pack: 1})
    done = ok(crew.post(f"/orders/{order.id}/complete", crew.staff))
    assert (done.claimed_by, done.waiting_since) == (None, None)
    assert crew.pool() == []


def test_alerts(crew: Crew) -> None:
    """Deliveries waiting or held past the company's limits are flagged."""
    shop = crew.shop
    waiting = shop.delivery({shop.water: 1})
    held = shop.delivery({shop.pack: 1})
    _ = shop.delivery({shop.cups: 1})
    _ = ok(crew.claim(held, crew.ali))

    def alerts() -> OrderAlerts:
        return OrderAlerts.model_validate_json(crew.get("/orders/alerts").content)

    assert alerts() == OrderAlerts(unclaimed=[], uncompleted=[])
    crew.sql(POOLED_AGO, age=timedelta(minutes=16), id=waiting.id)
    crew.sql(CLAIMED_AGO, age=timedelta(minutes=119), id=held.id)
    late = alerts()
    assert ([o.id for o in late.unclaimed], late.uncompleted) == ([waiting.id], [])

    shop.settings(uncompleted_alert_minutes=60, unclaimed_alert_minutes=30)
    late = alerts()
    assert ([o.id for o in late.unclaimed], [o.id for o in late.uncompleted]) == (
        [],
        [held.id],
    )
