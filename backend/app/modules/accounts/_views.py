# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the accounts module. Other modules get them via ``api``."""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId
from app.core.money import Money


class EntryKind(StrEnum):
    """What a ledger line is."""

    CHARGE = "charge"
    """An on-account order: the customer owes its total."""
    PAYMENT = "payment"
    """The customer paid towards their balance."""
    ADJUSTMENT = "adjustment"
    """A correction by an admin, e.g. an opening balance or a write-off."""


class AccountPaymentMethod(StrEnum):
    """How a customer paid off debt."""

    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class EntryView(_View):
    """One line of a customer's account."""

    id: EntityId
    customer_id: EntityId
    kind: EntryKind
    amount: Money
    """Positive raises what the customer owes; negative lowers it."""
    order_id: EntityId | None
    method: AccountPaymentMethod | None
    """For payments: how they paid."""
    reference: str | None
    note: str | None
    override_reason: str | None
    """Why a charge over the credit limit was allowed."""
    occurred_at: datetime
    recorded_by: EntityId
    voided_at: datetime | None
    voided_by: EntityId | None
    void_reason: str | None


class AccountView(_View):
    """Where a customer stands."""

    customer_id: EntityId
    balance: Money
    """What they owe; negative means they paid in advance."""
    credit_limit: Money | None
    """The most they may owe; ``None`` is no limit."""
    available: Money | None
    """How much more they may buy on account, if there is a limit."""


class StatementLine(_View):
    """A ledger line with the balance after it."""

    entry: EntryView
    balance: Money
    """Running balance after this line (voided lines don't count)."""


class StatementView(_View):
    """A customer's account over a period."""

    customer_id: EntityId
    since: datetime | None
    until: datetime | None
    opening_balance: Money
    lines: list[StatementLine]
    closing_balance: Money


class DebtorView(_View):
    """A customer who owes something, for collecting."""

    customer_id: EntityId
    customer_name: str
    balance: Money
    credit_limit: Money | None
    last_payment_at: datetime | None
