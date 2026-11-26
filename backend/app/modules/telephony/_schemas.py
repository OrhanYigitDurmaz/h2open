# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the telephony endpoints. Private to this module."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.modules.telephony._views import CallStatus, RingStrategy

type Endpoint = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=100,
        # Technology/resource, e.g. PJSIP/desk1 or Local/answer@selftest.
        pattern=r"^[A-Za-z]+/[A-Za-z0-9_.@{}-]+$",
    ),
]
type Sound = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9_/-]{1,100}$")
]


class SettingsUpdate(BaseModel):
    """Changes to the ring settings; omitted fields stay as they are."""

    ring_strategy: RingStrategy | None = None
    driver_ring_delay_seconds: Annotated[int, Field(ge=0, le=300)] | None = None
    ring_timeout_seconds: Annotated[int, Field(ge=10, le=600)] | None = None
    shop_endpoints: Annotated[list[Endpoint], Field(max_length=20)] | None = None
    driver_endpoint: Endpoint | None = None
    no_answer_sound: Sound | None = None
    """Send ``null`` to hang up without a message."""


class CallSearch(BaseModel):
    """Query parameters for the call log."""

    status: CallStatus | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
