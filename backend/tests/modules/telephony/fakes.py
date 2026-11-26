# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fake Asterisk and a manual clock for driving calls in tests."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.ari import AriError, AriEvent, CallerId, Channel, Playback

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

type Action = tuple[str, ...]


@dataclass
class FakeAri:
    """Records what the controller asks Asterisk to do."""

    actions: list[Action] = field(default_factory=list)
    offline: set[str] = field(default_factory=set)
    """Endpoints that cannot be rung."""
    refuse: set[str] = field(default_factory=set)
    """Operations that fail, e.g. ``{"play"}``."""
    legs: dict[str, str] = field(default_factory=dict)
    """Endpoint -> the channel ID it was last rung on."""
    ring_seconds: list[int] = field(default_factory=list)

    async def _do(self, *action: str) -> None:
        await asyncio.sleep(0)
        if action[0] in self.refuse:
            msg = f"{action[0]} refused"
            raise AriError(msg)
        self.actions.append(action)

    async def originate(
        self,
        endpoint: str,
        *,
        app_args: Sequence[str],
        caller_id: str | None,
        ring_seconds: int,
    ) -> str:
        """Pretend to ring an endpoint.

        Returns:
            A channel ID.

        Raises:
            AriError: The endpoint is offline.
        """
        if endpoint in self.offline:
            msg = f"{endpoint} is offline"
            raise AriError(msg)
        leg = f"leg-{len(self.legs) + 1}"
        await self._do("originate", endpoint, ",".join(app_args), caller_id or "")
        self.legs[endpoint] = leg
        self.ring_seconds.append(ring_seconds)
        return leg

    async def ring(self, channel_id: str) -> None:
        """Record ringback."""
        await self._do("ring", channel_id)

    async def answer(self, channel_id: str) -> None:
        """Record an answer."""
        await self._do("answer", channel_id)

    async def hangup(self, channel_id: str) -> None:
        """Record a hang-up."""
        await self._do("hangup", channel_id)

    async def bridge(self, channel_ids: Sequence[str]) -> str:
        """Record a bridge.

        Returns:
            The bridge ID.
        """
        await self._do("bridge", *channel_ids)
        return "bridge-1"

    async def destroy_bridge(self, bridge_id: str) -> None:
        """Record a bridge being removed."""
        await self._do("destroy_bridge", bridge_id)

    async def play(self, channel_id: str, media: str) -> str:
        """Record a playback.

        Returns:
            The playback ID.
        """
        await self._do("play", channel_id, media)
        return "playback-1"

    def take(self) -> list[Action]:
        """Actions since the last call.

        Returns:
            The actions, in order.
        """
        taken, self.actions = self.actions, []
        return taken


@dataclass
class Clock:
    """Timers that fire only when a test moves time forward."""

    now: float = 0
    waiting: list[tuple[float, asyncio.Future[None]]] = field(default_factory=list)

    async def sleep(self, seconds: float) -> None:
        """Wait until the test has moved time ``seconds`` forward."""
        future = asyncio.get_running_loop().create_future()
        self.waiting.append((self.now + seconds, future))
        await future

    def forward(self, seconds: float) -> None:
        """Move time forward, waking the timers that are due."""
        self.now += seconds
        for due, future in list(self.waiting):
            if due <= self.now:
                self.waiting.remove((due, future))
                if not future.done():
                    future.set_result(None)


async def eventually(check: Callable[[], bool], seconds: float = 3) -> None:
    """Wait until ``check`` passes, for work done by timers in the background.

    Raises:
        AssertionError: It still fails after ``seconds``.
    """
    deadline = time.monotonic() + seconds
    while not check():
        if time.monotonic() > deadline:
            msg = "condition never became true"
            raise AssertionError(msg)
        await asyncio.sleep(0.01)


def started(channel_id: str, *args: str, number: str = "") -> AriEvent:
    """A channel entering our app.

    Returns:
        The event.
    """
    channel = Channel(id=channel_id, caller=CallerId(number=number))
    return AriEvent(type="StasisStart", channel=channel, args=list(args))


def destroyed(channel_id: str) -> AriEvent:
    """A channel hanging up.

    Returns:
        The event.
    """
    return AriEvent(type="ChannelDestroyed", channel=Channel(id=channel_id))


def played(channel_id: str) -> AriEvent:
    """A sound finishing on a channel.

    Returns:
        The event.
    """
    playback = Playback(id="playback-1", target_uri=f"channel:{channel_id}")
    return AriEvent(type="PlaybackFinished", playback=playback)
