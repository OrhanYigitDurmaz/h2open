# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stock logic. Private to this module."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import DomainError
from app.core.ids import new_id
from app.modules.catalog import api as catalog
from app.modules.company import api as company
from app.modules.inventory._models import Level, Movement
from app.modules.inventory._views import (
    ItemKind,
    MovementReason,
    MovementView,
    StockLevelView,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.inventory._schemas import (
        AdjustmentCreate,
        CountCreate,
        MovementSearch,
        StockChange,
    )

type Item = tuple[ItemKind, EntityId]


@dataclass(frozen=True, slots=True)
class Source:
    """Who changed stock, and what for."""

    reason: MovementReason
    actor_id: EntityId
    source_id: EntityId | None = None
    note: str | None = None


def _movement_view(row: Movement) -> MovementView:
    return MovementView(
        id=row.id,
        kind=row.kind,
        item_id=row.item_id,
        change=row.change,
        reason=row.reason,
        source_id=row.source_id,
        occurred_at=row.occurred_at,
        recorded_by=row.recorded_by,
        note=row.note,
    )


async def _name(session: AsyncSession, item: Item) -> str:
    """A readable name for an item, for error messages.

    Returns:
        The product's name, or "empty <container type>".
    """
    kind, item_id = item
    if kind is ItemKind.PRODUCT:
        return (await catalog.get_product(session, item_id)).name
    return f"empty {(await catalog.get_container_type(session, item_id)).name}"


async def _bump(session: AsyncSession, item: Item, change: int) -> int:
    """Add to an item's level, creating it at zero first if needed.

    The row stays locked until the transaction ends.

    Returns:
        The level afterwards.
    """
    kind, item_id = item
    statement = (
        insert(Level)
        .values(kind=kind, item_id=item_id, quantity=change)
        .on_conflict_do_update(
            index_elements=[Level.kind, Level.item_id],
            set_={"quantity": Level.quantity + change},
        )
        .returning(Level.quantity)
    )
    return (await session.execute(statement)).scalar_one()


@dataclass(frozen=True, slots=True)
class _Moved:
    row: Movement
    level: int
    """The item's level afterwards."""


async def _move(
    session: AsyncSession, item: Item, change: int, source: Source
) -> _Moved:
    """Change one item's stock and add the ledger line.

    Returns:
        The ledger line and the new level.
    """
    level = await _bump(session, item, change)
    kind, item_id = item
    row = Movement(
        id=new_id(),
        kind=kind,
        item_id=item_id,
        change=change,
        reason=source.reason,
        source_id=source.source_id,
        occurred_at=datetime.now(UTC),
        recorded_by=source.actor_id,
        note=source.note,
    )
    session.add(row)
    return _Moved(row=row, level=level)


async def _check_level(
    session: AsyncSession, item: Item, moved: _Moved, *, allowed: bool
) -> None:
    """Refuse a removal that took stock below zero, if the company says so.

    Raises:
        DomainError: Stock went negative and that is not allowed.
    """
    change = moved.row.change
    if allowed or change >= 0 or moved.level >= 0:
        return
    name = await _name(session, item)
    msg = (
        f"not enough stock of {name!r}: {moved.level - change} on hand,"
        f" {-change} needed"
    )
    raise DomainError(msg)


async def record(
    session: AsyncSession, changes: Iterable[StockChange], source: Source
) -> list[MovementView]:
    """Apply stock changes in one go, as part of the caller's transaction.

    Changes to the same item are combined. Items are locked in a fixed
    order, so concurrent callers cannot deadlock.

    Returns:
        The ledger lines written.
    """
    totals: Counter[Item] = Counter()
    for change in changes:
        totals[change.kind, change.item_id] += change.change
    settings = await company.get_settings(session)
    rows: list[Movement] = []
    for item, change in sorted(totals.items()):
        if change:
            moved = await _move(session, item, change, source)
            await _check_level(
                session, item, moved, allowed=settings.negative_stock_allowed
            )
            rows.append(moved.row)
    await session.flush()
    return [_movement_view(row) for row in rows]


async def _check_item(session: AsyncSession, item: Item) -> None:
    """Check that the product or container type exists."""
    _ = await _name(session, item)


async def adjust(
    session: AsyncSession, data: AdjustmentCreate, actor_id: EntityId
) -> MovementView:
    """Correct one item's stock.

    Returns:
        The ledger line.
    """
    item = (data.kind, data.item_id)
    await _check_item(session, item)
    source = Source(MovementReason.ADJUSTMENT, actor_id, note=data.reason)
    settings = await company.get_settings(session)
    moved = await _move(session, item, data.change, source)
    await _check_level(session, item, moved, allowed=settings.negative_stock_allowed)
    await session.flush()
    return _movement_view(moved.row)


async def count(
    session: AsyncSession, data: CountCreate, actor_id: EntityId
) -> list[MovementView]:
    """Set stock to what was counted, recording each difference.

    Returns:
        The ledger lines, one per item whose stock was wrong.
    """
    source = Source(MovementReason.COUNT, actor_id, note=data.note)
    rows: list[Movement] = []
    for counted in sorted(data.items, key=lambda c: (c.kind, c.item_id)):
        item = (counted.kind, counted.item_id)
        await _check_item(session, item)
        difference = counted.counted - await _bump(session, item, 0)
        if difference:
            rows.append((await _move(session, item, difference, source)).row)
    await session.flush()
    return [_movement_view(row) for row in rows]


async def levels(session: AsyncSession, kind: ItemKind | None) -> list[StockLevelView]:
    """What we have on hand.

    Returns:
        Every item that ever had stock, by kind and ID.
    """
    query = select(Level).order_by(Level.kind, Level.item_id)
    if kind is not None:
        query = query.where(Level.kind == kind)
    return [
        StockLevelView(kind=row.kind, item_id=row.item_id, quantity=row.quantity)
        for row in await session.scalars(query)
    ]


async def movements(
    session: AsyncSession, search: MovementSearch
) -> list[MovementView]:
    """The stock ledger, newest first.

    Returns:
        Up to ``search.limit`` matching lines.
    """
    query = select(Movement).order_by(Movement.id.desc()).limit(search.limit)
    if search.kind is not None:
        query = query.where(Movement.kind == search.kind)
    if search.item_id is not None:
        query = query.where(Movement.item_id == search.item_id)
    if search.reason is not None:
        query = query.where(Movement.reason == search.reason)
    if search.source_id is not None:
        query = query.where(Movement.source_id == search.source_id)
    return [_movement_view(row) for row in await session.scalars(query)]
