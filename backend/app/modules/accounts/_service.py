# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Customer balances, payments and credit limits. Private to this module."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, func, select

from app.core.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    OverrideRequiredError,
)
from app.core.ids import new_id
from app.core.money import Money
from app.modules.accounts._models import CreditLimit, Entry
from app.modules.accounts._views import (
    AccountView,
    DebtorView,
    EntryKind,
    EntryView,
    StatementLine,
    StatementView,
)
from app.modules.customers import api as customers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.accounts._schemas import (
        AdjustmentCreate,
        CreditLimitUpdate,
        OrderCharge,
        PaymentCreate,
        StatementQuery,
        Void,
    )

CURRENCY = "TRY"
"""Accounts are kept in one currency, so a balance is a single number."""
CENT = Decimal("0.01")
LOCK_SPACE = 0x4143  # "AC": keeps these advisory locks apart from others


def _now() -> datetime:
    return datetime.now(UTC)


def _try(amount: Decimal) -> Money:
    return Money(amount=amount, currency=CURRENCY)


def _entry_view(row: Entry) -> EntryView:
    return EntryView(
        id=row.id,
        customer_id=row.customer_id,
        kind=row.kind,
        amount=_try(row.amount),
        order_id=row.order_id,
        method=row.method,
        reference=row.reference,
        note=row.note,
        override_reason=row.override_reason,
        occurred_at=row.occurred_at,
        recorded_by=row.recorded_by,
        voided_at=row.voided_at,
        voided_by=row.voided_by,
        void_reason=row.void_reason,
    )


async def _lock(session: AsyncSession, customer_id: EntityId) -> None:
    """Serialise changes to one account until the transaction ends.

    Two on-account orders completed at once would otherwise both see the
    old balance and could together go over the credit limit.
    """
    key = int.from_bytes(customer_id.bytes[:4], "big", signed=True)
    _ = await session.execute(select(func.pg_advisory_xact_lock(LOCK_SPACE, key)))


def _counts() -> ColumnElement[bool]:
    return Entry.voided_at.is_(None)


async def _balance(
    session: AsyncSession, customer_id: EntityId, before: datetime | None = None
) -> Decimal:
    query = select(func.coalesce(func.sum(Entry.amount), 0)).where(
        Entry.customer_id == customer_id, _counts()
    )
    if before is not None:
        query = query.where(Entry.occurred_at < before)
    return Decimal(await session.scalar(query) or 0)


async def _limit(session: AsyncSession, customer_id: EntityId) -> Decimal | None:
    row = await session.get(CreditLimit, customer_id)
    return None if row is None else row.amount


def _account(
    customer_id: EntityId, balance: Decimal, limit: Decimal | None
) -> AccountView:
    return AccountView(
        customer_id=customer_id,
        balance=_try(balance),
        credit_limit=None if limit is None else _try(limit),
        available=None if limit is None else _try(max(limit - balance, Decimal(0))),
    )


async def account(session: AsyncSession, customer_id: EntityId) -> AccountView:
    """Where a customer stands.

    Returns:
        The balance and credit limit.
    """
    _ = await customers.get_customer(session, customer_id)
    return _account(
        customer_id,
        await _balance(session, customer_id),
        await _limit(session, customer_id),
    )


# Charges from orders


