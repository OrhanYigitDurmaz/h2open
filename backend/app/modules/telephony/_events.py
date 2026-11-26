# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Events the telephony module publishes. Other modules get them via ``api``."""

from typing import ClassVar

from app.core.events import DomainEvent
from app.core.ids import EntityId


class DriversRung(DomainEvent):
    """Drivers on shift are being rung for a call nobody at the shop took.

    Their phones get a push so the app wakes up and can take the call.
    """

    event_type: ClassVar[str] = "telephony.drivers_rung"

    call_id: EntityId
    caller_number: str | None
    customer_name: str | None
