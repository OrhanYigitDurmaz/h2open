# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the ARI client, against a fake Asterisk."""

import asyncio
import base64
import json
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, cast

import httpx2
import pytest
import websockets

from app.core.ari import AriClient, AriConnection, AriError, AriEvent

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

CREDENTIAL = "not-a-real-one"
TOKEN = base64.b64encode(f"h2open:{CREDENTIAL}".encode()).decode()
CONNECTION = AriConnection(
    url="http://asterisk.test:8088/",
    username="h2open",
    password=CREDENTIAL,
    app="h2open",
)


@dataclass
class FakeAsterisk:
    """Answers ARI REST requests; records them."""

    requests: list[httpx2.Request] = field(default_factory=list)
    status: int = HTTPStatus.OK

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Answer with an ID for anything that creates something.

        Returns:
            The canned response.
        """
        self.requests.append(request)
        if self.status != HTTPStatus.OK:
            return httpx2.Response(self.status, text="nope")
        return httpx2.Response(HTTPStatus.OK, json={"id": f"id-{len(self.requests)}"})

    def client(self) -> AriClient:
        """A client talking to this fake.

        Returns:
            The client.
        """
        return AriClient(CONNECTION, transport=httpx2.MockTransport(self.handle))

    def sent(self) -> list[tuple[str, str, dict[str, str]]]:
        """What was asked, without the host.

        Returns:
            (method, path, query) per request.
        """
        return [(r.method, r.url.path, dict(r.url.params)) for r in self.requests]


def test_originate_and_call_control() -> None:
    """Each call-control step is one REST request, logged in as our user."""
    fake = FakeAsterisk()
    client = fake.client()

    async def scenario() -> None:
        leg = await client.originate(
            "PJSIP/desk1",
            app_args=["leg", "c1"],
            caller_id="05321234567",
            ring_seconds=60,
        )
        assert leg == "id-1"
        _ = await client.originate(
            "PJSIP/desk2", app_args=["leg", "c1"], caller_id=None, ring_seconds=5
        )
        await client.ring("caller")
        await client.answer("caller")
        assert await client.bridge(["caller", "id-1"]) == "id-5"
        assert await client.play("caller", "sound:h2open/no-answer") == "id-7"
        await client.hangup("id-1")
        await client.destroy_bridge("id-5")

    asyncio.run(scenario())
    assert fake.sent() == [
        (
            "POST",
            "/ari/channels",
            {
                "endpoint": "PJSIP/desk1",
                "app": "h2open",
                "appArgs": "leg,c1",
                "timeout": "60",
                "callerId": "05321234567",
            },
        ),
        (
            "POST",
            "/ari/channels",
            {
                "endpoint": "PJSIP/desk2",
                "app": "h2open",
                "appArgs": "leg,c1",
                "timeout": "5",
            },
        ),
        ("POST", "/ari/channels/caller/ring", {}),
        ("POST", "/ari/channels/caller/answer", {}),
        ("POST", "/ari/bridges", {"type": "mixing"}),
        ("POST", "/ari/bridges/id-5/addChannel", {"channel": "caller,id-1"}),
        ("POST", "/ari/channels/caller/play", {"media": "sound:h2open/no-answer"}),
        ("DELETE", "/ari/channels/id-1", {}),
        ("DELETE", "/ari/bridges/id-5", {}),
    ]
    assert fake.requests[0].headers["Authorization"] == f"Basic {TOKEN}"


def test_errors() -> None:
    """Refusals raise; hanging up something already gone does not."""
    gone = FakeAsterisk(status=HTTPStatus.NOT_FOUND)
    asyncio.run(gone.client().hangup("old"))
    asyncio.run(gone.client().destroy_bridge("old"))
    with pytest.raises(AriError, match="POST /channels/old/answer: 404 nope"):
        asyncio.run(gone.client().answer("old"))

    broken = FakeAsterisk(status=HTTPStatus.INTERNAL_SERVER_ERROR)
    with pytest.raises(AriError, match="500"):
        asyncio.run(broken.client().hangup("x"))

    def offline(request: httpx2.Request) -> httpx2.Response:
        msg = "connection refused"
        raise httpx2.ConnectError(msg, request=request)

    unreachable = AriClient(CONNECTION, transport=httpx2.MockTransport(offline))
    with pytest.raises(AriError, match="could not reach Asterisk"):
        asyncio.run(unreachable.ring("x"))


def test_follow_streams_events() -> None:
    """Events arrive in order; anything that is not an event is skipped."""
    messages = [
        json.dumps(
            {
                "type": "StasisStart",
                "application": "h2open",
                "args": ["inbound", "line1"],
                "channel": {
                    "id": "c1",
                    "name": "PJSIP/mp114-1",
                    "state": "Ring",
                    "caller": {"name": "", "number": "05321234567"},
                    "extra": "ignored",
                },
            }
        ),
        "not json",
        json.dumps({"no": "type"}),
        json.dumps({"type": "PlaybackFinished", "playback": {"id": "p1"}}),
    ]
    seen: list[AriEvent] = []
    headers: list[str] = []

    async def asterisk(connection: ServerConnection) -> None:
        request = connection.request
        assert request is not None
        headers.append(request.headers["Authorization"])
        assert request.path == "/ari/events?app=h2open"
        for message in messages:
            await connection.send(message)

    async def handle(event: AriEvent) -> None:
        await asyncio.sleep(0)
        seen.append(event)

    async def scenario() -> None:
        async with websockets.serve(asterisk, "127.0.0.1", 0) as server:
            # The standard library types socket addresses as Any.
            sockname = cast("tuple[str, int]", next(iter(server.sockets)).getsockname())
            port = sockname[1]
            here = AriConnection(
                url=f"http://127.0.0.1:{port}",
                username="h2open",
                password=CREDENTIAL,
                app="h2open",
            )
            await AriClient(here).follow(handle)

    asyncio.run(scenario())
    assert [event.type for event in seen] == ["StasisStart", "PlaybackFinished"]
    start = seen[0]
    assert start.args == ["inbound", "line1"]
    assert start.channel is not None
    assert start.channel.caller.number == "05321234567"
    assert headers == [f"Basic {TOKEN}"]
