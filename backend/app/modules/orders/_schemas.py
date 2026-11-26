# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the order endpoints. Private to this module."""

from typing import Annotated, Self

from pydantic import BaseModel, Field, PositiveInt, StringConstraints, model_validator

from app.core.ids import EntityId
from app.modules.containers.api import ContainerCount
from app.modules.orders._views import Channel, Fulfilment, OrderStatus, PaymentMethod

type Notes = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
type Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class LineIn(BaseModel):
    """A quantity of one product."""

    product_id: EntityId
    quantity: PositiveInt


def _unique_products(lines: list[LineIn]) -> None:
    products = [line.product_id for line in lines]
    if len(set(products)) != len(products):
        msg = "list each product once"
        raise ValueError(msg)


def _unique_types(counts: list[ContainerCount]) -> None:
    types = [count.container_type_id for count in counts]
    if len(set(types)) != len(types):
        msg = "list each container type once"
        raise ValueError(msg)


class OrderCreate(BaseModel):
    """A new order.

    ``expected_returns`` defaults to "an empty back for every returnable
    container delivered" (a plain swap). Give it to say otherwise, e.g.
    a new customer returns nothing.
    """

    customer_id: EntityId | None = None
    """Leave out for a walk-in sale (pickup only, if walk-ins are enabled)."""
    channel: Channel
    fulfilment: Fulfilment
    address_id: EntityId | None = None
    """One of the customer's addresses; required for delivery."""
    lines: list[LineIn] = []
    expected_returns: list[ContainerCount] | None = None
    payment_method: PaymentMethod
    notes: Notes | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _unique_products(self.lines)
        _unique_types(self.expected_returns or [])
        if not self.lines and not self.expected_returns:
            msg = "an order needs products or containers to return"
            raise ValueError(msg)
        if self.fulfilment is Fulfilment.DELIVERY and self.address_id is None:
            msg = "a delivery needs a customer and one of their addresses"
            raise ValueError(msg)
        if self.address_id is not None and self.customer_id is None:
            msg = "an address needs a customer"
            raise ValueError(msg)
        return self


class OrderUpdate(BaseModel):
    """Changes to an open order; omitted fields stay as they are.

    Changing ``lines`` without ``expected_returns`` resets the expected
    returns to a plain swap of the new lines.
    """

    lines: list[LineIn] | None = None
    expected_returns: list[ContainerCount] | None = None
    payment_method: PaymentMethod | None = None
    address_id: EntityId | None = None
    notes: Notes | None = None
    """Send ``null`` to clear the notes."""

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _unique_products(self.lines or [])
        _unique_types(self.expected_returns or [])
        return self


class OrderCompletion(BaseModel):
    """What actually happened when the order was handed over.

    Omit ``lines`` if everything was delivered as ordered, and ``returned``
    if the expected empties came back. Otherwise list what really happened:
    products left out of ``lines`` count as not delivered, and new products
    are added at today's price.
    """

    lines: list[LineIn] | None = None
    returned: list[ContainerCount] | None = None
    payment_method: PaymentMethod | None = None
    override_reason: Reason | None = None
    """Needed if empties of another brand were accepted."""

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _unique_products(self.lines or [])
        _unique_types(self.returned or [])
        return self


class OrderCancel(BaseModel):
    """Why an open order is cancelled."""

    reason: Reason


class Release(BaseModel):
    """A driver putting a delivery back in the pool."""

    reason: Reason | None = None


class TakeBack(BaseModel):
    """Staff taking a delivery away from a driver."""

    reason: Reason


class OrderSearch(BaseModel):
    """Query parameters for listing orders."""

    status: OrderStatus | None = None
    fulfilment: Fulfilment | None = None
    customer_id: EntityId | None = None
    claimed_by: EntityId | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
