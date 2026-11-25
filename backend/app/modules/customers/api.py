# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the customers module."""

from typing import TYPE_CHECKING

from app.modules.customers import _service
from app.modules.customers._views import (
    AddressView,
    CallerMatch,
    CustomerView,
    PhoneView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId

__all__ = [
    "AddressView",
    "CallerMatch",
    "CustomerView",
    "PhoneView",
    "find_by_phone",
    "get_customer",
]


async def get_customer(session: AsyncSession, customer_id: EntityId) -> CustomerView:
    """Look up one customer.

    Args:
        session: The caller's database session.
        customer_id: The customer.

    Returns:
        The customer with phones and addresses.
    """
    return await _service.get_customer(session, customer_id)


async def find_by_phone(session: AsyncSession, number: str) -> CallerMatch:
    """Find who a phone number belongs to, e.g. from caller ID.

    Args:
        session: The caller's database session.
        number: The phone number in any common format.

    Returns:
        The customer and the address to pre-select.
    """
    return await _service.find_by_phone(session, number)
