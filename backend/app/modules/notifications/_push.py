# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sending a message to a set of phones. Private to this module."""

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.push import PushError, SendOutcome, get_sender
from app.modules.identity import api as identity

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession


class PushReport(BaseModel):
    """What happened when messaging a set of phones."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    sent: int = 0
    skipped: int = 0
    """Not sent because push messages are not configured."""
    unregistered: int = 0
    """Phones whose token was dead; they won't be messaged again."""
    failed: int = 0
    error: str | None = None
    """The last error, if any failed."""


async def push(
    session: AsyncSession,
    targets: Iterable[identity.PushTarget],
    data: Mapping[str, str],
    *,
    ttl_seconds: int,
) -> PushReport:
    """Send one data message to each phone; dead tokens are forgotten.

    Returns:
        How it went.
    """
    sender = get_sender()
    counts = dict.fromkeys(SendOutcome, 0)
    failed, error = 0, None
    for target in targets:
        try:
            outcome = await sender.send(target.fcm_token, data, ttl_seconds=ttl_seconds)
        except PushError as problem:
            failed, error = failed + 1, str(problem)
            continue
        counts[outcome] += 1
        if outcome is SendOutcome.UNREGISTERED:
            await identity.forget_push_token(session, target.fcm_token)
    return PushReport(
        sent=counts[SendOutcome.SENT],
        skipped=counts[SendOutcome.SKIPPED],
        unregistered=counts[SendOutcome.UNREGISTERED],
        failed=failed,
        error=error,
    )
