# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the accounts module.

Orders call :func:`charge` when an on-account order is completed.
"""

from typing import TYPE_CHECKING

from app.modules.accounts import _service
from app.modules.accounts._schemas import OrderCharge
from app.modules.accounts._views import (
    AccountPaymentMethod,
    AccountView,
    DebtorView,
    EntryKind,
    EntryView,
    StatementLine,
    StatementView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId

__all__ = [
    "AccountPaymentMethod",
    "AccountView",
    "DebtorView",
    "EntryKind",
    "EntryView",
    "OrderCharge",
    "StatementLine",
    "StatementView",
    "charge",
]


async def charge(
    session: AsyncSession, data: OrderCharge, actor_id: EntityId
) -> EntryView | None:
    """Put an on-account order on the customer's account.

    Args:
        session: The caller's session; the charge commits with the order.
        data: The customer, order, total and any credit-limit override.
        actor_id: Who completed the order.

    Returns:
        The ledger line, or ``None`` if there was nothing to pay. An
        ``OverrideRequiredError`` is raised instead if the order takes the
        customer over their credit limit without a reason.
    """
    return await _service.charge(session, data, actor_id)
