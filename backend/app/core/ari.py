# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small client for the Asterisk REST Interface (ARI).

ARI is two things: REST calls to act on calls (ring, answer, bridge, play,
hang up), and a WebSocket that streams events about the channels handed to
our Stasis application. Only the parts h2open uses are wrapped here.
"""

import base64
import json
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar, Protocol

import httpx2
import websockets
from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence


class AriError(Exception):
    """Asterisk refused a request, e.g. ringing an endpoint that is offline."""


class _Model(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")


class CallerId(_Model):
    """Who a channel is from, as Asterisk reports it."""

    name: str = ""
    number: str = ""


class Channel(_Model):
    """One side of a call in Asterisk."""

    id: str
    name: str = ""
    state: str = ""
    caller: CallerId = CallerId()


class Playback(_Model):
    """A sound being played to a channel."""

    id: str
    target_uri: str = ""
    state: str = ""


class AriEvent(_Model):
    """An event from the ARI WebSocket; fields depend on ``type``."""

    type: str
    application: str = ""
    channel: Channel | None = None
    args: list[str] = Field(default_factory=list)
    playback: Playback | None = None


class CallControl(Protocol):
    """The ARI operations the call handling needs."""

    async def originate(
        self,
        endpoint: str,
        *,
        app_args: Sequence[str],
        caller_id: str | None,
        ring_seconds: int,
    ) -> str:
        """Ring an endpoint; it enters our app if answered."""
        ...

    async def ring(self, channel_id: str) -> None:
        """Play ringback to a channel."""
        ...

    async def answer(self, channel_id: str) -> None:
        """Answer a channel."""
        ...

    async def hangup(self, channel_id: str) -> None:
        """Hang up a channel; gone already is fine."""
        ...

    async def bridge(self, channel_ids: Sequence[str]) -> str:
        """Connect channels in a new bridge."""
        ...

    async def destroy_bridge(self, bridge_id: str) -> None:
        """Remove a bridge; gone already is fine."""
        ...

    async def play(self, channel_id: str, media: str) -> str:
        """Play a sound to a channel."""
        ...


class Asterisk(CallControl, Protocol):
    """Call control plus the stream of events: everything the backend uses."""

    async def follow(self, handle: Callable[[AriEvent], Awaitable[None]]) -> None:
        """Pass each event to ``handle`` until the connection drops."""
        ...


class _Created(_Model):
    id: str


@dataclass(frozen=True, slots=True)
class AriConnection:
    """Where Asterisk is and how to log in."""

    url: str
    """The ARI base URL, e.g. ``http://127.0.0.1:8088``."""
    username: str
    password: str
    app: str
    """Our Stasis application name."""


class AriClient:
    """Talks to one Asterisk over ARI."""

    def __init__(
        self,
        connection: AriConnection,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        """Set up a client. Nothing connects until it is used.

        Args:
            connection: Where Asterisk is.
            transport: How HTTP requests are made; tests replace it.
        """
        self._url: str = connection.url.rstrip("/")
        self._auth: tuple[str, str] = (connection.username, connection.password)
        self._app: str = connection.app
        self._transport: httpx2.AsyncBaseTransport | None = transport

    async def _request(
        self, method: str, path: str, params: dict[str, str] | None = None
    ) -> httpx2.Response:
        """Send one REST request.

        Returns:
            The response, if successful.

        Raises:
            AriError: Asterisk said no, or could not be reached.
        """
        try:
            async with httpx2.AsyncClient(
                transport=self._transport, auth=self._auth, timeout=5
            ) as http:
                response = await http.request(
                    method, f"{self._url}/ari{path}", params=params
                )
        except httpx2.HTTPError as error:
            msg = f"could not reach Asterisk: {error!r}"
            raise AriError(msg) from error
        if response.is_error:
            msg = f"{method} {path}: {response.status_code} {response.text[:200]}"
            raise AriError(msg)
        return response

    async def _forgiving(self, method: str, path: str) -> None:
        """A request where "already gone" (404) counts as done.

        Raises:
            AriError: Any other failure.
        """
        try:
            _ = await self._request(method, path)
        except AriError as error:
            if f": {HTTPStatus.NOT_FOUND} " not in str(error):
                raise

    async def originate(
        self,
        endpoint: str,
        *,
        app_args: Sequence[str],
        caller_id: str | None,
        ring_seconds: int,
    ) -> str:
        """Ring an endpoint; when answered, it enters our app with ``app_args``.

        Returns:
            The new channel's ID.
        """
        params = {
            "endpoint": endpoint,
            "app": self._app,
            "appArgs": ",".join(app_args),
            "timeout": str(ring_seconds),
        }
        if caller_id:
            params["callerId"] = caller_id
        response = await self._request("POST", "/channels", params)
        return _Created.model_validate_json(response.content).id

    async def ring(self, channel_id: str) -> None:
        """Play ringback (the country's ringing tone) to a channel."""
        _ = await self._request("POST", f"/channels/{channel_id}/ring")

    async def answer(self, channel_id: str) -> None:
        """Answer a channel."""
        _ = await self._request("POST", f"/channels/{channel_id}/answer")

    async def hangup(self, channel_id: str) -> None:
        """Hang up a channel; one that is already gone is fine."""
        await self._forgiving("DELETE", f"/channels/{channel_id}")

    async def bridge(self, channel_ids: Sequence[str]) -> str:
        """Connect channels to each other in a new bridge.

        Returns:
            The bridge's ID.
        """
        response = await self._request("POST", "/bridges", {"type": "mixing"})
        bridge_id = _Created.model_validate_json(response.content).id
        _ = await self._request(
            "POST",
            f"/bridges/{bridge_id}/addChannel",
            {"channel": ",".join(channel_ids)},
        )
        return bridge_id

    async def destroy_bridge(self, bridge_id: str) -> None:
        """Remove a bridge; one that is already gone is fine."""
        await self._forgiving("DELETE", f"/bridges/{bridge_id}")

    async def play(self, channel_id: str, media: str) -> str:
        """Play a sound, e.g. ``sound:h2open/no-answer``, to a channel.

        Returns:
            The playback's ID.
        """
        response = await self._request(
            "POST", f"/channels/{channel_id}/play", {"media": media}
        )
        return _Created.model_validate_json(response.content).id

    async def follow(self, handle: Callable[[AriEvent], Awaitable[None]]) -> None:
        """Pass each event for our app to ``handle`` until the connection drops.

        Messages that are not events are skipped.

        Args:
            handle: Called for each event, one at a time.
        """
        ws_url = self._url.replace("http", "ws", 1)
        token = base64.b64encode(":".join(self._auth).encode()).decode()
        async with websockets.connect(
            f"{ws_url}/ari/events?app={self._app}",
            additional_headers={"Authorization": f"Basic {token}"},
        ) as socket:
            async for message in socket:
                try:
                    event = AriEvent.model_validate_json(message)
                except ValidationError, json.JSONDecodeError:
                    continue
                await handle(event)
