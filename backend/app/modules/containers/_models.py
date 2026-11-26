# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Container ledger table, in the ``containers`` schema. Private to this module."""

from datetime import datetime
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, MetaData, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import enum_column, module_metadata
from app.core.ids import new_id
from app.modules.containers._views import MovementKind


class Base(DeclarativeBase):
    """Base for container tables."""

    metadata: ClassVar[MetaData] = module_metadata("containers")


class Movement(Base):
    """One append-only ledger line. Rows are never updated or deleted.

    ``customer_id`` and ``container_type_id`` belong to other modules, so
    they are plain IDs without foreign keys.
    """

    __tablename__: str = "movements"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "balance_change = quantity OR balance_change = -quantity",
            name="balance_change_matches_quantity",
        ),
        CheckConstraint("unit_deposit >= 0", name="unit_deposit_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    exchange_id: Mapped[UUID] = mapped_column(index=True)
    customer_id: Mapped[UUID] = mapped_column(index=True)
    container_type_id: Mapped[UUID] = mapped_column()
    kind: Mapped[MovementKind] = mapped_column(
        enum_column(MovementKind, "movement_kind")
    )
    quantity: Mapped[int] = mapped_column()
    balance_change: Mapped[int] = mapped_column()
    unit_deposit: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    currency: Mapped[str] = mapped_column(String(3))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[UUID] = mapped_column()
    """The user who recorded it (identity module)."""
    override_reason: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(String(500))
