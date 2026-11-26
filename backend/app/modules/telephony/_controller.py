# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Handling landline calls as they happen, driven by ARI events. Private.

For each call:

1. A landline call enters our app (``StasisStart`` with arguments
   ``inbound,<line>``). It is logged and matched to a customer, the caller
   hears ringback, and the shop phones ring.
2. Drivers on shift ring too, at once or after a delay, depending on the
   ring strategy; their phones get a push first so the app wakes up.
3. The first phone to answer enters our app (``leg,<call id>``). It is
   connected to the caller, and every other phone stops ringing.
4. If nobody answers in time, the phones stop, the caller hears the
   no-answer message (if one is set), and the call ends as missed.
5. Either side hanging up ends the call.

Events and timers are handled one at a time under a lock, so two phones
answering at the same moment cannot both get the call.
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core import outbox
from app.core.ari import AriError
from app.modules.identity import api as identity
from app.modules.telephony import _service
from app.modules.telephony._events import DriversRung
from app.modules.telephony._views import EndReason, RingStrategy

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from app.core.ari import AriEvent, CallControl, Channel
    from app.core.db import Database
    from app.core.ids import EntityId
    from app.modules.telephony._views import TelephonySettingsView

logger = logging.getLogger(__name__)

INBOUND = "inbound"
"""First Stasis argument of a landline call, from the dialplan."""
LEG = "leg"
"""First Stasis argument of a phone we rang, once it answers."""


@dataclass(frozen=True, slots=True)
class _Leg:
    """A phone being rung for a call."""

    endpoint: str
    user_id: EntityId | None
    """The driver whose phone it is, if any."""


@dataclass(slots=True)
class _Call:
    """What the controller knows about one call in progress."""

    id: EntityId
    caller: str
    """The landline channel."""
    caller_number: str | None
    customer_name: str | None
    settings: TelephonySettingsView
    deadline: float
    """When the ring timeout runs out (event loop time)."""
    ringing: dict[str, _Leg] = field(default_factory=dict)
    answered: str | None = None
    answered_leg: _Leg | None = None
    bridge: str | None = None
    in_message: bool = False
    """Ringing is over and the caller is hearing the no-answer message."""
    timers: list[asyncio.Task[None]] = field(default_factory=list)

    @property
    def still_ringing(self) -> bool:
        """Whether nobody has answered and the timeout has not run out."""
        return self.answered is None and not self.in_message

    def stop_timers(self) -> None:
        """Cancel pending timers.

        Only event handling calls this, never a timer, so no timer ever
        cancels itself.
        """
        for timer in self.timers:
            _ = timer.cancel()
        self.timers.clear()


