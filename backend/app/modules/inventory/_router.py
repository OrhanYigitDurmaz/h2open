# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the inventory module. Private to this module."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.db import SessionDep
from app.modules.identity import api as identity
from app.modules.inventory import _service
from app.modules.inventory._schemas import AdjustmentCreate, CountCreate, MovementSearch
from app.modules.inventory._views import ItemKind, MovementView, StockLevelView

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(identity.current_actor)],
)


@router.get("/stock")
async def stock(
    session: SessionDep, kind: ItemKind | None = None
) -> list[StockLevelView]:
    """What we have on hand: full goods per product, empties per container type.

    Returns:
        Every item that ever had stock.
    """
    return await _service.levels(session, kind)


@router.get("/movements")
async def movements(
    session: SessionDep, search: Annotated[MovementSearch, Query()]
) -> list[MovementView]:
    """The stock ledger, newest first, optionally filtered.

    Returns:
        The matching ledger lines.
    """
    return await _service.movements(session, search)


@router.post("/adjustments", status_code=HTTPStatus.CREATED)
async def adjust(
    session: SessionDep, actor: identity.AdminActor, data: AdjustmentCreate
) -> MovementView:
    """Correct one item's stock, e.g. for breakage. Admins only.

    Returns:
        The ledger line.
    """
    return await _service.adjust(session, data, actor.id)


@router.post("/counts", status_code=HTTPStatus.CREATED)
async def count(
    session: SessionDep, actor: identity.AdminActor, data: CountCreate
) -> list[MovementView]:
    """Record a stock count; each item is set to what was counted. Admins only.

    Returns:
        One ledger line per item whose stock differed from the count.
    """
    return await _service.count(session, data, actor.id)
