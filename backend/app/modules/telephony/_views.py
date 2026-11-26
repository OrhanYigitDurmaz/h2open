# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the telephony module. Other modules get them via ``api``."""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId


class RingStrategy(StrEnum):
    """Who rings when a landline call comes in."""

    SHOP_FIRST = "shop_first"
    """Shop phones at once; drivers on shift join after a delay."""
    EVERYONE = "everyone"
    """Shop phones and drivers on shift ring together."""
    SHOP_ONLY = "shop_only"
    """Only shop phones ring."""


class CallStatus(StrEnum):
    """Where a call is in its life."""

    RINGING = "ringing"
    ANSWERED = "answered"
    COMPLETED = "completed"
    """Answered, then ended."""
    MISSED = "missed"
    """Ended without anyone answering: call the customer back."""


class EndReason(StrEnum):
    """Why a call ended."""

    CALLER_HUNG_UP = "caller_hung_up"
    ANSWERER_HUNG_UP = "answerer_hung_up"
    NO_ANSWER = "no_answer"
    """Nobody answered before the ring timeout."""
    INTERRUPTED = "interrupted"
    """The backend restarted during the call."""


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class TelephonySettingsView(_View):
    """How incoming calls are rung."""

    ring_strategy: RingStrategy
    driver_ring_delay_seconds: int
    """With ``shop_first``: how long the shop rings alone."""
    ring_timeout_seconds: int
    """How long a call rings in total before it counts as missed."""
    shop_endpoints: list[str]
    """Asterisk endpoints of the shop phones, e.g. ``PJSIP/desk1``."""
    driver_endpoint: str
    """The endpoint of a driver's phone; ``{username}`` is filled in."""
    no_answer_sound: str | None
    """Played to the caller after the ring timeout, e.g. ``h2open/no-answer``
    (a file in Asterisk's sounds); ``None`` hangs up without a message."""


class CallView(_View):
    """One landline call."""

    id: EntityId
    line: str
    """Which landline it came in on, e.g. ``line1``."""
    caller_number: str | None
    """The caller's number from caller ID, if the line sent one."""
    customer_id: EntityId | None
    """The customer the number belongs to, if known."""
    customer_name: str | None
    status: CallStatus
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    answered_by: str | None
    """The endpoint that answered, e.g. ``PJSIP/desk1``."""
    answered_by_user: EntityId | None
    """The driver who answered, if it was a driver."""
    end_reason: EndReason | None
