# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the containers module. Other modules get them via ``api``."""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, PositiveInt

from app.core.ids import EntityId
from app.core.money import Money


class MovementKind(StrEnum):
    """Why a customer's container balance changed."""

    ISSUE = "issue"
    """Customer got containers and paid a deposit for each."""
    RETURN = "return"
    """Customer gave containers back for good; deposit refunded per policy."""
    TRANSFER_OUT = "transfer_out"
    """Staff override: an empty of another type was accepted instead..."""
    TRANSFER_IN = "transfer_in"
    """...and its deposit moved to the container type the customer received."""


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class ContainerCount(_View):
    """A number of containers of one type."""

    container_type_id: EntityId
    quantity: PositiveInt


class MovementView(_View):
    """One line of a customer's container ledger."""

    id: EntityId
    exchange_id: EntityId
    """Movements recorded together share this ID."""
    customer_id: EntityId
    container_type_id: EntityId
    kind: MovementKind
    quantity: PositiveInt
    balance_change: int
    """How many containers the customer holds more (or fewer) afterwards."""
    unit_deposit: Money
    """Deposit per container: charged, refunded or moved."""
    occurred_at: datetime
    override_reason: str | None
    note: str | None


class BalanceView(_View):
    """Containers of one type a customer holds, and the deposit behind them."""

    container_type_id: EntityId
    quantity: int
    deposit_held: Money
    """Total deposit the customer paid for these containers."""


class ExchangeResult(_View):
    """What happened in one exchange, and the money to collect or pay out."""

    exchange_id: EntityId
    swapped: list[ContainerCount]
    """Full for empty of the same type: no balance or money change."""
    movements: list[MovementView]
    deposit_charged: Money | None
    """Deposit the customer owes for new containers."""
    deposit_refunded: Money | None
    """Deposit to pay back for containers returned for good."""
