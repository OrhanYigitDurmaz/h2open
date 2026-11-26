# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stock tables, in the ``inventory`` schema. Private to this module.

Products and container types belong to the catalog, so ``item_id`` is a
plain ID without a foreign key.
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import module_metadata
from app.core.ids import new_id
from app.modules.inventory._views import ItemKind, MovementReason


def _kind() -> Enum:
    return Enum(
        ItemKind, name="item_kind", native_enum=False, create_constraint=True, length=20
    )


class Base(DeclarativeBase):
    """Base for inventory tables."""

    metadata: ClassVar[MetaData] = module_metadata("inventory")


class Level(Base):
    """The quantity on hand of one item, kept in step with the ledger.

    Updating this row also locks it, so two sales of the same product
    cannot both take the last one.
    """

    __tablename__: str = "levels"

    kind: Mapped[ItemKind] = mapped_column(_kind(), primary_key=True)
    item_id: Mapped[UUID] = mapped_column(primary_key=True)
    quantity: Mapped[int] = mapped_column()


class Movement(Base):
    """One append-only ledger line. Rows are never updated or deleted."""

    __tablename__: str = "movements"
    __table_args__: tuple[CheckConstraint | Index, ...] = (
        CheckConstraint("change <> 0", name="change_not_zero"),
        Index("ix_movements_item", "kind", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    kind: Mapped[ItemKind] = mapped_column(_kind())
    item_id: Mapped[UUID] = mapped_column()
    change: Mapped[int] = mapped_column()
    reason: Mapped[MovementReason] = mapped_column(
        Enum(
            MovementReason,
            name="movement_reason",
            native_enum=False,
            create_constraint=True,
            length=20,
        )
    )
    source_id: Mapped[UUID | None] = mapped_column(index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[UUID] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(500))
