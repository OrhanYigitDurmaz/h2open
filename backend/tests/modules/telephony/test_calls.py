# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for handling calls, against a fake Asterisk and a manual clock."""

import asyncio
import logging
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter
from sqlalchemy import select

from app.core.ari import AriEvent
from app.core.outbox import OutboxEvent
from app.modules.identity.api import Role, UserView
from app.modules.telephony.api import CallController, CallStatus, CallView, EndReason
from tests.modules.auth import bearer, login, make_user
from tests.modules.telephony.fakes import (
    Clock,
    FakeAri,
    destroyed,
    eventually,
    played,
    started,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

CALLS = TypeAdapter(list[CallView])
CALLER = "caller-1"
NUMBER = "05321234567"
DESK1, DESK2 = "PJSIP/desk1", "PJSIP/desk2"
DELAY, TIMEOUT = 15, 60


@dataclass
class Rig:
    """A controller wired to a fake Asterisk, plus the app for setup."""

    client: TestClient
    database: Database
    ari: FakeAri = field(default_factory=FakeAri)
    clock: Clock = field(default_factory=Clock)
    controller: CallController = field(init=False)

    def __post_init__(self) -> None:
        """Build the controller around the fakes."""
        self.controller = CallController(
            self.database, self.ari, sleep=self.clock.sleep
        )

    def settings(self, **changes: object) -> None:
        """Change the ring settings."""
        response = self.client.patch("/telephony/settings", json=changes)
        assert response.status_code == HTTPStatus.OK, response.text

    def driver(self, username: str) -> UserView:
        """A driver on shift.

        Returns:
            The driver.
        """
        driver = make_user(self.database, username, {Role.DRIVER})
        headers = bearer(login(self.client, username))
        shift = self.client.put(
            "/auth/me/shift", json={"on_shift": True}, headers=headers
        )
        assert shift.status_code == HTTPStatus.OK
        return driver

    def call(self) -> CallView:
        """The only call in the log.

        Returns:
            The call.
        """
        [call] = CALLS.validate_json(self.client.get("/calls").content)
        return call

    async def forward(self, seconds: float) -> None:
        """Let new timers start, then move the clock forward."""
        for _ in range(5):
            await asyncio.sleep(0)
        self.clock.forward(seconds)

    async def send(self, *events: AriEvent) -> None:
        """Hand events to the controller, as Asterisk would."""
        for event in events:
            await self.controller.handle(event)

    async def ring_in(self, number: str = NUMBER) -> None:
        """A landline call arrives on line 1."""
        await self.send(started(CALLER, "inbound", "line1", number=number))

    def leg_args(self) -> str:
        """The Stasis arguments phones are rung with.

        Returns:
            ``leg,<call id>``.
        """
        return f"leg,{self.call().id}"


@pytest.fixture
def rig(client: TestClient, database: Database) -> Rig:
    """The rig, with drivers joining 15 s into a call and a 60 s timeout.

    Returns:
        The rig.
    """
    return Rig(client, database)


def test_the_shop_answers(rig: Rig) -> None:
    """Ringback for the caller, both desks ring, the first to answer wins."""

    async def scenario() -> None:
        await rig.ring_in()
        legs = f"leg,{rig.call().id}"
        assert rig.ari.take() == [
            ("ring", CALLER),
            ("originate", DESK1, legs, NUMBER),
            ("originate", DESK2, legs, NUMBER),
        ]
        assert rig.ari.ring_seconds == [TIMEOUT, TIMEOUT]
        assert rig.call().status is CallStatus.RINGING

        desk1, desk2 = rig.ari.legs[DESK1], rig.ari.legs[DESK2]
        await rig.send(started(desk1, "leg", str(rig.call().id)))
        assert rig.ari.take() == [
            ("hangup", desk2),
            ("answer", CALLER),
            ("bridge", CALLER, desk1),
        ]
        await rig.send(destroyed(desk2))
        answered = rig.call()
        assert (answered.status, answered.answered_by) == (CallStatus.ANSWERED, DESK1)
        assert answered.answered_at is not None
        assert answered.answered_by_user is None

        await rig.forward(TIMEOUT)  # timers were cancelled: nothing happens
        await rig.send(destroyed(CALLER))
        assert rig.ari.take() == [
            ("hangup", CALLER),
            ("hangup", desk1),
            ("destroy_bridge", "bridge-1"),
        ]
        ended = rig.call()
        assert (ended.status, ended.end_reason) == (
            CallStatus.COMPLETED,
            EndReason.CALLER_HUNG_UP,
        )

    asyncio.run(scenario())


def test_the_answerer_hangs_up_first(rig: Rig) -> None:
    """When the shop hangs up, the caller is hung up too."""

    async def scenario() -> None:
        await rig.ring_in()
        desk1 = rig.ari.legs[DESK1]
        await rig.send(started(desk1, *rig.leg_args().split(",")))
        _ = rig.ari.take()
        await rig.send(destroyed(desk1))
        assert ("hangup", CALLER) in rig.ari.take()
        assert rig.call().end_reason is EndReason.ANSWERER_HUNG_UP
        await rig.send(destroyed(CALLER))  # already over: ignored
        assert rig.ari.take() == []

    asyncio.run(scenario())


def test_drivers_join_after_the_delay(rig: Rig, database: Database) -> None:
    """Drivers on shift ring after 15 s, get a push, and can take the call."""
    ali = rig.driver("ali")
    rig.settings(driver_endpoint="PJSIP/driver-{username}")
    _ = make_user(database, "veli", {Role.DRIVER})  # off shift: never rung

    async def scenario() -> None:
        await rig.ring_in()
        _ = rig.ari.take()
        await rig.forward(DELAY - 1)
        await asyncio.sleep(0.05)
        assert rig.ari.take() == []

        await rig.forward(1)
        await eventually(lambda: "PJSIP/driver-ali" in rig.ari.legs)
        assert rig.ari.take() == [
            ("originate", "PJSIP/driver-ali", rig.leg_args(), NUMBER)
        ]
        async with database.transaction() as session:
            [push] = await session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "telephony.drivers_rung"
                )
            )
        assert push.payload["call_id"] == str(rig.call().id)

        driver_leg = rig.ari.legs["PJSIP/driver-ali"]
        await rig.send(started(driver_leg, *rig.leg_args().split(",")))
        answered = rig.call()
        assert (answered.answered_by, answered.answered_by_user) == (
            "PJSIP/driver-ali",
            ali.id,
        )

    asyncio.run(scenario())


