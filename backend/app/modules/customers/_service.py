# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Customer logic. Private to this module."""

import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.core.ids import new_id
from app.modules.customers._models import Address, Customer, Phone
from app.modules.customers._phones import match_key
from app.modules.customers._views import (
    AddressView,
    CallerMatch,
    CustomerView,
    PhoneView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.customers._schemas import (
        AddressCreate,
        AddressUpdate,
        CustomerCreate,
        CustomerSearch,
        CustomerUpdate,
        PhoneCreate,
        PhoneUpdate,
    )

PHONE_TAKEN = "that phone number already belongs to a customer"


def _customer_view(customer: Customer) -> CustomerView:
    return CustomerView(
        id=customer.id,
        name=customer.name,
        notes=customer.notes,
        active=customer.active,
        phones=[
            PhoneView(
                id=phone.id,
                number=phone.number,
                default_address_id=phone.default_address_id,
            )
            for phone in customer.phones
        ],
        addresses=[
            AddressView(
                id=address.id,
                label=address.label,
                address=address.address,
                directions=address.directions,
                latitude=address.latitude,
                longitude=address.longitude,
            )
            for address in customer.addresses
        ],
    )


async def _load(session: AsyncSession, customer_id: EntityId) -> Customer:
    """Load a customer with phones and addresses, fresh from the database.

    Returns:
        The customer.

    Raises:
        NotFoundError: No such customer.
    """
    customer = await session.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(selectinload(Customer.phones), selectinload(Customer.addresses))
        .execution_options(populate_existing=True)
    )
    if customer is None:
        msg = f"customer {customer_id} not found"
        raise NotFoundError(msg)
    return customer


async def _save(session: AsyncSession, customer_id: EntityId) -> CustomerView:
    """Write changes and return the customer as now stored.

    Returns:
        The customer.

    Raises:
        ConflictError: A phone number is already taken.
    """
    try:
        await session.flush()
    except IntegrityError as error:
        raise ConflictError(PHONE_TAKEN) from error
    return _customer_view(await _load(session, customer_id))


def _address(customer: Customer, address_id: EntityId) -> Address:
    """Find one of the customer's addresses.

    Returns:
        The address.

    Raises:
        NotFoundError: The customer has no such address.
    """
    for address in customer.addresses:
        if address.id == address_id:
            return address
    msg = f"customer {customer.id} has no address {address_id}"
    raise NotFoundError(msg)


def _phone(customer: Customer, phone_id: EntityId) -> Phone:
    """Find one of the customer's phones.

    Returns:
        The phone.

    Raises:
        NotFoundError: The customer has no such phone.
    """
    for phone in customer.phones:
        if phone.id == phone_id:
            return phone
    msg = f"customer {customer.id} has no phone {phone_id}"
    raise NotFoundError(msg)


def _new_address(data: AddressCreate) -> Address:
    return Address(
        id=new_id(),
        label=data.label,
        address=data.address,
        directions=data.directions,
        latitude=data.latitude,
        longitude=data.longitude,
    )


# Customers


async def create_customer(session: AsyncSession, data: CustomerCreate) -> CustomerView:
    """Add a customer with any phones and addresses given.

    Returns:
        The new customer.
    """
    customer = Customer(id=new_id(), name=data.name, notes=data.notes)
    addresses = [_new_address(address) for address in data.addresses]
    customer.addresses.extend(addresses)
    customer.phones.extend(
        Phone(
            number=phone.number,
            match_key=match_key(phone.number),
            default_address_id=(
                None
                if phone.default_address_index is None
                else addresses[phone.default_address_index].id
            ),
        )
        for phone in data.phones
    )
    session.add(customer)
    return await _save(session, customer.id)


async def get_customer(session: AsyncSession, customer_id: EntityId) -> CustomerView:
    """Look up one customer.

    Returns:
        The customer with phones and addresses.
    """
    return _customer_view(await _load(session, customer_id))


