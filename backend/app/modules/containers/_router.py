# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the containers module. Private to this module."""

from http import HTTPStatus

from fastapi import APIRouter, Depends

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.containers import _service
from app.modules.containers._schemas import ExchangeCreate
from app.modules.containers._views import BalanceView, ExchangeResult, MovementView
from app.modules.identity import api as identity

router = APIRouter(
    prefix="/containers",
    tags=["containers"],
    dependencies=[Depends(identity.current_actor)],
)


@router.post("/exchanges", status_code=HTTPStatus.CREATED)
async def exchange(
    session: SessionDep, actor: identity.CurrentActor, data: ExchangeCreate
) -> ExchangeResult:
    """Record full containers delivered and empties returned in one visit.

    Returns:
        The ledger movements and the deposit to charge or refund. A 409 with
        code ``override_required`` means the empties are a different type
        than the fulls; repeat with ``override_reason`` to accept them.
    """
    return await _service.exchange(session, data, actor.id)


@router.get("/customers/{customer_id}/balances")
async def balances(session: SessionDep, customer_id: EntityId) -> list[BalanceView]:
    """Containers a customer holds now, and the deposit behind them.

    Returns:
        One entry per container type held.
    """
    return await _service.balances(session, customer_id)


@router.get("/customers/{customer_id}/movements")
async def movements(session: SessionDep, customer_id: EntityId) -> list[MovementView]:
    """A customer's container ledger, newest first.

    Returns:
        Every movement.
    """
    return await _service.movements(session, customer_id)
