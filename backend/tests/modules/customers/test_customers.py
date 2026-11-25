# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for customers, phones and addresses."""

import asyncio
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.modules.customers import api
from app.modules.customers.api import CallerMatch, CustomerView

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response

    from app.core.db import Database

CUSTOMERS = TypeAdapter(list[CustomerView])
PAGE = 2


def create(client: TestClient, body: dict[str, object]) -> CustomerView:
    """Create a customer through the API.

    Returns:
        The customer.
    """
    response = client.post("/customers", json=body)
    assert response.status_code == HTTPStatus.CREATED, response.text
    return CustomerView.model_validate_json(response.content)


def family(client: TestClient) -> CustomerView:
    """A customer with two addresses; the landline defaults to the summer house.

    Returns:
        The customer.
    """
    return create(
        client,
        {
            "name": "Demir family",
            "addresses": [
                {
                    "label": "Home",
                    "address": "Atatürk Cd. 1",
                    "directions": "3rd floor",
                },
                {
                    "label": "Summer house",
                    "address": "Sahil Yolu 7",
                    "latitude": "40.123456",
                    "longitude": "29.654321",
                },
            ],
            "phones": [
                {"number": "0532 123 45 67"},
                {"number": "(0224) 555 11 22", "default_address_index": 1},
            ],
        },
    )


def updated(response: Response) -> CustomerView:
    """Parse a customer from a successful response.

    Returns:
        The customer.
    """
    assert response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}, response.text
    return CustomerView.model_validate_json(response.content)


def test_create_with_phones_and_addresses(client: TestClient) -> None:
    """Phones can default to one of the addresses created with them."""
    customer = family(client)
    home, summer = customer.addresses
    mobile, landline = customer.phones
    assert (home.label, summer.label) == ("Home", "Summer house")
    assert summer.latitude == Decimal("40.123456")
    assert mobile.default_address_id is None
    assert landline.default_address_id == summer.id
    fetched = client.get(f"/customers/{customer.id}")
    assert CustomerView.model_validate_json(fetched.content) == customer


@pytest.mark.parametrize(
    "number", ["05321234567", "+90 532 123 45 67", "905321234567", "532-123-4567"]
)
def test_find_by_phone_in_any_format(client: TestClient, number: str) -> None:
    """Caller ID matches regardless of formatting and prefix."""
    customer = family(client)
    response = client.get(f"/customers/by-phone/{number}")
    match = CallerMatch.model_validate_json(response.content)
    assert match.customer == customer
    assert match.phone_id == customer.phones[0].id
    assert match.default_address_id is None


def test_caller_gets_the_phones_default_address(client: TestClient) -> None:
    """A call from the landline pre-selects the summer house."""
    customer = family(client)
    response = client.get("/customers/by-phone/02245551122")
    match = CallerMatch.model_validate_json(response.content)
    assert match.default_address_id == customer.addresses[1].id
    assert client.get("/customers/by-phone/0999999999").status_code == (
        HTTPStatus.NOT_FOUND
    )


def test_phone_numbers_are_unique(client: TestClient) -> None:
    """The same number, however written, cannot belong to two customers."""
    customer = family(client)
    response = client.post(
        "/customers", json={"name": "Other", "phones": [{"number": "+905321234567"}]}
    )
    assert response.status_code == HTTPStatus.CONFLICT
    other = create(client, {"name": "Other"})
    response = client.post(
        f"/customers/{other.id}/phones", json={"number": "0 532 123 45 67"}
    )
    assert response.status_code == HTTPStatus.CONFLICT
    again = client.post(
        f"/customers/{customer.id}/phones", json={"number": "05321234567"}
    )
    assert again.status_code == HTTPStatus.CONFLICT


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "X", "phones": [{"number": "12345"}]},
        {"name": "X", "phones": [{"number": "call me"}]},
        {
            "name": "X",
            "phones": [{"number": "05321234567", "default_address_index": 0}],
        },
        {"name": "X", "addresses": [{"address": "A", "latitude": "40"}]},
        {
            "name": "X",
            "addresses": [{"address": "A", "latitude": "91", "longitude": "0"}],
        },
    ],
)
def test_invalid_customers(client: TestClient, body: dict[str, object]) -> None:
    """Bad names, numbers, address indexes and coordinates are rejected."""
    assert client.post("/customers", json=body).status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )


def test_search(client: TestClient) -> None:
    """Search by part of the name, case-insensitive; % and _ are literal."""
    for name in ("Ayşe Kaya", "Mehmet Kaya", "Ali Demir", "100% Water Ltd", "A_B"):
        _ = create(client, {"name": name})

    def names(query: str) -> list[str]:
        response = client.get(f"/customers?{query}")
        return [customer.name for customer in CUSTOMERS.validate_json(response.content)]

    assert names("q=kaya") == ["Ayşe Kaya", "Mehmet Kaya"]
    assert names("q=%25") == ["100% Water Ltd"]
    assert names("q=_") == ["A_B"]
    assert len(names(f"limit={PAGE}")) == PAGE
    assert names("") == sorted(names(""))
    assert client.get("/customers?limit=0").status_code == (
        HTTPStatus.UNPROCESSABLE_CONTENT
    )


