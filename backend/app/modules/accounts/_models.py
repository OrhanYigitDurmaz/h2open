# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Account tables, in the ``accounts`` schema. Private to this module.

Amounts are in the account currency, TRY.

Customers, orders and users belong to other modules, so they are plain IDs.
Entries are never edited: mistakes are voided, which keeps them visible.
"""

from datetime import datetime
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
    Numeric,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import enum_column, module_metadata
from app.core.ids import new_id
from app.modules.accounts._views import AccountPaymentMethod, EntryKind

AMOUNT = Numeric(14, 2)


class Base(DeclarativeBase):
    """Base for account tables."""

    metadata: ClassVar[MetaData] = module_metadata("accounts")


class Entry(Base):
    """One ledger line of a customer's account."""

    __tablename__: str = "entries"
    __table_args__: tuple[CheckConstraint | Index, ...] = (
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        CheckConstraint(
            "kind <> 'PAYMENT' OR (amount < 0 AND method IS NOT NULL)",
            name="payments_lower_the_balance",
        ),
        CheckConstraint(
            "(kind = 'CHARGE') = (order_id IS NOT NULL)", name="charges_have_order"
        ),
        # An order is charged to an account once.
        Index("ux_entries_order", "order_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    customer_id: Mapped[UUID] = mapped_column(index=True)
    kind: Mapped[EntryKind] = mapped_column(enum_column(EntryKind, "entry_kind"))
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
    """In the account currency (TRY)."""
    order_id: Mapped[UUID | None] = mapped_column()
    method: Mapped[AccountPaymentMethod | None] = mapped_column(
        enum_column(AccountPaymentMethod, "account_payment_method")
    )
    reference: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(500))
    override_reason: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[UUID] = mapped_column(index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[UUID | None] = mapped_column()
    void_reason: Mapped[str | None] = mapped_column(String(500))


class CreditLimit(Base):
    """The most a customer may owe. No row means no limit."""

    __tablename__: str = "credit_limits"
    __table_args__: tuple[CheckConstraint] = (
        CheckConstraint("amount >= 0", name="amount_not_negative"),
    )

    customer_id: Mapped[UUID] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
