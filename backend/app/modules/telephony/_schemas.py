# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the telephony endpoints. Private to this module."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.modules.telephony._views import CallStatus, RingStrategy

TRUNK = "PJSIP/mp114"
"""The landline gateway. Ringing it would dial out on the shop's lines."""


def _not_the_trunk(endpoint: str) -> str:
    """Refuse the landline gateway as a phone to ring.

    Returns:
        The endpoint, unchanged.

    Raises:
        ValueError: It is the gateway.
    """
    if endpoint.lower() == TRUNK.lower():
        msg = "the landline gateway is not a phone to ring"
        raise ValueError(msg)
    return endpoint


type Endpoint = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=100,
        # Only phones of our own: a PJSIP endpoint by name (PJSIP/desk1,
        # PJSIP/driver-{username}), or the test numbers in the selftest
        # context (Local/answer@selftest). No "@" after PJSIP and no other
        # Local context, so the settings can't make every incoming call also
        # dial an outside number through the landline gateway.
        pattern=r"^(PJSIP/[A-Za-z0-9_.{}-]+|Local/[a-z0-9_-]+@selftest)$",
    ),
    AfterValidator(_not_the_trunk),
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
