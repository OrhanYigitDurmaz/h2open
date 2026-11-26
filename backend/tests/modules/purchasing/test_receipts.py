# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for entering and voiding supplier receipts."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from app.core.ids import new_id
from app.modules.identity.api import Role
from app.modules.inventory.api import ItemKind, MovementReason
from app.modules.purchasing.api import (
    ContainerFlowView,
    LineKind,
    PaymentStatus,
    ReceiptView,
    SupplierBalanceView,
)
from tests.modules.auth import bearer, login, make_user
from tests.modules.purchasing.helpers import (
    Purchasing,
    container_line,
    create_supplier,
    empties,
    goods_line,
    tl,
)

if TYPE_CHECKING:
    from app.core.db import Database

RECEIPTS = TypeAdapter(list[ReceiptView])
FULL, SWAPPED, BOUGHT, RENEWED = 50, 47, 3, 2
NINE, TEN = 9, 10


def full_receipt(buy: Purchasing) -> dict[str, object]:
    """50 waters: 47 swapped (2 of them renewed), 3 carboys bought, transport.

    Returns:
        The receipt body.
    """
    carboy = buy.goods.carboy
    return {
        "document_number": "ABC2026000000042",
        "lines": [
            goods_line(buy.goods.water, FULL, "2000.00"),
            container_line("container_renewal", carboy, RENEWED, "100.00"),
            container_line("container_purchase", carboy, BOUGHT, "450.00"),
            {
                "kind": "other",
                "description": "Nakliye",
                "net_amount": "50.00",
                "vat_rate": "20",
            },
        ],
        "empties_returned": empties(carboy, SWAPPED),
        "total": "2740.00",
        "notes": "Morning truck",
    }


def test_receipt_puts_goods_in_stock(buy: Purchasing) -> None:
    """Goods come in, empties go out, and every line is costed."""
    receipt = buy.entered(**full_receipt(buy))
    assert [line.kind for line in receipt.lines] == [
        LineKind.GOODS,
        LineKind.CONTAINER_RENEWAL,
        LineKind.CONTAINER_PURCHASE,
        LineKind.OTHER,
    ]
    water, renewal, _, transport = receipt.lines
    assert (water.description, water.vat_amount, water.total) == (
        "Brand A 19 L",
        tl("20.00"),
        tl("2020.00"),
    )
    assert water.unit_cost == tl("40.4000")
    assert (renewal.description, renewal.unit_cost) == ("19 L carboy", tl("60.0000"))
    assert (transport.description, transport.quantity) == ("Nakliye", 1)
    assert (receipt.net_total, receipt.vat_total, receipt.total) == (
        tl("2600.00"),
        tl("140.00"),
        tl("2740.00"),
    )
    assert (receipt.paid, receipt.outstanding, receipt.payment_status) == (
        tl("0"),
        tl("2740.00"),
        PaymentStatus.UNPAID,
    )
    assert receipt.containers == [
        ContainerFlowView(
            container_type_id=buy.goods.carboy,
            full_in=FULL,
            empties_out=SWAPPED,
            purchased=BOUGHT,
            renewed=RENEWED,
            balance_change=0,
        )
    ]
    assert (buy.goods.water_level(), buy.goods.empties_level()) == (FULL, -SWAPPED)
    moves = buy.goods.movements(source_id=str(receipt.id))
    assert {m.reason for m in moves} == {MovementReason.PURCHASE}
    assert moves[0].note == "Receipt ABC2026000000042 from Brand A Dolum"
    assert buy.receipt(receipt.id) == receipt


def test_lines_must_add_up_to_the_total(buy: Purchasing) -> None:
    """A typo is caught; VAT rounding of a kuruş per line is tolerated."""
    body = full_receipt(buy)
    wrong = buy.enter(**{**body, "total": "2741.00"})
    assert wrong.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert wrong.json()["detail"] == (
        "the lines add up to 2740.00 TRY but the receipt total is 2741.00;"
        " check the amounts and VAT rates"
    )
    rounded = buy.entered(**{**body, "total": "2740.04"})
    assert rounded.total == tl("2740.04")


def test_container_counts_must_fit(buy: Purchasing) -> None:
    """Containers bought or renewed arrive full; renewals need an old empty."""
    carboy, water = buy.goods.carboy, buy.goods.water
    bought = buy.enter(
        lines=[
            goods_line(water, 2, "80.00"),
            container_line("container_purchase", carboy, 3, "0"),
        ],
        total="80.80",
    )
    assert bought.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert (
        "3 x '19 L carboy' bought or renewed, but only 2 arrived full"
        in (bought.json()["detail"])
    )
    renewed = buy.enter(
        lines=[
            goods_line(water, 2, "80.00"),
            container_line("container_renewal", carboy, 2, "0"),
        ],
        empties_returned=empties(carboy, 1),
        total="80.80",
    )
    assert renewed.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "only 1 empties were handed over" in renewed.json()["detail"]


def test_supplier_container_balance(buy: Purchasing) -> None:
    """Short swaps leave us holding the supplier's carboys, and vice versa."""
    _ = buy.entered(empties_returned=empties(buy.goods.carboy, 8))
    url = f"/purchasing/suppliers/{buy.supplier.id}/balance"
    balance = SupplierBalanceView.model_validate_json(buy.goods.client.get(url).content)
    assert [(c.container_type_id, c.quantity) for c in balance.containers] == [
        (buy.goods.carboy, 2)
    ]
    _ = buy.entered(
        document_number="2",
        lines=[goods_line(buy.goods.water, 1, "50.00")],
        empties_returned=empties(buy.goods.carboy, 5),
        total="50.50",
    )
    balance = SupplierBalanceView.model_validate_json(buy.goods.client.get(url).content)
    assert [c.quantity for c in balance.containers] == [-2]
    assert balance.payable == [tl("555.50")]

    _ = buy.entered(
        document_number="3",
        lines=[goods_line(buy.goods.water, 2, "100.00")],
        empties_returned=[],
        total="101.00",
    )
    balance = SupplierBalanceView.model_validate_json(buy.goods.client.get(url).content)
    assert balance.containers == []


