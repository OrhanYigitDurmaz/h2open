# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers shared by the order tests."""

from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.core.money import Money
from app.modules.orders.api import OrderView
from tests.modules.catalog.helpers import create_product, try_

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response

    from app.core.ids import EntityId
    from app.modules.customers.api import CustomerView


def tl(amount: str) -> Money:
    """An amount in TRY.

    Returns:
        The money.
    """
    return Money(amount=Decimal(amount), currency="TRY")


def ok(response: Response) -> OrderView:
    """Parse an order from a successful response.

    Returns:
        The order.
    """
    assert response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}, response.text
    return OrderView.model_validate_json(response.content)


class ErrorBody(BaseModel):
    """The body of a domain error response."""

    code: str = "validation"
    """Missing for request validation errors."""
    detail: object


def error(response: Response, status: HTTPStatus) -> str:
    """Check an error response.

    Returns:
        The error code, or ``"validation"`` for a rejected request body.
    """
    assert response.status_code == status, response.text
    return ErrorBody.model_validate_json(response.content).code


@dataclass(frozen=True)
class Shop:
    """A Brand A carboy (deposit 200), three products and one customer."""

    client: TestClient
    carboy: EntityId
    water: EntityId
    """Brand A 19 L in a returnable carboy, 100 TRY, 1 % VAT."""
    pack: EntityId
    """12 x 500 ml, 60 TRY, 10 % VAT."""
    cups: EntityId
    """Paper cups, 20 TRY, 20 % VAT."""
    customer: CustomerView

    def order(self, **body: object) -> Response:
        """Send a new order.

        Returns:
            The raw response.
        """
        return self.client.post("/orders", json=body)

    def delivery(self, lines: dict[EntityId, int], **extra: object) -> OrderView:
        """Take a phone order for delivery to the customer's home.

        Returns:
            The open order.
        """
        return ok(
            self.order(
                customer_id=str(self.customer.id),
                channel="phone",
                fulfilment="delivery",
                address_id=str(self.customer.addresses[0].id),
                lines=lines_json(lines),
                payment_method="cash",
                **extra,
            )
        )

    def walk_in(self, lines: dict[EntityId, int], **extra: object) -> Response:
        """Ring up a counter sale without a customer.

        Returns:
            The raw response.
        """
        body: dict[str, object] = {
            "channel": "counter",
            "fulfilment": "pickup",
            "lines": lines_json(lines),
            "payment_method": "cash",
        }
        return self.order(**{**body, **extra})

    def complete(self, order: OrderView, **body: object) -> Response:
        """Complete an order.

        Returns:
            The raw response.
        """
        return self.client.post(f"/orders/{order.id}/complete", json=body)

    def give_carboys(self, quantity: int) -> None:
        """Let the customer hold some Brand A carboys already."""
        order = self.delivery({self.water: quantity}, expected_returns=[])
        _ = ok(self.complete(order))

    def settings(self, **changes: object) -> None:
        """Change company settings."""
        response = self.client.patch("/company/settings", json=changes)
        assert response.status_code == HTTPStatus.OK


def lines_json(lines: dict[EntityId, int]) -> list[dict[str, object]]:
    """Order lines as JSON.

    Returns:
        The lines.
    """
    return [{"product_id": str(p), "quantity": q} for p, q in lines.items()]


def returns_json(counts: dict[EntityId, int]) -> list[dict[str, object]]:
    """Container counts as JSON.

    Returns:
        The counts.
    """
    return [{"container_type_id": str(t), "quantity": q} for t, q in counts.items()]


def priced(client: TestClient, body: dict[str, object], price: str) -> EntityId:
    """Create a product and give it a price.

    Returns:
        The product's ID.
    """
    product = create_product(client, body)
    response = client.post(
        f"/catalog/products/{product.id}/prices", json={"price": try_(price)}
    )
    assert response.status_code == HTTPStatus.CREATED
    return product.id