async def charge(
    session: AsyncSession, data: OrderCharge, actor_id: EntityId
) -> EntryView | None:
    """Put an on-account order on the customer's account.

    Returns:
        The ledger line, or ``None`` for an order with nothing to pay.

    Raises:
        DomainError: The order is not in the account currency.
        OverrideRequiredError: It takes the customer over their credit limit
            and no reason was given to allow it.
    """
    total = data.total or _try(Decimal(0))
    if total.currency != CURRENCY:
        msg = f"accounts are kept in {CURRENCY}, not {total.currency}"
        raise DomainError(msg)
    customer_id = data.customer_id
    amount = total.amount.quantize(CENT, ROUND_HALF_UP)
    if amount == 0:
        return None
    await _lock(session, customer_id)
    limit = await _limit(session, customer_id)
    balance = await _balance(session, customer_id)
    over = limit is not None and amount > 0 and balance + amount > limit
    if over and data.override_reason is None:
        msg = (
            f"this takes the balance to {balance + amount} {CURRENCY}, over the"
            f" credit limit of {limit}; send credit_override_reason to allow it"
        )
        raise OverrideRequiredError(msg)
    row = Entry(
        id=new_id(),
        customer_id=customer_id,
        kind=EntryKind.CHARGE,
        amount=amount,
        order_id=data.order_id,
        override_reason=data.override_reason if over else None,
        occurred_at=_now(),
        recorded_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return _entry_view(row)


# Payments and corrections


async def _append(session: AsyncSession, row: Entry) -> EntryView:
    """Add a line to a customer's account, locked against concurrent changes.

    Returns:
        The line.
    """
    _ = await customers.get_customer(session, row.customer_id)
    await _lock(session, row.customer_id)
    session.add(row)
    await session.flush()
    return _entry_view(row)


async def record_payment(
    session: AsyncSession, data: PaymentCreate, actor_id: EntityId
) -> EntryView:
    """Record a customer paying towards their balance.

    Returns:
        The ledger line.
    """
    row = Entry(
        id=new_id(),
        customer_id=data.customer_id,
        kind=EntryKind.PAYMENT,
        amount=-data.amount,
        method=data.method,
        reference=data.reference,
        note=data.note,
        occurred_at=_now(),
        recorded_by=actor_id,
    )
    return await _append(session, row)


async def adjust(
    session: AsyncSession, data: AdjustmentCreate, actor_id: EntityId
) -> EntryView:
    """Correct a balance, e.g. to enter what a customer owed before h2open.

    Returns:
        The ledger line.
    """
    row = Entry(
        id=new_id(),
        customer_id=data.customer_id,
        kind=EntryKind.ADJUSTMENT,
        amount=data.amount,
        note=data.reason,
        occurred_at=_now(),
        recorded_by=actor_id,
    )
    return await _append(session, row)


async def void(
    session: AsyncSession, entry_id: EntityId, data: Void, actor_id: EntityId
) -> EntryView:
    """Void a payment or adjustment entered by mistake.

    Returns:
        The voided line.

    Raises:
        NotFoundError: No such line.
        DomainError: It is an order's charge, which belongs to the order.
        ConflictError: It is already voided.
    """
    row = await session.get(Entry, entry_id, with_for_update=True)
    if row is None:
        msg = f"account entry {entry_id} not found"
        raise NotFoundError(msg)
    if row.kind is EntryKind.CHARGE:
        msg = "order charges cannot be voided; adjust the balance instead"
        raise DomainError(msg)
    if row.voided_at is not None:
        msg = "the entry is already voided"
        raise ConflictError(msg)
    row.voided_at = _now()
    row.voided_by = actor_id
    row.void_reason = data.reason
    await session.flush()
    return _entry_view(row)


async def set_limit(
    session: AsyncSession, customer_id: EntityId, data: CreditLimitUpdate
) -> AccountView:
    """Set or remove a customer's credit limit.

    Returns:
        Where the customer stands now.
    """
    _ = await customers.get_customer(session, customer_id)
    row = await session.get(CreditLimit, customer_id)
    if data.amount is None:
        if row is not None:
            await session.delete(row)
    elif row is None:
        session.add(CreditLimit(customer_id=customer_id, amount=data.amount))
    else:
        row.amount = data.amount
    await session.flush()
    return await account(session, customer_id)


# Reading


async def statement(
    session: AsyncSession, customer_id: EntityId, query: StatementQuery
) -> StatementView:
    """A customer's account over a period, with a running balance.

    Returns:
        The opening balance, every line (voided ones marked) and the
        closing balance.
    """
    _ = await customers.get_customer(session, customer_id)
    opening = (
        Decimal(0)
        if query.since is None
        else await _balance(session, customer_id, before=query.since)
    )
    rows = select(Entry).where(Entry.customer_id == customer_id)
    if query.since is not None:
        rows = rows.where(Entry.occurred_at >= query.since)
    if query.until is not None:
        rows = rows.where(Entry.occurred_at < query.until)
    running = opening
    lines: list[StatementLine] = []
    for row in await session.scalars(rows.order_by(Entry.occurred_at, Entry.id)):
        if row.voided_at is None:
            running += row.amount
        lines.append(StatementLine(entry=_entry_view(row), balance=_try(running)))
    return StatementView(
        customer_id=customer_id,
        since=query.since,
        until=query.until,
        opening_balance=_try(opening),
        lines=lines,
        closing_balance=_try(running),
    )


async def debtors(session: AsyncSession) -> list[DebtorView]:
    """Customers who owe something, most first.

    Returns:
        The debtors.
    """
    balance = func.sum(Entry.amount)
    last_payment = func.max(Entry.occurred_at).filter(Entry.kind == EntryKind.PAYMENT)
    rows = await session.execute(
        select(Entry.customer_id, balance, last_payment)
        .where(_counts())
        .group_by(Entry.customer_id)
        .having(balance > 0)
        .order_by(balance.desc(), Entry.customer_id)
    )
    views: list[DebtorView] = []
    for customer_id, owed, paid_at in rows:
        customer = await customers.get_customer(session, customer_id)
        limit = await _limit(session, customer_id)
        views.append(
            DebtorView(
                customer_id=customer_id,
                customer_name=customer.name,
                balance=_try(owed),
                credit_limit=None if limit is None else _try(limit),
                last_payment_at=paid_at,
            )
        )
    return views
