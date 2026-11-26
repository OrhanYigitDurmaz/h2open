# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the accounts endpoints. Private to this module."""

from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.ids import EntityId
from app.core.money import Money
from app.modules.accounts._views import AccountPaymentMethod

type Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
type Reference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
type Positive = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class OrderCharge(BaseModel):
    """An on-account order to put on a customer's account."""

    customer_id: EntityId
    order_id: EntityId
    """Each order is charged once."""
    total: Money | None
    """The order's total; negative if the customer got money back, and
    ``None`` if nothing on it has a price."""
    override_reason: Text | None = None
    """Why going over the credit limit is fine, if it is."""


class PaymentCreate(BaseModel):
    """A customer paying towards what they owe."""

    customer_id: EntityId
    amount: Positive
    method: AccountPaymentMethod
    reference: Reference | None = None
    """Bank transfer reference, card slip number and the like."""
    note: Text | None = None


class AdjustmentCreate(BaseModel):
    """A correction: positive adds to what the customer owes."""

    customer_id: EntityId
    amount: Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
    reason: Text

    @field_validator("amount")
    @classmethod
    def _not_zero(cls, amount: Decimal) -> Decimal:
        if amount == 0:
            msg = "the amount cannot be zero"
            raise ValueError(msg)
        return amount


class Void(BaseModel):
    """Why a payment or adjustment is voided."""

    reason: Text


class CreditLimitUpdate(BaseModel):
    """A customer's new credit limit; ``null`` removes it."""

    amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)] | None


class StatementQuery(BaseModel):
    """The period of a statement; open-ended by default."""

    since: AwareDatetime | None = None
    until: AwareDatetime | None = None

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if (
            self.since is not None
            and self.until is not None
            and self.until < self.since
        ):
            msg = "until must not be before since"
            raise ValueError(msg)
        return self
