# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for customer accounts: charges, payments, limits and statements."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from app.core.ids import new_id
from app.modules.accounts.api import (
    AccountPaymentMethod,
    AccountView,
    DebtorView,
    EntryKind,
    EntryView,
    StatementView,
)
from app.modules.customers.api import CustomerView
from app.modules.identity.api import Role
from tests.modules.auth import bearer, login, make_user
from tests.modules.orders.helpers import Shop, make_shop, ok, tl

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response

    from app.core.db import Database
    from app.core.ids import EntityId

DEBTORS = TypeAdapter(list[DebtorView])


@dataclass(frozen=True)
class Books:
    """The test shop, with helpers for its customer's account."""

    shop: Shop

    @property
    def client(self) -> TestClient:
        """The admin's client.

        Returns:
            The client.
        """
        return self.shop.client

    @property
    def customer(self) -> EntityId:
        """The shop's customer.

        Returns:
            Their ID.
        """
        return self.shop.customer.id

    def sell_on_account(self, packs: int, **completion: object) -> Response:
        """Deliver packs of water (60 TRY each) on account.

        Returns:
            The completion response.
        """
        order = self.shop.delivery({self.shop.pack: packs})
        return self.shop.complete(order, payment_method="on_account", **completion)

    def account(self, customer: EntityId | None = None) -> AccountView:
        """A customer's account.

        Returns:
            The account.
        """
        url = f"/accounts/customers/{customer or self.customer}"
        return AccountView.model_validate_json(self.client.get(url).content)

    def pay(self, amount: str, **extra: object) -> Response:
        """Pay towards the customer's balance in cash.

        Returns:
            The raw response.
        """
        body = {"customer_id": str(self.customer), "amount": amount, "method": "cash"}
        return self.client.post("/accounts/payments", json={**body, **extra})

    def statement(self, **params: str) -> StatementView:
        """The customer's statement.

        Returns:
            The statement.
        """
        url = f"/accounts/customers/{self.customer}/statement"
        response = self.client.get(url, params=params)
        assert response.status_code == HTTPStatus.OK, response.text
        return StatementView.model_validate_json(response.content)


@pytest.fixture
def books(client: TestClient) -> Books:
    """The shop and its customer's (empty) account.

    Returns:
        The books.
    """
    return Books(make_shop(client))


def entry(response: Response) -> EntryView:
    """Parse a ledger line from a successful response.

    Returns:
        The line.
    """
    assert response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}, response.text
    return EntryView.model_validate_json(response.content)


def test_on_account_orders_are_charged(books: Books) -> None:
    """Completing an on-account order adds its total; cash orders don't."""
    assert books.account() == AccountView(
        customer_id=books.customer, balance=tl("0"), credit_limit=None, available=None
    )
    sold = ok(books.sell_on_account(2))
    _ = ok(books.shop.complete(books.shop.delivery({books.shop.cups: 1})))
    assert books.account().balance == tl("120")
    [charge] = books.statement().lines
    assert (charge.entry.kind, charge.entry.order_id, charge.entry.amount) == (
        EntryKind.CHARGE,
        sold.id,
        tl("120"),
    )


def test_payments_lower_the_balance(books: Books, database: Database) -> None:
    """Drivers take payments at the door; overpaying leaves a credit."""
    _ = ok(books.sell_on_account(2))
    driver = make_user(database, "ali", {Role.DRIVER})
    paid = entry(
        books.pay(
            "50",
            method="card",
            reference="slip 42",
            note="at the door",
        )
    )
    assert (paid.kind, paid.amount, paid.method) == (
        EntryKind.PAYMENT,
        tl("-50"),
        AccountPaymentMethod.CARD,
    )
    response = books.client.post(
        "/accounts/payments",
        json={"customer_id": str(books.customer), "amount": "100", "method": "cash"},
        headers=bearer(login(books.client, "ali")),
    )
    assert entry(response).recorded_by == driver.id
    assert books.account().balance == tl("-30")

    for bad in ("0", "-5", "1.001"):
        assert books.pay(bad).status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert books.pay("1", method="on_account").status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )


