# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ring settings and the call log. Private to this module."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.modules.customers import api as customers
from app.modules.telephony._models import SETTINGS_ROW_ID, Call, Settings
from app.modules.telephony._views import (
    CallStatus,
    CallView,
    EndReason,
    RingStrategy,
    TelephonySettingsView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.telephony._schemas import CallSearch, SettingsUpdate

DEFAULTS = TelephonySettingsView(
    ring_strategy=RingStrategy.SHOP_FIRST,
    driver_ring_delay_seconds=15,
    ring_timeout_seconds=60,
    shop_endpoints=["PJSIP/desk1", "PJSIP/desk2"],
    driver_endpoint="PJSIP/driver-{username}",
    no_answer_sound="h2open/no-answer",
)


def _now() -> datetime:
    return datetime.now(UTC)


# Settings


def _settings_view(row: Settings | None) -> TelephonySettingsView:
    if row is None:
        return DEFAULTS
    return TelephonySettingsView(
        ring_strategy=row.ring_strategy,
        driver_ring_delay_seconds=row.driver_ring_delay_seconds,
        ring_timeout_seconds=row.ring_timeout_seconds,
        shop_endpoints=list(row.shop_endpoints),
        driver_endpoint=row.driver_endpoint,
        no_answer_sound=row.no_answer_sound,
    )


async def get_settings(session: AsyncSession) -> TelephonySettingsView:
    """Read the ring settings, falling back to defaults.

    Returns:
        The settings in effect.
    """
    return _settings_view(await session.get(Settings, SETTINGS_ROW_ID))


async def update_settings(
    session: AsyncSession, data: SettingsUpdate
) -> TelephonySettingsView:
    """Change ring settings.

    Returns:
        The settings in effect afterwards.
    """
    row = await session.get(Settings, SETTINGS_ROW_ID)
    if row is None:
        row = Settings(
            id=SETTINGS_ROW_ID,
            ring_strategy=DEFAULTS.ring_strategy,
            driver_ring_delay_seconds=DEFAULTS.driver_ring_delay_seconds,
            ring_timeout_seconds=DEFAULTS.ring_timeout_seconds,
            shop_endpoints=DEFAULTS.shop_endpoints,
            driver_endpoint=DEFAULTS.driver_endpoint,
            no_answer_sound=DEFAULTS.no_answer_sound,
        )
        session.add(row)
    if data.ring_strategy is not None:
        row.ring_strategy = data.ring_strategy
    if data.driver_ring_delay_seconds is not None:
        row.driver_ring_delay_seconds = data.driver_ring_delay_seconds
    if data.ring_timeout_seconds is not None:
        row.ring_timeout_seconds = data.ring_timeout_seconds
    if data.shop_endpoints is not None:
        row.shop_endpoints = data.shop_endpoints
    if data.driver_endpoint is not None:
        row.driver_endpoint = data.driver_endpoint
    if "no_answer_sound" in data.model_fields_set:
        row.no_answer_sound = data.no_answer_sound
    await session.flush()
    return _settings_view(row)


# The call log


def _call_view(row: Call) -> CallView:
    return CallView(
        id=row.id,
        line=row.line,
        caller_number=row.caller_number,
        customer_id=row.customer_id,
        customer_name=row.customer_name,
        status=row.status,
        started_at=row.started_at,
        answered_at=row.answered_at,
        ended_at=row.ended_at,
        answered_by=row.answered_by,
        answered_by_user=row.answered_by_user,
        end_reason=row.end_reason,
    )


async def start_call(
    session: AsyncSession, line: str, caller_number: str | None
) -> CallView:
    """Log a new ringing call, matched to a customer by caller ID.

    Returns:
        The call.
    """
    customer_id, customer_name = None, None
    if caller_number:
        try:
            match = await customers.find_by_phone(session, caller_number)
        except NotFoundError:
            pass
        else:
            customer_id, customer_name = match.customer.id, match.customer.name
    row = Call(
        id=new_id(),
        line=line,
        caller_number=caller_number or None,
        customer_id=customer_id,
        customer_name=customer_name,
        status=CallStatus.RINGING,
        started_at=_now(),
    )
    session.add(row)
    await session.flush()
    return _call_view(row)


async def _row(session: AsyncSession, call_id: EntityId) -> Call:
    row = await session.get(Call, call_id)
    if row is None:
        msg = f"call {call_id} not found"
        raise NotFoundError(msg)
    return row


async def mark_answered(
    session: AsyncSession,
    call_id: EntityId,
    endpoint: str,
    user_id: EntityId | None,
) -> None:
    """Record who answered."""
    row = await _row(session, call_id)
    row.status = CallStatus.ANSWERED
    row.answered_at = _now()
    row.answered_by = endpoint
    row.answered_by_user = user_id


async def end_call(session: AsyncSession, call_id: EntityId, reason: EndReason) -> None:
    """Record that a call ended: completed if answered, missed if not."""
    row = await _row(session, call_id)
    if row.ended_at is not None:
        return
    row.status = (
        CallStatus.COMPLETED if row.answered_at is not None else CallStatus.MISSED
    )
    row.ended_at = _now()
    row.end_reason = reason


async def interrupt_unfinished(session: AsyncSession) -> int:
    """Close calls left open by a restart; Asterisk has dropped them.

    Returns:
        How many calls were closed.
    """
    rows = list(
        await session.scalars(
            select(Call).where(
                Call.status.in_([CallStatus.RINGING, CallStatus.ANSWERED])
            )
        )
    )
    for row in rows:
        await end_call(session, row.id, EndReason.INTERRUPTED)
    return len(rows)


async def get_call(session: AsyncSession, call_id: EntityId) -> CallView:
    """Look up one call.

    Returns:
        The call.
    """
    return _call_view(await _row(session, call_id))


async def list_calls(session: AsyncSession, search: CallSearch) -> list[CallView]:
    """The call log, newest first.

    Returns:
        Up to ``search.limit`` calls.
    """
    query = select(Call).order_by(Call.id.desc()).limit(search.limit)
    if search.status is not None:
        query = query.where(Call.status == search.status)
    return [_call_view(row) for row in await session.scalars(query)]


async def active_calls(session: AsyncSession) -> list[CallView]:
    """Calls ringing or in progress, for the POS's incoming-call popup.

    Returns:
        The calls, oldest first.
    """
    rows = await session.scalars(
        select(Call)
        .where(Call.status.in_([CallStatus.RINGING, CallStatus.ANSWERED]))
        .order_by(Call.id)
    )
    return [_call_view(row) for row in rows]
