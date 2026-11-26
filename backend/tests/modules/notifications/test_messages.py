# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the push messages sent when orders change."""

import asyncio
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from app.core import outbox
from app.core.ids import new_id
from app.core.push import PushError, PushStatus, SendOutcome, get_sender, use_sender
from app.modules.identity import api as identity
from app.modules.identity.api import LoginResult, Role
from app.modules.notifications import api as notifications
from app.modules.notifications.api import PushReport
from app.modules.telephony.api import DriversRung
from tests.modules.auth import CREDENTIAL, bearer, make_user
from tests.modules.orders.helpers import Shop, make_shop, ok

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from fastapi.testclient import TestClient

    from app.core.db import Database
    from app.core.outbox import Dispatcher
    from app.modules.orders.api import OrderView

type Sent = tuple[str, str]
"""(phone token, message type)."""


@dataclass
class FakeSender:
    """Records messages instead of sending; phones can be made to fail."""

    sent: list[Sent] = field(default_factory=list)
    dead: set[str] = field(default_factory=set)
    broken: set[str] = field(default_factory=set)

    @property
    def status(self) -> PushStatus:
        """Pretend to be configured.

        Returns:
            The status.
        """
        return PushStatus(configured=True, project_id="fake", problem=None)

    async def send(
        self, token: str, data: Mapping[str, str], *, ttl_seconds: int
    ) -> SendOutcome:
        """Record a message.

        Returns:
            The outcome for this phone.

        Raises:
            PushError: The phone is in ``broken``.
        """
        await asyncio.sleep(0)
        assert ttl_seconds > 0
        if token in self.broken:
            msg = f"{token} unreachable"
            raise PushError(msg)
        if token in self.dead:
            return SendOutcome.UNREGISTERED
        self.sent.append((token, data["type"]))
        return SendOutcome.SENT

    def take(self) -> list[Sent]:
        """What was sent since the last call, sorted.

        Returns:
            The messages.
        """
        sent, self.sent = sorted(self.sent), []
        return sent


@pytest.fixture
def phones() -> Iterator[FakeSender]:
    """Replace Firebase with a fake for one test.

    Yields:
        The fake.
    """
    fake = FakeSender()
    use_sender(fake)
    yield fake
    use_sender(None)


@dataclass(frozen=True)
class Crew:
    """Drivers Ali (on shift) and Veli (off shift), staff Ayşe; all with phones."""

    shop: Shop
    outbox: Dispatcher
    ali: dict[str, str]
    veli: dict[str, str]
    ayse: dict[str, str]

    def post(self, url: str, who: dict[str, str], **body: object) -> OrderView:
        """Send a POST that must succeed.

        Returns:
            The order.
        """
        return ok(self.shop.client.post(url, json=body, headers=who))

    def deliver(self) -> OrderView:
        """Take a delivery order for a pack of water.

        Returns:
            The order.
        """
        return self.shop.delivery({self.shop.pack: 1})

    def flush(self) -> None:
        """Dispatch every waiting event."""
        _ = asyncio.run(self.outbox.drain())


def phone_login(client: TestClient, username: str, fcm_token: str) -> dict[str, str]:
    """Log in from a phone with a push token.

    Returns:
        The auth header.
    """
    response = client.post(
        "/auth/login",
        json={
            "username": username,
            "password": CREDENTIAL,
            "platform": "android",
            "fcm_token": fcm_token,
        },
    )
    return bearer(LoginResult.model_validate_json(response.content).token)


@pytest.fixture
def crew(
    client: TestClient, database: Database, dispatcher: Dispatcher, phones: FakeSender
) -> Crew:
    """The crew, with the shop set up and nothing sent yet.

    Returns:
        The crew.
    """
    for name, roles in (
        ("ali", {Role.DRIVER}),
        ("veli", {Role.DRIVER}),
        ("ayse", {Role.STAFF}),
    ):
        _ = make_user(database, name, roles)
    crew = Crew(
        make_shop(client),
        dispatcher,
        ali=phone_login(client, "ali", "ali-phone"),
        veli=phone_login(client, "veli", "veli-phone"),
        ayse=phone_login(client, "ayse", "ayse-phone"),
    )
    shift = client.put("/auth/me/shift", json={"on_shift": True}, headers=crew.ali)
    assert shift.status_code == HTTPStatus.OK
    crew.flush()
    _ = phones.take()
    return crew


def test_new_deliveries_reach_drivers_on_shift(crew: Crew, phones: FakeSender) -> None:
    """Only drivers on shift hear about the pool; pickups never enter it."""
    _ = crew.deliver()
    _ = ok(crew.shop.walk_in({crew.shop.cups: 1}))
    crew.flush()
    assert phones.take() == [("ali-phone", "pool_changed")]


def test_claiming_and_taking_back(crew: Crew, phones: FakeSender) -> None:
    """Claims update everyone's pool; a driver hears when staff take one back."""
    order = crew.deliver()
    url = f"/orders/{order.id}"
    _ = crew.post(f"{url}/claim", crew.ali)
    crew.flush()
    assert phones.take() == [
        ("ali-phone", "pool_changed"),
        ("ali-phone", "pool_changed"),
    ]

    _ = crew.post(f"{url}/take-back", crew.ayse, reason="customer called back")
    crew.flush()
    assert phones.take() == [
        ("ali-phone", "order_taken_back"),
        ("ali-phone", "pool_changed"),
    ]

    _ = crew.post(f"{url}/claim", crew.ali)
    _ = crew.post(f"{url}/release", crew.ali)
    crew.flush()
    assert phones.take() == [("ali-phone", "pool_changed")] * 2