def test_bad_receipts(buy: Purchasing) -> None:
    """Malformed lines are rejected before anything is looked up."""
    water, carboy = str(buy.goods.water), str(buy.goods.carboy)
    bad_lines: list[dict[str, object]] = [
        {"kind": "goods", "net_amount": "1", "vat_rate": "1"},
        {
            "kind": "goods",
            "product_id": water,
            "container_type_id": carboy,
            "net_amount": "1",
            "vat_rate": "1",
        },
        {"kind": "container_purchase", "net_amount": "1", "vat_rate": "1"},
        {"kind": "other", "net_amount": "1", "vat_rate": "1"},
        {"kind": "other", "description": "x", "net_amount": "-1", "vat_rate": "1"},
        {"kind": "other", "description": "x", "net_amount": "1.001", "vat_rate": "1"},
    ]
    for line in bad_lines:
        response = buy.enter(lines=[line])
        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT, line
    assert buy.enter(lines=[]).status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    twice = [*empties(buy.goods.carboy, 1), *empties(buy.goods.carboy, 1)]
    assert buy.enter(empties_returned=twice).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )


def test_unknown_or_inactive_references(buy: Purchasing) -> None:
    """Unknown products, container types and suppliers are 404s."""
    missing = new_id()
    assert buy.enter(lines=[goods_line(missing, 1, "1")]).status_code == (
        HTTPStatus.NOT_FOUND
    )
    assert buy.enter(empties_returned=empties(missing, 1)).status_code == (
        HTTPStatus.NOT_FOUND
    )
    assert buy.enter(supplier_id=str(missing)).status_code == HTTPStatus.NOT_FOUND
    assert buy.goods.client.get(f"/purchasing/receipts/{missing}").status_code == (
        HTTPStatus.NOT_FOUND
    )
    _ = buy.goods.client.patch(
        f"/purchasing/suppliers/{buy.supplier.id}", json={"active": False}
    )
    inactive = buy.enter()
    assert inactive.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "inactive" in inactive.json()["detail"]


def test_void_and_reenter(buy: Purchasing, database: Database) -> None:
    """A receipt is entered once; voiding reverses its stock and frees it."""
    receipt = buy.entered()
    assert buy.enter().status_code == HTTPStatus.CONFLICT
    url = f"/purchasing/receipts/{receipt.id}/void"

    _ = make_user(database, "ayse", {Role.STAFF})
    staff = bearer(login(buy.goods.client, "ayse"))
    assert buy.goods.client.post(
        url, json={"reason": "x"}, headers=staff
    ).status_code == (HTTPStatus.FORBIDDEN)
    assert buy.post(url, {"reason": " "}).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )

    response = buy.post(url, {"reason": "typed the wrong quantity"})
    assert response.status_code == HTTPStatus.OK
    voided = ReceiptView.model_validate_json(response.content)
    assert (voided.void_reason, voided.voided_at is not None) == (
        "typed the wrong quantity",
        True,
    )
    assert (buy.goods.water_level(), buy.goods.empties_level()) == (0, 0)
    reversal = buy.goods.movements(reason="purchase_void")
    assert {(m.kind, m.change) for m in reversal} == {
        (ItemKind.PRODUCT, -10),
        (ItemKind.EMPTY, 10),
    }
    assert buy.post(url, {"reason": "again"}).status_code == HTTPStatus.CONFLICT

    again = buy.entered(
        lines=[
            goods_line(buy.goods.water, NINE, "450.00"),
            goods_line(buy.goods.cups, TEN, "100.00", vat="20"),
        ],
        total="574.50",
    )
    assert buy.goods.water_level() == NINE
    assert buy.goods.level(ItemKind.PRODUCT, buy.goods.cups) == TEN
    assert [c.full_in for c in again.containers] == [NINE]
    client = buy.goods.client
    live = RECEIPTS.validate_json(client.get("/purchasing/receipts").content)
    assert [r.id for r in live] == [again.id]
    every = RECEIPTS.validate_json(
        client.get(
            "/purchasing/receipts",
            params={"include_voided": "true", "supplier_id": str(buy.supplier.id)},
        ).content
    )
    assert {r.id for r in every} == {receipt.id, again.id}
    other = create_supplier(buy.goods, "Brand B Dolum")
    assert (
        client.get("/purchasing/receipts", params={"supplier_id": str(other.id)}).json()
        == []
    )


def test_void_respects_negative_stock(buy: Purchasing) -> None:
    """Goods already sold cannot be voided away while negative stock is off."""
    buy.goods.settings(negative_stock_allowed=False)
    refused = buy.enter()
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "'empty 19 L carboy': 0 on hand, 10 needed" in refused.json()["detail"]

    receipt = buy.entered(empties_returned=[])
    adjusted = buy.post(
        "/inventory/adjustments",
        {
            "kind": "product",
            "item_id": str(buy.goods.water),
            "change": -4,
            "reason": "sold off the books",
        },
    )
    assert adjusted.status_code == HTTPStatus.CREATED
    response = buy.post(f"/purchasing/receipts/{receipt.id}/void", {"reason": "x"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert buy.receipt(receipt.id).voided_at is None
