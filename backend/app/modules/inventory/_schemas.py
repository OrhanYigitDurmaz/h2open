# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the inventory endpoints. Private to this module."""

from typing import Annotated, Self

from pydantic import (
    BaseModel,
    Field,
    NonNegativeInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.ids import EntityId
from app.modules.inventory._views import ItemKind, MovementReason

type Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class StockChange(BaseModel):
    """Stock of one item going up or down."""

    kind: ItemKind
    item_id: EntityId
    change: int


class AdjustmentCreate(BaseModel):
    """A correction to one item's stock, with the reason for it."""

    kind: ItemKind
    item_id: EntityId
    change: int
    """Positive to add, negative to remove (e.g. ``-2`` for two leaking)."""
    reason: Text

    @field_validator("change")
    @classmethod
    def _not_zero(cls, change: int) -> int:
        if change == 0:
            msg = "the change cannot be zero"
            raise ValueError(msg)
        return change


class CountedItem(BaseModel):
    """How many of one item were found."""

    kind: ItemKind
    item_id: EntityId
    counted: NonNegativeInt


class CountCreate(BaseModel):
    """The result of counting stock. Items left out are not changed."""

    items: Annotated[list[CountedItem], Field(min_length=1)]
    note: Text | None = None

    @model_validator(mode="after")
    def _unique(self) -> Self:
        keys = [(item.kind, item.item_id) for item in self.items]
        if len(set(keys)) != len(keys):
            msg = "list each item once"
            raise ValueError(msg)
        return self


class MovementSearch(BaseModel):
    """Query parameters for the stock ledger."""

    kind: ItemKind | None = None
    item_id: EntityId | None = None
    reason: MovementReason | None = None
    source_id: EntityId | None = None
    limit: Annotated[int, Field(ge=1, le=500)] = 100
