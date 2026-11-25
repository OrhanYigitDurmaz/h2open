# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the customers module. Other modules get them via ``api``."""

from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class AddressView(_View):
    """A delivery address."""

    id: EntityId
    label: str | None
    """A short name staff use, e.g. "Home" or "Summer house"."""
    address: str
    directions: str | None
    """Notes for the driver: floor, entrance, landmarks."""
    latitude: Decimal | None
    longitude: Decimal | None


class PhoneView(_View):
    """A phone number of a customer."""

    id: EntityId
    number: str
    default_address_id: EntityId | None
    """The address to pre-select when this number calls."""


class CustomerView(_View):
    """A customer with all their phones and addresses."""

    id: EntityId
    name: str
    notes: str | None
    active: bool
    phones: list[PhoneView]
    addresses: list[AddressView]


class CallerMatch(_View):
    """The customer a phone number belongs to, for incoming calls."""

    customer: CustomerView
    phone_id: EntityId
    default_address_id: EntityId | None
    """The phone's default address, if it has one."""
