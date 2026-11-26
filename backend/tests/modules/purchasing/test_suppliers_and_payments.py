# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for suppliers, paying them, and what we owe."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from app.core.ids import new_id
from app.modules.identity.api import Role
from app.modules.purchasing.api import (
    PaymentStatus,
    SupplierBalanceView,
    SupplierPaymentMethod,
    SupplierPaymentView,
    SupplierView,
)
from tests.modules.auth import bearer, login, make_user
from tests.modules.purchasing.helpers import Purchasing, create_supplier, tl

if TYPE_CHECKING:
    from app.core.db import Database
    from app.core.ids import EntityId

SUPPLIERS = TypeAdapter(list[SupplierView])
PAYMENTS = TypeAdapter(list[SupplierPaymentView])


def balance(buy: Purchasing, supplier_id: EntityId) -> SupplierBalanceView:
    """A supplier's balance.

    Returns:
        The balance.
    """
    response = buy.goods.client.get(f"/purchasing/suppliers/{supplier_id}/balance")
    assert response.status_code == HTTPStatus.OK, response.text
    return SupplierBalanceView.model_validate_json(response.content)


def paid(buy: Purchasing, amount: str, **body: object) -> SupplierPaymentView:
    """Make a payment that must be accepted.

    Returns:
        The payment.
    """
    response = buy.pay(amount, **body)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return SupplierPaymentView.model_validate_json(response.content)


def test_manage_suppliers(buy: Purchasing) -> None:
    """Admins add, rename, edit and deactivate suppliers."""
    client = buy.goods.client
    assert buy.supplier.tax_number == "1234567890"
    taken = client.post("/purchasing/suppliers", json={"name": "brand a dolum"})
    assert taken.status_code == HTTPStatus.CONFLICT
    bad = client.post("/purchasing/suppliers", json={"name": "X", "tax_number": "12"})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_CONTENT

    other = create_supplier(buy.goods, "Akdeniz Su")
    names = [
        s.name
        for s in SUPPLIERS.validate_json(client.get("/purchasing/suppliers").content)
    ]
    assert names == ["Akdeniz Su", "Brand A Dolum"]

    url = f"/purchasing/suppliers/{other.id}"
    response = client.patch(
        url,
        json={"name": "Akdeniz Su A.Ş.", "phone": "0242 000 00 00", "notes": "Fridays"},
    )
    changed = SupplierView.model_validate_json(response.content)
    assert (changed.name, changed.phone, changed.notes) == (
        "Akdeniz Su A.Ş.",
        "0242 000 00 00",
        "Fridays",
    )
    response = client.patch(
        url, json={"phone": None, "tax_number": None, "active": False}
    )
    cleared = SupplierView.model_validate_json(response.content)
    assert (cleared.phone, cleared.tax_number, cleared.notes, cleared.active) == (
        None,
        None,
        "Fridays",
        False,
    )
    assert SupplierView.model_validate_json(client.get(url).content) == cleared
    assert client.patch(url, json={"name": "Brand A Dolum"}).status_code == (
        HTTPStatus.CONFLICT
    )
    assert client.patch(url, json={"name": "Akdeniz Su A.Ş."}).status_code == (
        HTTPStatus.OK
    )


def test_unknown_suppliers(buy: Purchasing) -> None:
    """Unknown suppliers are 404s everywhere."""
    client, missing = buy.goods.client, new_id()
    assert client.get(f"/purchasing/suppliers/{missing}").status_code == (
        HTTPStatus.NOT_FOUND
    )
    assert client.patch(f"/purchasing/suppliers/{missing}", json={}).status_code == (
        HTTPStatus.NOT_FOUND
    )
    assert client.get(f"/purchasing/suppliers/{missing}/balance").status_code == (
        HTTPStatus.NOT_FOUND
    )
    assert buy.pay("1", supplier_id=str(missing)).status_code == HTTPStatus.NOT_FOUND


