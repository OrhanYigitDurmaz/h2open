# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the customers module. Private to this module."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.customers import _service
from app.modules.customers._schemas import (
    AddressCreate,
    AddressUpdate,
    CustomerCreate,
    CustomerSearch,
    CustomerUpdate,
    PhoneCreate,
    PhoneUpdate,
)
from app.modules.customers._views import CallerMatch, CustomerView

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", status_code=HTTPStatus.CREATED)
async def create_customer(session: SessionDep, data: CustomerCreate) -> CustomerView:
    """Add a customer, optionally with phones and addresses.

    Returns:
        The new customer.
    """
    return await _service.create_customer(session, data)


@router.get("")
async def search_customers(
    session: SessionDep, search: Annotated[CustomerSearch, Query()]
) -> list[CustomerView]:
    """List customers by name, optionally filtered by part of the name.

    Returns:
        The matching customers.
    """
    return await _service.search_customers(session, search)


@router.get("/by-phone/{number}")
async def find_by_phone(session: SessionDep, number: str) -> CallerMatch:
    """Find the customer a phone number belongs to, e.g. for an incoming call.

    Returns:
        The customer and the address to pre-select.
    """
    return await _service.find_by_phone(session, number)


@router.get("/{customer_id}")
async def get_customer(session: SessionDep, customer_id: EntityId) -> CustomerView:
    """Get one customer with phones and addresses.

    Returns:
        The customer.
    """
    return await _service.get_customer(session, customer_id)


@router.patch("/{customer_id}")
async def update_customer(
    session: SessionDep, customer_id: EntityId, data: CustomerUpdate
) -> CustomerView:
    """Rename, change notes, or (de)activate a customer.

    Returns:
        The updated customer.
    """
    return await _service.update_customer(session, customer_id, data)


@router.post("/{customer_id}/phones", status_code=HTTPStatus.CREATED)
async def add_phone(
    session: SessionDep, customer_id: EntityId, data: PhoneCreate
) -> CustomerView:
    """Add a phone number.

    Returns:
        The updated customer.
    """
    return await _service.add_phone(session, customer_id, data)


@router.patch("/{customer_id}/phones/{phone_id}")
async def update_phone(
    session: SessionDep, customer_id: EntityId, phone_id: EntityId, data: PhoneUpdate
) -> CustomerView:
    """Change or clear the address a phone pre-selects.

    Returns:
        The updated customer.
    """
    return await _service.update_phone(session, customer_id, phone_id, data)


@router.delete("/{customer_id}/phones/{phone_id}")
async def remove_phone(
    session: SessionDep, customer_id: EntityId, phone_id: EntityId
) -> CustomerView:
    """Remove a phone number.

    Returns:
        The updated customer.
    """
    return await _service.remove_phone(session, customer_id, phone_id)


@router.post("/{customer_id}/addresses", status_code=HTTPStatus.CREATED)
async def add_address(
    session: SessionDep, customer_id: EntityId, data: AddressCreate
) -> CustomerView:
    """Add a delivery address.

    Returns:
        The updated customer.
    """
    return await _service.add_address(session, customer_id, data)


@router.patch("/{customer_id}/addresses/{address_id}")
async def update_address(
    session: SessionDep,
    customer_id: EntityId,
    address_id: EntityId,
    data: AddressUpdate,
) -> CustomerView:
    """Change an address.

    Returns:
        The updated customer.
    """
    return await _service.update_address(session, customer_id, address_id, data)


@router.delete("/{customer_id}/addresses/{address_id}")
async def remove_address(
    session: SessionDep, customer_id: EntityId, address_id: EntityId
) -> CustomerView:
    """Remove an address; phones that pre-selected it lose their default.

    Returns:
        The updated customer.
    """
    return await _service.remove_address(session, customer_id, address_id)
