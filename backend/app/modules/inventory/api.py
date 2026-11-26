# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the inventory module.

Orders, container exchanges and supplier receipts call :func:`record`
whenever goods or empties come in or go out.
"""

from typing import TYPE_CHECKING

from app.modules.inventory import _service
from app.modules.inventory._schemas import StockChange
from app.modules.inventory._service import Source
from app.modules.inventory._views import (
    ItemKind,
    MovementReason,
    MovementView,
    StockLevelView,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ItemKind",
    "MovementReason",
    "MovementView",
    "Source",
    "StockChange",
    "StockLevelView",
    "record",
]


async def record(
    session: AsyncSession, changes: Iterable[StockChange], source: Source
) -> list[MovementView]:
    """Move stock in or out, as part of the caller's transaction.

    Args:
        session: The caller's database session.
        changes: Per item, how much comes in (positive) or goes out
            (negative). Zero changes are skipped.
        source: Why, by whom, and the document behind it.

    Returns:
        The ledger lines written. A ``DomainError`` is raised instead if
        stock would go below zero while the company setting forbids it.
    """
    return await _service.record(session, changes, source)