def test_staff_enter_but_do_not_administer(buy: Purchasing, database: Database) -> None:
    """Staff enter receipts and payments; suppliers and voids are for admins."""
    _ = make_user(database, "ayse", {Role.STAFF})
    client = buy.goods.client
    client.headers.update(bearer(login(client, "ayse")))
    assert client.get("/purchasing/suppliers").status_code == HTTPStatus.OK
    assert client.post("/purchasing/suppliers", json={"name": "X"}).status_code == (
        HTTPStatus.FORBIDDEN
    )
    receipt = buy.entered()
    assert receipt.recorded_by != buy.supplier.id
    payment = paid(buy, "5.00")
    response = client.post(
        f"/purchasing/payments/{payment.id}/void", json={"reason": "x"}
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_paying_a_receipt(buy: Purchasing) -> None:
    """Payments against a receipt move it from unpaid to partial to paid."""
    receipt = buy.entered()
    first = paid(
        buy,
        "300.00",
        receipt_id=str(receipt.id),
        method="bank_transfer",
        reference="EFT 123",
    )
    assert (first.amount, first.method, first.reference) == (
        tl("300.00"),
        SupplierPaymentMethod.BANK_TRANSFER,
        "EFT 123",
    )
    partial = buy.receipt(receipt.id)
    assert (partial.paid, partial.outstanding, partial.payment_status) == (
        tl("300.00"),
        tl("205.00"),
        PaymentStatus.PARTIAL,
    )

    too_much = buy.pay("205.01", receipt_id=str(receipt.id))
    assert too_much.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert too_much.json()["detail"] == (
        "only 205.00 TRY is outstanding on receipt 'GIB2026000000001'"
    )
    _ = paid(buy, "205.00", receipt_id=str(receipt.id))
    done = buy.receipt(receipt.id)
    assert (done.outstanding, done.payment_status) == (tl("0"), PaymentStatus.PAID)
    assert balance(buy, buy.supplier.id).payable == [tl("0.00")]


def test_payments_must_fit_the_receipt(buy: Purchasing) -> None:
    """Wrong supplier, wrong currency, voided or unknown receipts are refused."""
    receipt = buy.entered()
    other = create_supplier(buy.goods, "Akdeniz Su")
    cases: list[tuple[dict[str, object], HTTPStatus, str]] = [
        (
            {"supplier_id": str(other.id)},
            HTTPStatus.UNPROCESSABLE_CONTENT,
            "different supplier",
        ),
        ({"currency": "EUR"}, HTTPStatus.UNPROCESSABLE_CONTENT, "is in TRY, not EUR"),
        ({"receipt_id": str(new_id())}, HTTPStatus.NOT_FOUND, "not found"),
    ]
    for body, status, message in cases:
        response = buy.pay("1.00", **{"receipt_id": str(receipt.id), **body})
        assert response.status_code == status, body
        assert message in response.json()["detail"]
    assert buy.pay("0").status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert buy.pay("1.001").status_code == HTTPStatus.UNPROCESSABLE_CONTENT

    _ = buy.post(f"/purchasing/receipts/{receipt.id}/void", {"reason": "dup"})
    voided = buy.pay("1.00", receipt_id=str(receipt.id))
    assert voided.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "is voided" in voided.json()["detail"]


def test_voiding_payments(buy: Purchasing) -> None:
    """A paid receipt can only be voided after its payments are."""
    receipt = buy.entered()
    payment = paid(buy, "100.00", receipt_id=str(receipt.id))
    void_receipt = f"/purchasing/receipts/{receipt.id}/void"
    blocked = buy.post(void_receipt, {"reason": "wrong supplier"})
    assert blocked.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "void them first" in blocked.json()["detail"]

    url = f"/purchasing/payments/{payment.id}/void"
    response = buy.post(url, {"reason": "bounced"})
    voided = SupplierPaymentView.model_validate_json(response.content)
    assert (voided.void_reason, voided.voided_by is not None) == ("bounced", True)
    assert buy.post(url, {"reason": "again"}).status_code == HTTPStatus.CONFLICT
    assert buy.receipt(receipt.id).payment_status is PaymentStatus.UNPAID
    assert buy.post(void_receipt, {"reason": "wrong supplier"}).status_code == (
        HTTPStatus.OK
    )
    missing = f"/purchasing/payments/{new_id()}/void"
    assert buy.post(missing, {"reason": "x"}).status_code == HTTPStatus.NOT_FOUND


def test_listing_payments_and_balance(buy: Purchasing) -> None:
    """Payments without a receipt count towards the supplier's balance."""
    receipt = buy.entered()
    against = paid(buy, "5.00", receipt_id=str(receipt.id))
    advance = paid(buy, "1000.00", method="card")
    euros = paid(buy, "10.00", currency="EUR")
    _ = buy.post(f"/purchasing/payments/{euros.id}/void", {"reason": "test"})

    client = buy.goods.client

    def listed(**params: str) -> list[EntityId]:
        response = client.get("/purchasing/payments", params=params)
        return [p.id for p in PAYMENTS.validate_json(response.content)]

    assert set(listed()) == {against.id, advance.id}
    assert listed(receipt_id=str(receipt.id)) == [against.id]
    assert set(listed(include_voided="true", supplier_id=str(buy.supplier.id))) == {
        against.id,
        advance.id,
        euros.id,
    }
    assert balance(buy, buy.supplier.id).payable == [tl("-500.00")]
