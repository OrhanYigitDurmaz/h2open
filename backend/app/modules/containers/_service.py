# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Container ledger logic. Private to this module.

Deposits are tracked per container ("lots"), oldest first. A customer who
paid 150 for one carboy and 200 for another holds two lots; returning one
carboy under the "paid amount" policy refunds the oldest, 150.
"""

from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.core.errors import DomainError, OverrideRequiredError
from app.core.ids import new_id
from app.core.money import Money
from app.modules.catalog import api as catalog
from app.modules.company import api as company
from app.modules.containers._models import Movement
from app.modules.containers._planning import Step, plan_exchange
from app.modules.containers._views import (
    BalanceView,
    ContainerCount,
    ExchangeResult,
    MovementKind,
    MovementView,
)
from app.modules.customers import api as customers

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.containers._schemas import ExchangeCreate

type Lots = defaultdict[EntityId, deque[Money]]


def _movement_view(row: Movement) -> MovementView:
    return MovementView(
        id=row.id,
        exchange_id=row.exchange_id,
        customer_id=row.customer_id,
        container_type_id=row.container_type_id,
        kind=row.kind,
        quantity=row.quantity,
        balance_change=row.balance_change,
        unit_deposit=Money(amount=row.unit_deposit, currency=row.currency),
        occurred_at=row.occurred_at,
        override_reason=row.override_reason,
        note=row.note,
    )


async def _lock(session: AsyncSession, customer_id: EntityId) -> None:
    """Serialise exchanges per customer until the transaction ends.

    Two drivers recording for the same customer at once would otherwise
    both see the same lots and could refund the same deposit twice.
    """
    key = int.from_bytes(customer_id.bytes[:8], "big", signed=True)
    _ = await session.execute(select(func.pg_advisory_xact_lock(key)))


async def _lots(session: AsyncSession, customer_id: EntityId) -> Lots:
    """Replay the ledger into the deposit lots the customer holds now.

    Returns:
        Per container type, the deposit of each container held, oldest first.
    """
    lots: Lots = defaultdict(deque)
    rows = await session.scalars(
        select(Movement)
        .where(Movement.customer_id == customer_id)
        .order_by(Movement.id)
    )
    for row in rows:
        held = lots[row.container_type_id]
        if row.balance_change > 0:
            value = Money(amount=row.unit_deposit, currency=row.currency)
            held.extend([value] * row.quantity)
        else:
            for _ in range(row.quantity):
                _ = held.popleft()
    return lots


def _group(values: Iterable[Money]) -> list[tuple[Money, int]]:
    """Collapse runs of equal deposits, so each ledger row has one unit price.

    Returns:
        ``(deposit, count)`` pairs in order.
    """
    groups: list[tuple[Money, int]] = []
    for value in values:
        if groups and groups[-1][0] == value:
            groups[-1] = (value, groups[-1][1] + 1)
        else:
            groups.append((value, 1))
    return groups


def _total(rows: Iterable[Movement], kind: MovementKind) -> Money | None:
    total: Money | None = None
    for row in rows:
        if row.kind is kind:
            amount = Money(
                amount=row.unit_deposit * row.quantity, currency=row.currency
            )
            total = amount if total is None else total + amount
    return total


class _Ledger:
    """Turns planned steps into ledger rows, updating the lots as it goes."""

    def __init__(
        self,
        data: ExchangeCreate,
        lots: Lots,
        types: Mapping[EntityId, catalog.ContainerTypeView],
        policy: company.DepositRefundPolicy,
    ) -> None:
        self.exchange_id: EntityId = new_id()
        self.rows: list[Movement] = []
        self._data: ExchangeCreate = data
        self._lots: Lots = lots
        self._types: Mapping[EntityId, catalog.ContainerTypeView] = types
        self._policy: company.DepositRefundPolicy = policy
        self._now: datetime = datetime.now(UTC)

    def apply(self, step: Step) -> None:
        """Record one step."""
        match step.kind:
            case MovementKind.ISSUE:
                self._issue(step)
            case MovementKind.RETURN:
                self._return(step)
            case MovementKind.TRANSFER_OUT:
                self._transfer(step)
            case _:  # swaps change nothing
                pass

    def _record(self, kind: MovementKind, step: Step, unit: Money, count: int) -> None:
        type_id = (
            step.target if kind is MovementKind.TRANSFER_IN else step.container_type_id
        )
        sign = 1 if kind in {MovementKind.ISSUE, MovementKind.TRANSFER_IN} else -1
        self.rows.append(
            Movement(
                id=new_id(),
                exchange_id=self.exchange_id,
                customer_id=self._data.customer_id,
                container_type_id=type_id,
                kind=kind,
                quantity=count,
                balance_change=sign * count,
                unit_deposit=unit.amount,
                currency=unit.currency,
                occurred_at=self._now,
                override_reason=self._data.override_reason,
                note=self._data.note,
            )
        )

    def _current_deposit(self, type_id: EntityId) -> Money:
        """The deposit in effect now.

        Returns:
            The deposit.

        Raises:
            DomainError: The container type has no deposit price yet.
        """
        container_type = self._types[type_id]
        if container_type.deposit is None:
            msg = f"no deposit price is set for {container_type.name!r}"
            raise DomainError(msg)
        return container_type.deposit

    def _issue(self, step: Step) -> None:
        deposit = self._current_deposit(step.container_type_id)
        self._record(MovementKind.ISSUE, step, deposit, step.quantity)
        self._lots[step.container_type_id].extend([deposit] * step.quantity)

    def _pop(self, type_id: EntityId, quantity: int) -> list[Money]:
        held = self._lots[type_id]
        return [held.popleft() for _ in range(quantity)]

    def _return(self, step: Step) -> None:
        paid = self._pop(step.container_type_id, step.quantity)
        match self._policy:
            case company.DepositRefundPolicy.PAID_AMOUNT:
                refunds = paid
            case company.DepositRefundPolicy.CURRENT_PRICE:
                refunds = [self._current_deposit(step.container_type_id)] * len(paid)
            case _:  # DepositRefundPolicy.NONE, the only one left
                refunds = [Money.zero(value.currency) for value in paid]
        for unit, count in _group(refunds):
            self._record(MovementKind.RETURN, step, unit, count)

    def _transfer(self, step: Step) -> None:
        moved = self._pop(step.container_type_id, step.quantity)
        for unit, count in _group(moved):
            self._record(MovementKind.TRANSFER_OUT, step, unit, count)
            self._record(MovementKind.TRANSFER_IN, step, unit, count)
        self._lots[step.target].extend(moved)


async def _container_types(
    session: AsyncSession, data: ExchangeCreate
) -> dict[EntityId, catalog.ContainerTypeView]:
    """Load every container type in the exchange.

    Returns:
        The container types by ID.

    Raises:
        DomainError: A delivered container type is inactive.
    """
    delivered = data.delivered_by_type()
    type_ids = delivered.keys() | data.returned_by_type().keys()
    types = {
        type_id: await catalog.get_container_type(session, type_id)
        for type_id in sorted(type_ids)
    }
    for type_id in delivered:
        if not types[type_id].active:
            msg = f"container type {types[type_id].name!r} is inactive"
            raise DomainError(msg)
    return types


def _check_holdings(
    lots: Lots,
    returned: Mapping[EntityId, int],
    types: Mapping[EntityId, catalog.ContainerTypeView],
) -> None:
    """Customers can only return containers they hold.

    Raises:
        DomainError: More empties returned than the customer holds.
    """
    for type_id, quantity in returned.items():
        held = len(lots[type_id])
        if quantity > held:
            msg = (
                f"the customer holds {held} x {types[type_id].name!r}"
                f" but is returning {quantity}"
            )
            raise DomainError(msg)


async def _active_customer(session: AsyncSession, customer_id: EntityId) -> None:
    """Check that the customer exists and is active.

    Raises:
        DomainError: The customer is inactive.
    """
    customer = await customers.get_customer(session, customer_id)
    if not customer.active:
        msg = f"customer {customer.name!r} is inactive"
        raise DomainError(msg)


async def exchange(session: AsyncSession, data: ExchangeCreate) -> ExchangeResult:
    """Record containers handed over in one visit.

    Returns:
        The movements and the deposit to charge or refund.

    Raises:
        OverrideRequiredError: Empties of another type were returned and no
            override reason was given.
    """
    await _active_customer(session, data.customer_id)
    plan = plan_exchange(data.delivered_by_type(), data.returned_by_type())
    if plan.mismatched and data.override_reason is None:
        msg = (
            "the returned empties are a different container type than the"
            " delivered ones; send an override_reason to accept them anyway"
        )
        raise OverrideRequiredError(msg)
    types = await _container_types(session, data)
    await _lock(session, data.customer_id)
    lots = await _lots(session, data.customer_id)
    _check_holdings(lots, data.returned_by_type(), types)

    settings = await company.get_settings(session)
    ledger = _Ledger(data, lots, types, settings.deposit_refund_policy)
    for step in plan.steps:
        ledger.apply(step)
    session.add_all(ledger.rows)
    await session.flush()
    return ExchangeResult(
        exchange_id=ledger.exchange_id,
        swapped=[
            ContainerCount(
                container_type_id=step.container_type_id, quantity=step.quantity
            )
            for step in plan.steps
            if step.kind is None
        ],
        movements=[_movement_view(row) for row in ledger.rows],
        deposit_charged=_total(ledger.rows, MovementKind.ISSUE),
        deposit_refunded=_total(ledger.rows, MovementKind.RETURN),
    )


async def balances(session: AsyncSession, customer_id: EntityId) -> list[BalanceView]:
    """The containers a customer holds now, per type.

    Returns:
        One entry per container type the customer holds at least one of.
    """
    _ = await customers.get_customer(session, customer_id)
    lots = await _lots(session, customer_id)
    views: list[BalanceView] = []
    for type_id, held in sorted(lots.items()):
        if held:
            total = Money.zero(held[0].currency)
            for value in held:
                total += value
            views.append(
                BalanceView(
                    container_type_id=type_id, quantity=len(held), deposit_held=total
                )
            )
    return views


async def movements(session: AsyncSession, customer_id: EntityId) -> list[MovementView]:
    """A customer's container ledger, newest first.

    Returns:
        Every movement.
    """
    _ = await customers.get_customer(session, customer_id)
    rows = await session.scalars(
        select(Movement)
        .where(Movement.customer_id == customer_id)
        .order_by(Movement.id.desc())
    )
    return [_movement_view(row) for row in rows]