def test_everyone_rings_at_once_or_only_the_shop(rig: Rig) -> None:
    """``everyone`` rings drivers right away; ``shop_only`` never does."""
    _ = rig.driver("ali")

    async def scenario() -> None:
        rig.settings(ring_strategy="everyone")
        await rig.ring_in()
        assert "PJSIP/driver-ali" in rig.ari.legs
        await rig.send(destroyed(CALLER))

        rig.settings(ring_strategy="shop_only")
        rig.ari.legs.clear()
        await rig.send(started("caller-2", "inbound", "line2"))
        await rig.forward(DELAY)
        await asyncio.sleep(0.05)
        assert set(rig.ari.legs) == {DESK1, DESK2}

    asyncio.run(scenario())


def test_drivers_are_not_rung_after_the_timeout(rig: Rig) -> None:
    """If drivers are due after the timeout, the call is over by then."""
    _ = rig.driver("ali")
    rig.settings(driver_ring_delay_seconds=100)

    async def scenario() -> None:
        await rig.ring_in()
        await rig.forward(TIMEOUT)
        await eventually(lambda: any(a[0] == "play" for a in rig.ari.actions))
        await rig.forward(100 - TIMEOUT)
        await asyncio.sleep(0.05)
        assert "PJSIP/driver-ali" not in rig.ari.legs

    asyncio.run(scenario())


def test_no_drivers_on_shift_means_no_push(rig: Rig, database: Database) -> None:
    """With nobody on shift, the delay passes quietly."""

    async def scenario() -> None:
        await rig.ring_in()
        await rig.forward(DELAY)
        await asyncio.sleep(0.05)
        async with database.transaction() as session:
            pushes = list(await session.scalars(select(OutboxEvent)))
        assert [p.event_type for p in pushes] == []

    asyncio.run(scenario())


def test_nobody_answers(rig: Rig) -> None:
    """After the timeout the phones stop and the caller hears the message."""

    async def scenario() -> None:
        await rig.ring_in()
        desk1, desk2 = rig.ari.legs[DESK1], rig.ari.legs[DESK2]
        await rig.send(destroyed(desk2))  # desk 2 declined; desk 1 rings on
        _ = rig.ari.take()

        await rig.forward(TIMEOUT)
        await eventually(lambda: any(a[0] == "play" for a in rig.ari.actions))
        assert rig.call().status is CallStatus.MISSED
        assert rig.ari.take() == [
            ("hangup", desk1),
            ("answer", CALLER),
            ("play", CALLER, "sound:h2open/no-answer"),
        ]
        late = rig.call()
        assert late.end_reason is EndReason.NO_ANSWER

        await rig.send(started(desk1, *rig.leg_args().split(",")))  # too late
        await rig.send(played("someone-else"), played(CALLER))
        assert rig.ari.take() == [("hangup", desk1), ("hangup", CALLER)]
        await rig.send(destroyed(CALLER))
        assert rig.call().end_reason is EndReason.NO_ANSWER

    asyncio.run(scenario())


def test_without_a_message_the_call_just_ends(rig: Rig) -> None:
    """With no message set, or when it cannot be played, the line is freed."""

    async def scenario() -> None:
        rig.settings(no_answer_sound=None)
        await rig.ring_in()
        await rig.forward(TIMEOUT)
        await eventually(lambda: ("hangup", CALLER) in rig.ari.actions)

        rig.settings(no_answer_sound="h2open/no-answer")
        rig.ari.refuse.add("play")
        await rig.send(started("caller-2", "inbound", "line1"))
        await rig.forward(TIMEOUT)
        await eventually(lambda: ("hangup", "caller-2") in rig.ari.actions)

    asyncio.run(scenario())


