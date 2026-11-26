# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the inventory module. Other modules get them via ``api``."""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId


class ItemKind(StrEnum):
    """What kind of thing a stock level counts."""

    PRODUCT = "product"
    """Goods we sell, counted in product units (a 19 L carboy, a pack)."""
    EMPTY = "empty"
    """Empty returnable containers, counted per container type."""


class MovementReason(StrEnum):
    """Why stock changed."""

    PURCHASE = "purchase"
    """Goods arrived on a supplier's receipt, or empties went back with it."""
    PURCHASE_VOID = "purchase_void"
    """A receipt entered by mistake was voided; its movements are reversed."""
    SALE = "sale"
    """Goods handed over on a completed order."""
    CUSTOMER_RETURN = "customer_return"
    """Empties a customer gave back."""
    ADJUSTMENT = "adjustment"
    """A correction by an admin: breakage, leaks, giveaways."""
    COUNT = "count"
    """The difference found when stock was counted."""


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class StockLevelView(_View):
    """How many of one item we have now. Negative means paperwork is missing."""

    kind: ItemKind
    item_id: EntityId
    """A product ID or a container type ID, depending on ``kind``."""
    quantity: int


class MovementView(_View):
    """One line of the stock ledger."""

    id: EntityId
    kind: ItemKind
    item_id: EntityId
    change: int
    """Positive for stock in, negative for stock out."""
    reason: MovementReason
    source_id: EntityId | None
    """The receipt, order or container exchange behind it, if any."""
    occurred_at: datetime
    recorded_by: EntityId
    note: str | None
