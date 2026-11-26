# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the accounts module. Private to this module."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.accounts import _service
from app.modules.accounts._schemas import (
    AdjustmentCreate,
    CreditLimitUpdate,
    PaymentCreate,
    StatementQuery,
    Void,
)
from app.modules.accounts._views import (
    AccountView,
    DebtorView,
    EntryView,
    StatementView,
)
from app.modules.identity import api as identity

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    dependencies=[Depends(identity.current_actor)],
)


@router.get("/debtors")
async def debtors(session: SessionDep) -> list[DebtorView]:
    """Customers who owe something, most first: the collecting list.

    Returns:
        The debtors.
    """
    return await _service.debtors(session)


@router.get("/customers/{customer_id}")
async def account(session: SessionDep, customer_id: EntityId) -> AccountView:
    """What a customer owes, and how much more they may buy on account.

    Returns:
        The account.
    """
    return await _service.account(session, customer_id)


@router.get("/customers/{customer_id}/statement")
async def statement(
    session: SessionDep,
    customer_id: EntityId,
    query: Annotated[StatementQuery, Query()],
) -> StatementView:
    """A customer's account over a period, with a running balance.

    Returns:
        The statement.
    """
    return await _service.statement(session, customer_id, query)


@router.put("/customers/{customer_id}/credit-limit")
async def set_credit_limit(
    session: SessionDep,
    _admin: identity.AdminActor,
    customer_id: EntityId,
    data: CreditLimitUpdate,
) -> AccountView:
    """Set (or with ``null``, remove) a customer's credit limit. Admins only.

    Returns:
        The account.
    """
    return await _service.set_limit(session, customer_id, data)


@router.post("/payments", status_code=HTTPStatus.CREATED)
async def record_payment(
    session: SessionDep, actor: identity.CurrentActor, data: PaymentCreate
) -> EntryView:
    """Record a customer paying off debt, at the shop or at the door.

    Returns:
        The ledger line; it records who took the money.
    """
    return await _service.record_payment(session, data, actor.id)


@router.post("/adjustments", status_code=HTTPStatus.CREATED)
async def adjust(
    session: SessionDep, actor: identity.AdminActor, data: AdjustmentCreate
) -> EntryView:
    """Correct a balance, e.g. an old debt from before h2open. Admins only.

    Returns:
        The ledger line.
    """
    return await _service.adjust(session, data, actor.id)


@router.post("/entries/{entry_id}/void")
async def void(
    session: SessionDep, actor: identity.AdminActor, entry_id: EntityId, data: Void
) -> EntryView:
    """Void a payment or adjustment entered by mistake. Admins only.

    Returns:
        The voided line.
    """
    return await _service.void(session, entry_id, data, actor.id)