def test_the_caller_gives_up(rig: Rig) -> None:
    """Hanging up while it rings stops every phone; the call is missed."""

    async def scenario() -> None:
        await rig.ring_in()
        desk1, desk2 = rig.ari.legs[DESK1], rig.ari.legs[DESK2]
        _ = rig.ari.take()
        await rig.send(destroyed(CALLER))
        assert rig.ari.take() == [
            ("hangup", CALLER),
            ("hangup", desk1),
            ("hangup", desk2),
        ]
        missed = rig.call()
        assert (missed.status, missed.end_reason) == (
            CallStatus.MISSED,
            EndReason.CALLER_HUNG_UP,
        )
        await rig.forward(TIMEOUT)
        await asyncio.sleep(0.05)
        assert rig.ari.take() == []

    asyncio.run(scenario())


def test_known_and_unknown_callers(rig: Rig) -> None:
    """Caller ID is matched to a customer; no caller ID is fine too."""
    response = rig.client.post(
        "/customers",
        json={"name": "Demir family", "phones": [{"number": "+90 532 123 45 67"}]},
    )
    assert response.status_code == HTTPStatus.CREATED

    async def scenario() -> None:
        await rig.ring_in()
        known = rig.call()
        assert (known.caller_number, known.customer_name) == (NUMBER, "Demir family")
        await rig.send(destroyed(CALLER))

        await rig.send(started("caller-2", "inbound"))
        calls = CALLS.validate_json(rig.client.get("/calls").content)
        assert (calls[0].line, calls[0].caller_number, calls[0].customer_id) == (
            "unknown",
            None,
            None,
        )
        await rig.send(destroyed("caller-2"))

        await rig.send(started("caller-3", "inbound", "line2", number="05559999999"))
        assert (
            CALLS.validate_json(rig.client.get("/calls").content)[0].customer_name
            is None
        )

    asyncio.run(scenario())


def test_odd_events_are_ignored_or_refused(rig: Rig) -> None:
    """Strangers in our app are hung up; irrelevant events change nothing."""

    async def scenario() -> None:
        await rig.send(
            started("stray", "something-else"),
            started("orphan-leg", "leg", "no-such-call"),
            AriEvent(type="StasisStart"),
            AriEvent(type="ChannelDestroyed"),
            AriEvent(type="ChannelVarset"),
            destroyed("never-seen"),
            AriEvent(type="PlaybackFinished"),
        )
        assert rig.ari.take() == [("hangup", "stray"), ("hangup", "orphan-leg")]

    asyncio.run(scenario())


def test_asterisk_refusing_is_logged_not_fatal(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """An offline phone is skipped; a refused request does not stop the loop."""
    rig.ari.offline.add(DESK2)
    rig.ari.refuse.add("ring")

    async def scenario() -> None:
        with caplog.at_level(logging.INFO):
            await rig.ring_in()
        assert "could not play ringback" in caplog.text
        assert "could not ring PJSIP/desk2" in caplog.text
        assert set(rig.ari.legs) == {DESK1}

        rig.ari.refuse = {"hangup"}
        rig.ari.offline.clear()
        await rig.send(started("caller-2", "inbound", "line1"))
        assert set(rig.ari.legs) == {DESK1, DESK2}
        await rig.forward(TIMEOUT)
        await eventually(lambda: "Asterisk refused a request for" in caplog.text)
        await rig.send(destroyed("caller-2"))
        assert "Asterisk refused a request for ChannelDestroyed" in caplog.text

    asyncio.run(scenario())


def test_ring_time_shrinks_as_the_call_waits(rig: Rig) -> None:
    """Drivers rung late only ring until the call's own timeout."""
    _ = rig.driver("ali")
    rig.settings(driver_ring_delay_seconds=0)

    async def scenario() -> None:
        await rig.ring_in()
        await rig.forward(0)
        await eventually(lambda: "PJSIP/driver-ali" in rig.ari.legs)
        assert all(1 <= seconds <= TIMEOUT for seconds in rig.ari.ring_seconds)

    asyncio.run(scenario())


def test_a_restart_closes_unfinished_calls(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """Calls open when the backend stopped are closed as interrupted."""

    async def scenario() -> None:
        await rig.ring_in()
        await rig.send(started("caller-2", "inbound", "line2"))
        desk = rig.ari.legs[DESK1]
        await rig.send(
            started(
                desk,
                "leg",
                str(CALLS.validate_json(rig.client.get("/calls").content)[0].id),
            )
        )
        with caplog.at_level(logging.WARNING):
            await rig.controller.start()
        assert "closed 2 calls interrupted by a restart" in caplog.text
        calls = CALLS.validate_json(rig.client.get("/calls").content)
        assert {(c.status, c.end_reason) for c in calls} == {
            (CallStatus.MISSED, EndReason.INTERRUPTED),
            (CallStatus.COMPLETED, EndReason.INTERRUPTED),
        }
        _ = rig.ari.take()
        await rig.send(destroyed(CALLER))  # forgotten: nothing to do
        assert rig.ari.take() == []
        await rig.controller.start()  # nothing left to close

    asyncio.run(scenario())