def test_the_holder_hears_about_changes(crew: Crew, phones: FakeSender) -> None:
    """Changes by others reach the driver holding the delivery; their own don't."""
    shop = crew.shop
    changed, cancelled, completed, own = (crew.deliver() for _ in range(4))
    for order in (changed, cancelled, completed, own):
        _ = crew.post(f"/orders/{order.id}/claim", crew.ali)
    crew.flush()
    _ = phones.take()

    response = shop.client.patch(
        f"/orders/{changed.id}", json={"notes": "ring twice"}, headers=crew.ayse
    )
    assert response.status_code == HTTPStatus.OK
    _ = crew.post(f"/orders/{cancelled.id}/cancel", crew.ayse, reason="not home")
    _ = crew.post(f"/orders/{completed.id}/complete", crew.ayse)
    _ = crew.post(f"/orders/{own.id}/complete", crew.ali)
    crew.flush()
    assert phones.take() == [
        ("ali-phone", "order_cancelled"),
        ("ali-phone", "order_changed"),
        ("ali-phone", "order_completed"),
    ]


def test_pool_orders_changed_or_closed_update_the_pool(
    crew: Crew, phones: FakeSender
) -> None:
    """Editing, cancelling or completing an unclaimed delivery refreshes pools."""
    shop = crew.shop
    first, second = crew.deliver(), crew.deliver()
    crew.flush()
    _ = phones.take()
    _ = shop.client.patch(f"/orders/{first.id}", json={"notes": "3rd floor"})
    _ = crew.post(f"/orders/{first.id}/cancel", crew.ayse, reason="duplicate")
    _ = crew.post(f"/orders/{second.id}/complete", crew.ayse)
    crew.flush()
    assert phones.take() == [("ali-phone", "pool_changed")] * 3


def test_dead_tokens_are_forgotten(crew: Crew, phones: FakeSender) -> None:
    """A phone Firebase no longer knows is not messaged again."""
    phones.dead.add("ali-phone")
    _ = crew.deliver()
    crew.flush()
    phones.dead.clear()
    _ = crew.deliver()
    crew.flush()
    assert phones.take() == []


def test_failed_messages_are_retried(crew: Crew, phones: FakeSender) -> None:
    """If Firebase can't be reached, the outbox tries the event again."""
    phones.broken.add("ali-phone")
    _ = crew.deliver()
    crew.flush()  # tries until the retry policy gives up
    assert phones.take() == []
    phones.broken.clear()
    _ = crew.deliver()
    crew.flush()
    assert phones.take() == [("ali-phone", "pool_changed")]


def test_status_and_test_message(crew: Crew, phones: FakeSender) -> None:
    """Admins see the push status; anyone can test their own phones."""
    client = crew.shop.client
    status = PushStatus.model_validate_json(client.get("/notifications/status").content)
    assert status.project_id == "fake"
    forbidden = client.get("/notifications/status", headers=crew.ayse)
    assert forbidden.status_code == HTTPStatus.FORBIDDEN

    response = client.post("/notifications/test", headers=crew.veli)
    assert PushReport.model_validate_json(response.content) == PushReport(sent=1)
    assert phones.take() == [("veli-phone", "test")]


def test_unconfigured_pushes_are_skipped(crew: Crew) -> None:
    """Without Firebase credentials, messages are logged and counted as skipped."""
    use_sender(None)
    assert get_sender().status.problem == "FCM_CREDENTIALS_FILE is not set"
    response = crew.shop.client.post("/notifications/test", headers=crew.ali)
    assert PushReport.model_validate_json(response.content) == PushReport(skipped=1)


def test_push_for_other_modules(
    crew: Crew, database: Database, phones: FakeSender
) -> None:
    """Telephony will push through the module's public API."""

    async def ring() -> PushReport:
        async with database.transaction() as session:
            targets = await identity.push_targets(
                session, Role.DRIVER, on_shift_only=True
            )
            data = {"type": "incoming_call"}
            return await notifications.push(session, targets, data, ttl_seconds=30)

    phones.broken.add("ali-phone")
    report = asyncio.run(ring())
    assert (report.failed, report.error) == (1, "ali-phone unreachable")
    assert crew.shop.client.get("/auth/me", headers=crew.ali).status_code == (
        HTTPStatus.OK
    )


def test_incoming_calls_wake_the_drivers_on_shift(
    crew: Crew, database: Database, phones: FakeSender
) -> None:
    """A call the shop didn't take rings drivers' phones via a push."""

    async def announce(caller: str | None) -> None:
        async with database.transaction() as session:
            event = DriversRung(
                call_id=new_id(), caller_number=caller, customer_name=None
            )
            await outbox.publish(session, event)

    asyncio.run(announce("05321234567"))
    crew.flush()
    assert phones.take() == [("ali-phone", "incoming_call")]

    phones.broken.add("ali-phone")
    asyncio.run(announce(None))
    crew.flush()  # retried until the outbox gives up
    assert phones.take() == []
