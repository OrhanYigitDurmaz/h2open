# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""End to end against the real Asterisk container, with simulated phones.

The ``[selftest]`` dialplan context stands in for hardware: a caller who
waits on the line (``Local/answer@selftest``), a phone that rings forever
(``Local/noanswer@selftest``) and one that answers at once. Skipped when
Asterisk is not running (``docker compose up -d asterisk``).
"""

import asyncio
import contextlib
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx2
import pytest
from dotenv import dotenv_values
from pydantic import TypeAdapter

from app.core.ari import AriClient, AriConnection
from app.core.settings import REPO_ROOT
from app.modules.identity.api import Role
from app.modules.telephony import api as telephony
from app.modules.telephony.api import CallStatus, CallView, EndReason
from tests.modules.auth import bearer, login, make_user
from tests.modules.telephony.fakes import eventually

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi.testclient import TestClient

    from app.core.db import Database

CALLS = TypeAdapter(list[CallView])
CHANNELS = TypeAdapter(list[dict[str, object]])
NUMBER = "05321234567"


def _asterisk() -> AriConnection | None:
    """The local Asterisk, if it is up, logged in with the .env credentials.

    Returns:
        The connection, or ``None`` to skip these tests.
    """
    env = dotenv_values(REPO_ROOT / ".env")
    username, password = env.get("ARI_USERNAME"), env.get("ARI_PASSWORD")
    if not username or not password:
        return None
    url = env.get("ARI_URL") or "http://127.0.0.1:8088"
    try:
        response = httpx2.get(
            f"{url}/ari/asterisk/info", auth=(username, password), timeout=1
        )
    except httpx2.HTTPError:
        return None
    if response.status_code != HTTPStatus.OK:
        return None
    return AriConnection(
        url=url, username=username, password=password, app=telephony.APP
    )


ASTERISK = _asterisk()
pytestmark = pytest.mark.skipif(
    ASTERISK is None, reason="Asterisk is not running (docker compose up -d asterisk)"
)


def channels_left(connection: AriConnection) -> list[dict[str, object]]:
    """Every channel Asterisk still has.

    Returns:
        The channels.
    """
    response = httpx2.get(
        f"{connection.url}/ari/channels",
        auth=(connection.username, connection.password),
    )
    return CHANNELS.validate_json(response.content)


def last_call(client: TestClient) -> CallView | None:
    """The newest call in the log, if any.

    Returns:
        The call.
    """
    calls = CALLS.validate_json(client.get("/calls").content)
    return calls[0] if calls else None


def status(client: TestClient) -> CallStatus | None:
    """The newest call's status.

    Returns:
        The status, or ``None`` before the first call.
    """
    call = last_call(client)
    return None if call is None else call.status


def live(database: Database, scenario: Callable[[AriClient], Awaitable[None]]) -> None:
    """Run a scenario with a controller following the real Asterisk."""

    async def run() -> None:
        ari = AriClient(ari_connection())
        controller = telephony.CallController(database, ari)
        following = asyncio.create_task(ari.follow(controller.handle))
        await asyncio.sleep(0.5)  # let the WebSocket connect
        try:
            await scenario(ari)
        finally:
            _ = following.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await following

    asyncio.run(run())


def test_a_call_rings_through_to_a_driver(
    client: TestClient, database: Database
) -> None:
    """The shop doesn't pick up, a driver on shift does; then the caller hangs up."""
    patch = client.patch(
        "/telephony/settings",
        json={
            "shop_endpoints": ["Local/noanswer@selftest"],
            "driver_endpoint": "Local/answer@selftest",
            "driver_ring_delay_seconds": 1,
            "ring_timeout_seconds": 10,
        },
    )
    assert patch.status_code == HTTPStatus.OK
    ali = make_user(database, "ali", {Role.DRIVER})
    shift = client.put(
        "/auth/me/shift", json={"on_shift": True}, headers=bearer(login(client, "ali"))
    )
    assert shift.status_code == HTTPStatus.OK

    async def scenario(ari: AriClient) -> None:
        caller = await ari.originate(
            "Local/answer@selftest",
            app_args=["inbound", "line1"],
            caller_id=NUMBER,
            ring_seconds=10,
        )
        await eventually(lambda: status(client) is CallStatus.ANSWERED, seconds=8)
        answered = last_call(client)
        assert answered is not None
        assert (answered.line, answered.caller_number) == ("line1", NUMBER)
        assert (answered.answered_by, answered.answered_by_user) == (
            "Local/answer@selftest",
            ali.id,
        )

        await ari.hangup(caller)
        await eventually(lambda: status(client) is CallStatus.COMPLETED)
        ended = last_call(client)
        assert ended is not None
        assert ended.end_reason is EndReason.CALLER_HUNG_UP
        await eventually(lambda: channels_left(ari_connection()) == [])

    live(database, scenario)


def test_a_caller_who_gives_up(client: TestClient, database: Database) -> None:
    """Hanging up while the shop rings leaves a missed call and no channels."""
    patch = client.patch(
        "/telephony/settings",
        json={
            "shop_endpoints": ["Local/noanswer@selftest"],
            "ring_strategy": "shop_only",
        },
    )
    assert patch.status_code == HTTPStatus.OK

    async def scenario(ari: AriClient) -> None:
        caller = await ari.originate(
            "Local/answer@selftest",
            app_args=["inbound", "line2"],
            caller_id=None,
            ring_seconds=10,
        )
        await eventually(lambda: status(client) is CallStatus.RINGING)
        await asyncio.sleep(0.5)  # the shop phone is ringing
        await ari.hangup(caller)
        await eventually(lambda: status(client) is CallStatus.MISSED)
        ended = last_call(client)
        assert ended is not None
        assert ended.end_reason is EndReason.CALLER_HUNG_UP
        await eventually(lambda: channels_left(ari_connection()) == [])

    live(database, scenario)


def ari_connection() -> AriConnection:
    """The connection these tests run against.

    Returns:
        The connection.
    """
    assert ASTERISK is not None
    return ASTERISK
