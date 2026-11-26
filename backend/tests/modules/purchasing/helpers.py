# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers for the purchasing tests."""

from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING

from app.core.money import Money
from app.modules.purchasing.api import ReceiptView, SupplierView

if TYPE_CHECKING:
    from httpx2 import Response

    from app.core.ids import EntityId
    from tests.modules.inventory.helpers import Goods


def tl(amount: str) -> Money:
    """An amount in TRY.

    Returns:
        The money.
    """
    return Money(amount=Decimal(amount), currency="TRY")


def goods_line(
    product: EntityId, quantity: int, net: str, vat: str = "1"
) -> dict[str, object]:
    """A goods line as JSON.

    Returns:
        The line.
    """
    return {
        "kind": "goods",
        "product_id": str(product),
        "quantity": quantity,
        "net_amount": net,
        "vat_rate": vat,
    }


def container_line(
    kind: str, carboy: EntityId, quantity: int, net: str
) -> dict[str, object]:
    """A container purchase or renewal line at 20 % VAT, as JSON.

    Returns:
        The line.
    """
    return {
        "kind": kind,
        "container_type_id": str(carboy),
        "quantity": quantity,
        "net_amount": net,
        "vat_rate": "20",
    }


def empties(carboy: EntityId, quantity: int) -> list[dict[str, object]]:
    """Empties handed over, as JSON.

    Returns:
        The counts.
    """
    return [{"container_type_id": str(carboy), "quantity": quantity}]


@dataclass(frozen=True)
class Purchasing:
    """The test products and one supplier."""

    goods: Goods
    supplier: SupplierView

    def post(self, url: str, body: dict[str, object]) -> Response:
        """Send a POST request as the admin.

        Returns:
            The raw response.
        """
        return self.goods.client.post(url, json=body)

    def enter(self, **body: object) -> Response:
        """Enter a receipt from the supplier; defaults to 10 waters, swapped.

        Returns:
            The raw response.
        """
        defaults: dict[str, object] = {
            "supplier_id": str(self.supplier.id),
            "document_number": "GIB2026000000001",
            "issued_on": "2026-11-25",
            "lines": [goods_line(self.goods.water, 10, "500.00")],
            "empties_returned": empties(self.goods.carboy, 10),
            "total": "505.00",
        }
        return self.post("/purchasing/receipts", {**defaults, **body})

    def entered(self, **body: object) -> ReceiptView:
        """Enter a receipt that must be accepted.

        Returns:
            The receipt.
        """
        response = self.enter(**body)
        assert response.status_code == HTTPStatus.CREATED, response.text
        return ReceiptView.model_validate_json(response.content)

    def pay(self, amount: str, **body: object) -> Response:
        """Pay the supplier in cash.

        Returns:
            The raw response.
        """
        defaults: dict[str, object] = {
            "supplier_id": str(self.supplier.id),
            "amount": amount,
            "method": "cash",
            "paid_on": "2026-11-26",
        }
        return self.post("/purchasing/payments", {**defaults, **body})

    def receipt(self, receipt_id: EntityId) -> ReceiptView:
        """Read a receipt back.

        Returns:
            The receipt.
        """
        response = self.goods.client.get(f"/purchasing/receipts/{receipt_id}")
        assert response.status_code == HTTPStatus.OK, response.text
        return ReceiptView.model_validate_json(response.content)


def create_supplier(goods: Goods, name: str = "Brand A Dolum") -> SupplierView:
    """Add a supplier through the API.

    Returns:
        The supplier.
    """
    response = goods.client.post(
        "/purchasing/suppliers", json={"name": name, "tax_number": "1234567890"}
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    return SupplierView.model_validate_json(response.content)