async def search_customers(
    session: AsyncSession, search: CustomerSearch
) -> list[CustomerView]:
    """List customers by name, optionally filtered.

    Returns:
        Up to ``search.limit`` customers.
    """
    query = (
        select(Customer)
        .options(selectinload(Customer.phones), selectinload(Customer.addresses))
        .order_by(Customer.name, Customer.id)
        .limit(search.limit)
    )
    if search.q:
        # Treat %, _ and \ in the search text literally, not as LIKE wildcards.
        escaped = re.sub(r"([\\%_])", r"\\\1", search.q)
        query = query.where(Customer.name.ilike(f"%{escaped}%", escape="\\"))
    return [_customer_view(customer) for customer in await session.scalars(query)]


async def find_by_phone(session: AsyncSession, number: str) -> CallerMatch:
    """Find who a phone number belongs to, e.g. for an incoming call.

    Returns:
        The customer and the address to pre-select.

    Raises:
        NotFoundError: The number is unknown.
    """
    phone = await session.scalar(
        select(Phone).where(Phone.match_key == match_key(number))
    )
    if phone is None:
        msg = "no customer has that phone number"
        raise NotFoundError(msg)
    return CallerMatch(
        customer=_customer_view(await _load(session, phone.customer_id)),
        phone_id=phone.id,
        default_address_id=phone.default_address_id,
    )


async def update_customer(
    session: AsyncSession, customer_id: EntityId, data: CustomerUpdate
) -> CustomerView:
    """Rename, change notes, or (de)activate a customer.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    if data.name is not None:
        customer.name = data.name
    if "notes" in data.model_fields_set:
        customer.notes = data.notes
    if data.active is not None:
        customer.active = data.active
    return await _save(session, customer_id)


# Phones


async def add_phone(
    session: AsyncSession, customer_id: EntityId, data: PhoneCreate
) -> CustomerView:
    """Add a phone number to a customer.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    if data.default_address_id is not None:
        _ = _address(customer, data.default_address_id)
    customer.phones.append(
        Phone(
            number=data.number,
            match_key=match_key(data.number),
            default_address_id=data.default_address_id,
        )
    )
    return await _save(session, customer_id)


async def update_phone(
    session: AsyncSession, customer_id: EntityId, phone_id: EntityId, data: PhoneUpdate
) -> CustomerView:
    """Change or clear the address a phone pre-selects.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    phone = _phone(customer, phone_id)
    if data.default_address_id is not None:
        _ = _address(customer, data.default_address_id)
    phone.default_address_id = data.default_address_id
    return await _save(session, customer_id)


async def remove_phone(
    session: AsyncSession, customer_id: EntityId, phone_id: EntityId
) -> CustomerView:
    """Remove a phone number from a customer.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    customer.phones.remove(_phone(customer, phone_id))
    return await _save(session, customer_id)


# Addresses


async def add_address(
    session: AsyncSession, customer_id: EntityId, data: AddressCreate
) -> CustomerView:
    """Add a delivery address to a customer.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    customer.addresses.append(_new_address(data))
    return await _save(session, customer_id)


async def update_address(
    session: AsyncSession,
    customer_id: EntityId,
    address_id: EntityId,
    data: AddressUpdate,
) -> CustomerView:
    """Change an address.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    address = _address(customer, address_id)
    if data.address is not None:
        address.address = data.address
    sent = data.model_fields_set
    if "label" in sent:
        address.label = data.label
    if "directions" in sent:
        address.directions = data.directions
    if "latitude" in sent:  # the schema guarantees longitude came with it
        address.latitude, address.longitude = data.latitude, data.longitude
    return await _save(session, customer_id)


async def remove_address(
    session: AsyncSession, customer_id: EntityId, address_id: EntityId
) -> CustomerView:
    """Remove an address. Phones that pre-selected it lose their default.

    Returns:
        The updated customer.
    """
    customer = await _load(session, customer_id)
    customer.addresses.remove(_address(customer, address_id))
    return await _save(session, customer_id)
