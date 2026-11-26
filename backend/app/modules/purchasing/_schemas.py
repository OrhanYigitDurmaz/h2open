# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the purchasing endpoints. Private to this module."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    Field,
    PositiveInt,
    StringConstraints,
    model_validator,
)

from app.core.ids import EntityId
from app.core.money import CurrencyCode
from app.modules.containers.api import ContainerCount
from app.modules.purchasing._views import LineKind, SupplierPaymentMethod

type Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
type Notes = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
type Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
type TaxNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^\d{10,11}$")
]
"""A Turkish tax number (VKN, 10 digits) or national ID (TCKN, 11 digits)."""
type Phone = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
]
type DocumentNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
type Reference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
type Amount = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
type VatRate = Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)]


class SupplierCreate(BaseModel):
    """A new supplier."""

    name: Name
    tax_number: TaxNumber | None = None
    phone: Phone | None = None
    notes: Notes | None = None


class SupplierUpdate(BaseModel):
    """Changes to a supplier; omitted fields stay, ``null`` clears."""

    name: Name | None = None
    tax_number: TaxNumber | None = None
    phone: Phone | None = None
    notes: Notes | None = None
    active: bool | None = None


class ReceiptLineIn(BaseModel):
    """One line as printed on the receipt.

    ``net_amount`` is the line amount before VAT, as Turkish invoices print
    it. VAT is worked out from ``vat_rate``.
    """

    kind: LineKind
    product_id: EntityId | None = None
    """Required for goods lines."""
    container_type_id: EntityId | None = None
    """Required for container purchase and renewal lines."""
    description: Name | None = None
    """Defaults to the product or container name; required for other lines."""
    quantity: PositiveInt = 1
    net_amount: Amount
    vat_rate: VatRate

    @model_validator(mode="after")
    def _complete(self) -> Self:
        goods = self.kind is LineKind.GOODS
        container = self.kind in {
            LineKind.CONTAINER_PURCHASE,
            LineKind.CONTAINER_RENEWAL,
        }
        if (self.product_id is not None) != goods:
            msg = "goods lines, and only those, name a product"
            raise ValueError(msg)
        if (self.container_type_id is not None) != container:
            msg = "container lines, and only those, name a container type"
            raise ValueError(msg)
        if self.kind is LineKind.OTHER and self.description is None:
            msg = "other lines need a description"
            raise ValueError(msg)
        return self


class ReceiptCreate(BaseModel):
    """A supplier's receipt, typed in from the paper."""

    supplier_id: EntityId
    document_number: DocumentNumber
    issued_on: date
    currency: CurrencyCode = "TRY"
    lines: Annotated[list[ReceiptLineIn], Field(min_length=1)]
    empties_returned: list[ContainerCount] = []
    """Empties handed to the supplier, including old ones being renewed."""
    total: Amount
    """The grand total printed on the receipt, checked against the lines."""
    notes: Notes | None = None

    @model_validator(mode="after")
    def _unique_types(self) -> Self:
        types = [count.container_type_id for count in self.empties_returned]
        if len(set(types)) != len(types):
            msg = "list each container type once"
            raise ValueError(msg)
        return self


class Void(BaseModel):
    """Why a receipt or payment is voided."""

    reason: Reason


class PaymentCreate(BaseModel):
    """Money paid to a supplier."""

    supplier_id: EntityId
    receipt_id: EntityId | None = None
    """The receipt it pays, if it is for one in particular."""
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    currency: CurrencyCode = "TRY"
    method: SupplierPaymentMethod
    paid_on: date
    reference: Reference | None = None
    """Bank transfer reference, slip number and the like."""


class ReceiptSearch(BaseModel):
    """Query parameters for listing receipts."""

    supplier_id: EntityId | None = None
    include_voided: bool = False
    limit: Annotated[int, Field(ge=1, le=200)] = 50


class PaymentSearch(BaseModel):
    """Query parameters for listing payments."""

    supplier_id: EntityId | None = None
    receipt_id: EntityId | None = None
    include_voided: bool = False
    limit: Annotated[int, Field(ge=1, le=200)] = 50
