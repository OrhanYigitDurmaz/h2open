# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the customer endpoints. Private to this module."""

from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.core.ids import EntityId

type Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
type Notes = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
type Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
type AddressText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
type Directions = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
type PhoneNumber = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=30,
        # Digits with optional +, spaces, dashes and parentheses; 7+ digits.
        pattern=r"^\+?(?:[ ()-]*\d){7,}[ ()-]*$",
    ),
]
type Latitude = Annotated[Decimal, Field(ge=-90, le=90, decimal_places=6)]
type Longitude = Annotated[Decimal, Field(ge=-180, le=180, decimal_places=6)]


class AddressCreate(BaseModel):
    """A new delivery address."""

    label: Label | None = None
    address: AddressText
    directions: Directions | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @model_validator(mode="after")
    def _coordinates_complete(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            msg = "give both latitude and longitude, or neither"
            raise ValueError(msg)
        return self


class AddressUpdate(BaseModel):
    """Changes to an address; omitted fields stay as they are.

    Send ``null`` to clear the label or directions. Coordinates are replaced
    together: send both, or both as ``null`` to clear them.
    """

    label: Label | None = None
    address: AddressText | None = None
    directions: Directions | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @model_validator(mode="after")
    def _coordinates_together(self) -> Self:
        sent = {"latitude", "longitude"} & self.model_fields_set
        if len(sent) == 1 or (self.latitude is None) != (self.longitude is None):
            msg = "change latitude and longitude together"
            raise ValueError(msg)
        return self


class PhoneCreate(BaseModel):
    """A new phone number for an existing customer."""

    number: PhoneNumber
    default_address_id: EntityId | None = None


class PhoneUpdate(BaseModel):
    """Change which address a phone pre-selects; ``null`` clears it."""

    default_address_id: EntityId | None


class NewCustomerPhone(BaseModel):
    """A phone given while creating a customer.

    Its default address is picked by position in the request's
    ``addresses`` list, since those addresses have no IDs yet.
    """

    number: PhoneNumber
    default_address_index: Annotated[int, Field(ge=0)] | None = None


class CustomerCreate(BaseModel):
    """A new customer, optionally with phones and addresses."""

    name: Name
    notes: Notes | None = None
    addresses: list[AddressCreate] = []
    phones: list[NewCustomerPhone] = []

    @model_validator(mode="after")
    def _indexes_exist(self) -> Self:
        for phone in self.phones:
            index = phone.default_address_index
            if index is not None and index >= len(self.addresses):
                msg = f"default_address_index {index} has no matching address"
                raise ValueError(msg)
        return self


class CustomerUpdate(BaseModel):
    """Changes to a customer; omitted fields stay as they are."""

    name: Name | None = None
    notes: Notes | None = None
    """Send ``null`` to clear the notes."""
    active: bool | None = None


class CustomerSearch(BaseModel):
    """Query parameters for listing customers."""

    q: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    """Part of the name, case-insensitive."""
    limit: Annotated[int, Field(ge=1, le=200)] = 50