def test_credit_limit_needs_an_override(books: Books, database: Database) -> None:
    """Going over the limit asks for a reason; the reason is kept."""
    url = f"/accounts/customers/{books.customer}/credit-limit"
    limited = AccountView.model_validate_json(
        books.client.put(url, json={"amount": "100"}).content
    )
    assert (limited.credit_limit, limited.available) == (tl("100"), tl("100"))

    over = books.sell_on_account(2)
    assert over.status_code == HTTPStatus.CONFLICT
    assert over.json()["code"] == "override_required"
    assert "over the credit limit of 100" in over.json()["detail"]
    assert books.account().balance == tl("0")  # nothing was recorded

    order = books.shop.delivery({books.shop.pack: 2})
    done = books.shop.complete(
        order, payment_method="on_account", credit_override_reason="pays Friday"
    )
    assert done.status_code == HTTPStatus.OK
    [charge] = books.statement().lines
    assert charge.entry.override_reason == "pays Friday"
    assert books.account().available == tl("0")

    raised = books.client.put(url, json={"amount": "500"})
    assert AccountView.model_validate_json(raised.content).available == tl("380")
    _ = ok(books.sell_on_account(1, credit_override_reason="not needed"))
    assert books.statement().lines[-1].entry.override_reason is None

    removed = books.client.put(url, json={"amount": None})
    assert AccountView.model_validate_json(removed.content).credit_limit is None
    assert books.client.put(url, json={"amount": None}).status_code == HTTPStatus.OK
    assert books.client.put(url, json={"amount": "-1"}).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    _ = make_user(database, "ayse", {Role.STAFF})
    staff = bearer(login(books.client, "ayse"))
    response = books.client.put(url, json={"amount": "1"}, headers=staff)
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_orders_with_nothing_to_pay_add_nothing(books: Books) -> None:
    """Returning carboys for no refund, on account, leaves no line."""
    books.shop.give_carboys(1)
    books.shop.settings(deposit_refund_policy="none")
    order = ok(
        books.shop.order(
            customer_id=str(books.customer),
            channel="phone",
            fulfilment="pickup",
            expected_returns=[
                {"container_type_id": str(books.shop.carboy), "quantity": 1}
            ],
            payment_method="on_account",
        )
    )
    assert ok(books.shop.complete(order)).total == tl("0")
    assert books.statement().lines == []


def test_accounts_are_kept_in_lira(books: Books) -> None:
    """An on-account order in another currency is refused."""
    shop = books.shop
    response = shop.client.post(
        f"/catalog/products/{shop.cups}/prices",
        json={"price": {"amount": "5", "currency": "EUR"}},
    )
    assert response.status_code == HTTPStatus.CREATED
    order = shop.delivery({shop.cups: 1})
    refused = shop.complete(order, payment_method="on_account")
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert refused.json()["detail"] == "accounts are kept in TRY, not EUR"


def test_adjustments_and_voids(books: Books, database: Database) -> None:
    """Admins correct balances and void mistakes; order charges stay."""
    client = books.client
    opening = entry(
        client.post(
            "/accounts/adjustments",
            json={
                "customer_id": str(books.customer),
                "amount": "250",
                "reason": "debt from the old notebook",
            },
        )
    )
    assert (opening.kind, opening.note) == (
        EntryKind.ADJUSTMENT,
        "debt from the old notebook",
    )
    payment = entry(books.pay("50"))
    voided = entry(
        client.post(f"/accounts/entries/{payment.id}/void", json={"reason": "typo"})
    )
    assert (voided.void_reason, voided.voided_at is not None) == ("typo", True)
    assert books.account().balance == tl("250")
    again = client.post(f"/accounts/entries/{payment.id}/void", json={"reason": "x"})
    assert again.status_code == HTTPStatus.CONFLICT

    _ = ok(books.sell_on_account(1))
    charge = books.statement().lines[-1].entry
    refused = client.post(f"/accounts/entries/{charge.id}/void", json={"reason": "x"})
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    missing = client.post(f"/accounts/entries/{new_id()}/void", json={"reason": "x"})
    assert missing.status_code == HTTPStatus.NOT_FOUND

    zero = {"customer_id": str(books.customer), "amount": "0", "reason": "x"}
    assert client.post("/accounts/adjustments", json=zero).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )
    _ = make_user(database, "ali", {Role.DRIVER})
    driver = bearer(login(client, "ali"))
    for url in ("/accounts/adjustments", f"/accounts/entries/{charge.id}/void"):
        assert client.post(url, json={}, headers=driver).status_code == (
            HTTPStatus.FORBIDDEN
        )