class CallController:
    """Keeps track of every call in progress and acts on Asterisk's events."""

    def __init__(
        self,
        database: Database,
        ari: CallControl,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Set up a controller with no calls.

        Args:
            database: Where calls are logged.
            ari: How calls are acted on.
            sleep: Waits a number of seconds; tests speed it up.
        """
        self._database: Database = database
        self._ari: CallControl = ari
        self._sleep: Callable[[float], Awaitable[None]] = sleep
        self._calls: dict[EntityId, _Call] = {}
        self._channels: dict[str, EntityId] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def start(self) -> None:
        """Forget calls from before a restart; Asterisk has dropped them."""
        for call in list(self._calls.values()):
            call.stop_timers()
            self._forget(call)
        async with self._database.transaction() as session:
            closed = await _service.interrupt_unfinished(session)
        if closed:
            logger.warning("closed %d calls interrupted by a restart", closed)

    async def handle(self, event: AriEvent) -> None:
        """Act on one event from Asterisk.

        Args:
            event: The event.
        """
        async with self._lock:
            try:
                await self._dispatch(event)
            except AriError:
                logger.exception("Asterisk refused a request for %s", event.type)

    async def _dispatch(self, event: AriEvent) -> None:
        channel = event.channel
        if event.type == "StasisStart" and channel is not None:
            match event.args[:1]:
                case [kind] if kind == INBOUND:
                    line = event.args[1] if len(event.args) > 1 else "unknown"
                    await self._incoming(channel, line)
                case [kind] if kind == LEG:
                    await self._answered(channel)
                case _:
                    await self._ari.hangup(channel.id)
        elif event.type == "ChannelDestroyed" and channel is not None:
            await self._gone(channel.id)
        elif event.type == "PlaybackFinished" and event.playback is not None:
            target = event.playback.target_uri.removeprefix("channel:")
            if target in self._channels:
                await self._ari.hangup(target)

    # Ringing

    async def _incoming(self, channel: Channel, line: str) -> None:
        number = channel.caller.number or None
        async with self._database.transaction() as session:
            settings = await _service.get_settings(session)
            logged = await _service.start_call(session, line, number)
        loop = asyncio.get_running_loop()
        call = _Call(
            id=logged.id,
            caller=channel.id,
            caller_number=logged.caller_number,
            customer_name=logged.customer_name,
            settings=settings,
            deadline=loop.time() + settings.ring_timeout_seconds,
        )
        self._calls[call.id] = call
        self._channels[channel.id] = call.id
        logger.info("call %s on %s from %s", call.id, line, number or "unknown")
        try:
            await self._ari.ring(channel.id)
        except AriError:
            # Ringback is a courtesy; the phones should ring regardless.
            logger.exception("could not play ringback for call %s", call.id)
        await self._ring(
            call, [(endpoint, None) for endpoint in settings.shop_endpoints]
        )
        match settings.ring_strategy:
            case RingStrategy.EVERYONE:
                await self._ring_drivers(call)
            case RingStrategy.SHOP_FIRST:
                self._after(
                    call, settings.driver_ring_delay_seconds, self._ring_drivers
                )
            case _:  # RingStrategy.SHOP_ONLY
                pass
        self._after(call, settings.ring_timeout_seconds, self._time_out)

    async def _ring(
        self, call: _Call, targets: list[tuple[str, EntityId | None]]
    ) -> None:
        remaining = call.deadline - asyncio.get_running_loop().time()
        for endpoint, user_id in targets:
            try:
                leg = await self._ari.originate(
                    endpoint,
                    app_args=[LEG, str(call.id)],
                    caller_id=call.caller_number,
                    ring_seconds=max(1, math.ceil(remaining)),
                )
            except AriError as error:
                # Usually a phone that is offline; the others still ring.
                logger.info("could not ring %s: %s", endpoint, error)
                continue
            call.ringing[leg] = _Leg(endpoint, user_id)
            self._channels[leg] = call.id

    async def _ring_drivers(self, call: _Call) -> None:
        if not call.still_ringing:
            return
        async with self._database.transaction() as session:
            drivers = await identity.drivers_on_shift(session)
            if drivers:
                await outbox.publish(
                    session,
                    DriversRung(
                        call_id=call.id,
                        caller_number=call.caller_number,
                        customer_name=call.customer_name,
                    ),
                )
        template = call.settings.driver_endpoint
        await self._ring(
            call,
            [
                (template.replace("{username}", driver.username), driver.id)
                for driver in drivers
            ],
        )

    async def _time_out(self, call: _Call) -> None:
        # Answering or ending a call cancels this timer, so nobody has
        # answered when it fires.
        call.in_message = True
        for leg in list(call.ringing):
            await self._ari.hangup(leg)
        async with self._database.transaction() as session:
            await _service.end_call(session, call.id, EndReason.NO_ANSWER)
        sound = call.settings.no_answer_sound
        if sound is None:
            await self._ari.hangup(call.caller)
            return
        try:
            await self._ari.answer(call.caller)
            _ = await self._ari.play(call.caller, f"sound:{sound}")
        except AriError:
            logger.exception("could not play %s; hanging up", sound)
            await self._ari.hangup(call.caller)

    def _after(
        self,
        call: _Call,
        seconds: int,
        action: Callable[[_Call], Coroutine[None, None, None]],
    ) -> None:
        async def later() -> None:
            await self._sleep(seconds)
            # Forgetting a call cancels its timers, so the call is still here.
            async with self._lock:
                try:
                    await action(call)
                except AriError:
                    logger.exception("Asterisk refused a request for %s", call.id)

        call.timers.append(asyncio.create_task(later()))

    # Answering and hanging up

    async def _answered(self, channel: Channel) -> None:
        call_id = self._channels.get(channel.id)
        call = None if call_id is None else self._calls.get(call_id)
        if call is None or not call.still_ringing or channel.id not in call.ringing:
            # Too late: someone else answered, or the call is over.
            await self._ari.hangup(channel.id)
            return
        leg = call.ringing.pop(channel.id)
        call.answered, call.answered_leg = channel.id, leg
        call.stop_timers()
        for other in list(call.ringing):
            await self._ari.hangup(other)
        await self._ari.answer(call.caller)
        call.bridge = await self._ari.bridge([call.caller, channel.id])
        async with self._database.transaction() as session:
            await _service.mark_answered(session, call.id, leg.endpoint, leg.user_id)
        logger.info("call %s answered by %s", call.id, leg.endpoint)

    async def _gone(self, channel_id: str) -> None:
        call_id = self._channels.pop(channel_id, None)
        call = None if call_id is None else self._calls.get(call_id)
        if call is None:
            return
        if channel_id == call.caller:
            await self._finish(call, EndReason.CALLER_HUNG_UP)
        elif channel_id == call.answered:
            await self._finish(call, EndReason.ANSWERER_HUNG_UP)
        else:
            # A phone stopped ringing: declined, offline or timed out.
            _ = call.ringing.pop(channel_id, None)

    async def _finish(self, call: _Call, reason: EndReason) -> None:
        call.stop_timers()
        self._forget(call)
        for channel in [call.caller, call.answered, *call.ringing]:
            if channel is not None:
                await self._ari.hangup(channel)
        if call.bridge is not None:
            await self._ari.destroy_bridge(call.bridge)
        async with self._database.transaction() as session:
            await _service.end_call(session, call.id, reason)
        logger.info("call %s ended: %s", call.id, reason.value)

    def _forget(self, call: _Call) -> None:
        _ = self._calls.pop(call.id, None)
        for channel in [call.caller, call.answered, *call.ringing]:
            if channel is not None:
                _ = self._channels.pop(channel, None)
