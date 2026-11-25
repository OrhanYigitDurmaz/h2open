# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the containers module.

Orders and deliveries call :func:`exchange` when containers change hands.
"""

from typing import TYPE_CHECKING

from app.modules.containers import _service
from app.modules.containers._schemas import ExchangeCreate
from app.modules.containers._views import (
    BalanceView,
    ContainerCount,
    ExchangeResult,
    MovementKind,
    MovementView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId

__all__ = [
    "BalanceView",
    "ContainerCount",
    "ExchangeCreate",
    "ExchangeResult",
    "MovementKind",
    "MovementView",
    "balances",
    "exchange",
]


async def exchange(
    session: AsyncSession, data: ExchangeCreate, actor_id: EntityId
) -> ExchangeResult:
    """Record containers handed over in one visit.

    Args:
        session: The caller's database session; the movements are part of
            the caller's transaction.
        data: What was delivered and returned.
        actor_id: The user recording it.

    Returns:
        The movements and the deposit to charge or refund.
    """
    return await _service.exchange(session, data, actor_id)


async def balances(session: AsyncSession, customer_id: EntityId) -> list[BalanceView]:
    """The containers a customer holds now.

    Args:
        session: The caller's database session.
        customer_id: The customer.

    Returns:
        One entry per container type held.
    """
    return await _service.balances(session, customer_id)
