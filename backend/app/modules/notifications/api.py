# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the notifications module.

Telephony will use :func:`push` to ring drivers' phones on incoming calls.
"""

from typing import TYPE_CHECKING

from app.core.push import PushStatus
from app.modules.notifications import _push
from app.modules.notifications._push import PushReport

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.api import PushTarget

__all__ = ["PushReport", "PushStatus", "push"]


async def push(
    session: AsyncSession,
    targets: Iterable[PushTarget],
    data: Mapping[str, str],
    *,
    ttl_seconds: int,
) -> PushReport:
    """Send a high-priority data message to each phone.

    Args:
        session: The caller's session; dead tokens are forgotten in it.
        targets: The phones, from ``identity.api.push_targets``.
        data: The message; FCM only carries string values.
        ttl_seconds: How long the message is worth delivering.

    Returns:
        How it went. Failures are counted, not raised.
    """
    return await _push.push(session, targets, data, ttl_seconds=ttl_seconds)