def test_statement_over_a_period(books: Books) -> None:
    """Opening balance, running balance per line, voided lines not counted."""
    _ = ok(books.sell_on_account(2))  # 120
    mistake = entry(books.pay("1000"))
    _ = books.client.post(f"/accounts/entries/{mistake.id}/void", json={"reason": "x"})
    middle = datetime.now(UTC)
    _ = entry(books.pay("20"))
    _ = ok(books.sell_on_account(1))  # 60

    full = books.statement()
    assert [line.balance for line in full.lines] == [
        tl("120"),
        tl("120"),
        tl("100"),
        tl("160"),
    ]
    assert (full.opening_balance, full.closing_balance) == (tl("0"), tl("160"))

    later = books.statement(since=middle.isoformat())
    assert later.opening_balance == tl("120")
    assert [line.entry.kind for line in later.lines] == [
        EntryKind.PAYMENT,
        EntryKind.CHARGE,
    ]
    earlier = books.statement(until=middle.isoformat())
    assert earlier.closing_balance == tl("120")

    future = (middle + timedelta(days=1)).isoformat()
    backwards = books.client.get(
        f"/accounts/customers/{books.customer}/statement",
        params={"since": future, "until": middle.isoformat()},
    )
    assert backwards.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    naive = books.client.get(
        f"/accounts/customers/{books.customer}/statement",
        params={"since": "2026-11-26T10:00:00"},
    )
    assert naive.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_debtors_list(books: Books) -> None:
    """Who owes, most first, with their limit and last payment."""
    client = books.client
    other = CustomerView.model_validate_json(
        client.post("/customers", json={"name": "Kaya market"}).content
    )
    settled = CustomerView.model_validate_json(
        client.post("/customers", json={"name": "Paid up"}).content
    )

    def adjust(customer: EntityId, amount: str) -> None:
        body = {"customer_id": str(customer), "amount": amount, "reason": "x"}
        _ = entry(client.post("/accounts/adjustments", json=body))

    adjust(books.customer, "300")
    adjust(other.id, "900")
    adjust(settled.id, "50")
    _ = entry(
        client.post(
            "/accounts/payments",
            json={
                "customer_id": str(settled.id),
                "amount": "50",
                "method": "bank_transfer",
            },
        )
    )
    _ = entry(books.pay("100"))
    _ = client.put(
        f"/accounts/customers/{other.id}/credit-limit", json={"amount": "1000"}
    )

    debtors = DEBTORS.validate_json(client.get("/accounts/debtors").content)
    assert [(d.customer_name, d.balance) for d in debtors] == [
        ("Kaya market", tl("900")),
        ("Demir family", tl("200")),
    ]
    assert debtors[0].credit_limit == tl("1000")
    assert (debtors[0].last_payment_at, debtors[1].credit_limit) == (None, None)
    assert debtors[1].last_payment_at is not None


def test_unknown_customers(client: TestClient) -> None:
    """Accounts only exist for real customers."""
    missing = new_id()
    for url in (
        f"/accounts/customers/{missing}",
        f"/accounts/customers/{missing}/statement",
    ):
        assert client.get(url).status_code == HTTPStatus.NOT_FOUND
    payment = {"customer_id": str(missing), "amount": "1", "method": "cash"}
    assert client.post("/accounts/payments", json=payment).status_code == (
        HTTPStatus.NOT_FOUND
    )
    adjustment = {"customer_id": str(missing), "amount": "1", "reason": "x"}
    assert client.post("/accounts/adjustments", json=adjustment).status_code == (
        HTTPStatus.NOT_FOUND
    )
    limit = client.put(
        f"/accounts/customers/{missing}/credit-limit", json={"amount": "1"}
    )
    assert limit.status_code == HTTPStatus.NOT_FOUND