def test_update_customer(client: TestClient) -> None:
    """Name, notes and active flag change; null clears the notes."""
    customer = create(client, {"name": "A", "notes": "Pays monthly"})
    url = f"/customers/{customer.id}"
    changed = updated(client.patch(url, json={"name": "B", "active": False}))
    assert (changed.name, changed.notes, changed.active) == ("B", "Pays monthly", False)
    cleared = updated(client.patch(url, json={"notes": None}))
    assert cleared.notes is None
    missing = client.patch(f"/customers/{new_id()}", json={})
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"/customers/{new_id()}").status_code == HTTPStatus.NOT_FOUND


def test_manage_phones(client: TestClient) -> None:
    """Phones can be added, re-pointed to another address, and removed."""
    customer = family(client)
    home, summer = customer.addresses
    base = f"/customers/{customer.id}/phones"

    added = updated(
        client.post(
            base, json={"number": "0533 000 00 00", "default_address_id": str(home.id)}
        )
    )
    new_phone = added.phones[-1]
    assert new_phone.default_address_id == home.id

    moved = updated(
        client.patch(
            f"{base}/{new_phone.id}", json={"default_address_id": str(summer.id)}
        )
    )
    assert moved.phones[-1].default_address_id == summer.id
    cleared = updated(
        client.patch(f"{base}/{new_phone.id}", json={"default_address_id": None})
    )
    assert cleared.phones[-1].default_address_id is None

    removed = updated(client.delete(f"{base}/{new_phone.id}"))
    assert [phone.id for phone in removed.phones] == [p.id for p in customer.phones]


def test_phone_errors(client: TestClient) -> None:
    """Phones cannot point at another customer's address or unknown phones."""
    customer = family(client)
    stranger = create(
        client, {"name": "Other", "addresses": [{"address": "Elsewhere"}]}
    )
    foreign = str(stranger.addresses[0].id)
    base = f"/customers/{customer.id}/phones"
    response = client.post(
        base, json={"number": "05330000000", "default_address_id": foreign}
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    phone = customer.phones[0].id
    response = client.patch(f"{base}/{phone}", json={"default_address_id": foreign})
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert client.delete(f"{base}/{new_id()}").status_code == HTTPStatus.NOT_FOUND
    assert client.post(
        f"/customers/{new_id()}/phones", json={"number": "05330000000"}
    ).status_code == (HTTPStatus.NOT_FOUND)


def test_manage_addresses(client: TestClient) -> None:
    """Addresses can be added, edited field by field, and removed."""
    customer = family(client)
    home, summer = customer.addresses
    base = f"/customers/{customer.id}/addresses"

    added = updated(client.post(base, json={"label": "Office", "address": "Plaza 5"}))
    assert added.addresses[-1].label == "Office"

    url = f"{base}/{home.id}"
    edited = updated(
        client.patch(
            url,
            json={
                "address": "Atatürk Cd. 2",
                "label": None,
                "latitude": "1.5",
                "longitude": "2.5",
            },
        )
    )
    new_home = edited.addresses[0]
    assert (new_home.address, new_home.label, new_home.directions) == (
        "Atatürk Cd. 2",
        None,
        "3rd floor",
    )
    assert (new_home.latitude, new_home.longitude) == (Decimal("1.5"), Decimal("2.5"))

    edited = updated(
        client.patch(
            url, json={"directions": None, "latitude": None, "longitude": None}
        )
    )
    assert edited.addresses[0].directions is None
    assert edited.addresses[0].latitude is None
    unchanged = updated(client.patch(url, json={}))
    assert unchanged.addresses[0] == edited.addresses[0]

    removed = updated(client.delete(f"{base}/{summer.id}"))
    assert [address.id for address in removed.addresses] == [
        home.id,
        added.addresses[-1].id,
    ]
    landline = removed.phones[1]
    assert landline.default_address_id is None  # cleared with the address
    assert removed.phones == [customer.phones[0], landline]


def test_address_errors(client: TestClient) -> None:
    """Coordinates change together; unknown addresses are not found."""
    customer = family(client)
    url = f"/customers/{customer.id}/addresses/{customer.addresses[0].id}"
    for body in ({"latitude": "1"}, {"latitude": "1", "longitude": None}):
        assert client.patch(url, json=body).status_code == (
            HTTPStatus.UNPROCESSABLE_CONTENT
        )
    missing = f"/customers/{customer.id}/addresses/{new_id()}"
    assert client.patch(missing, json={}).status_code == HTTPStatus.NOT_FOUND
    assert client.delete(missing).status_code == HTTPStatus.NOT_FOUND


def test_public_api(client: TestClient, database: Database) -> None:
    """Other modules (and later the phone system) look customers up via api."""
    customer = family(client)

    async def lookup(number: str) -> CallerMatch:
        async with database.transaction() as session:
            return await api.find_by_phone(session, number)

    assert asyncio.run(lookup("+90 224 555 11 22")).customer == customer
    with pytest.raises(NotFoundError):
        _ = asyncio.run(lookup("0000000000"))
