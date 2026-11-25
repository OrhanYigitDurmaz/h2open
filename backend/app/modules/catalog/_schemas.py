# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the catalog endpoints. Private to this module."""

from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
)

from app.core.ids import EntityId
from app.core.money import Money
from app.modules.catalog._views import ContainerLink

if TYPE_CHECKING:
    from datetime import datetime

type Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
type ProductName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
type Code = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
type VatRate = Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)]


class BrandCreate(BaseModel):
    """A new brand."""

    name: Name


class BrandUpdate(BaseModel):
    """Changes to a brand; omitted fields stay as they are."""

    name: Name | None = None
    active: bool | None = None


class ContainerTypeCreate(BaseModel):
    """A new returnable container type."""

    brand_id: EntityId
    name: Name


class ContainerTypeUpdate(BaseModel):
    """Changes to a container type; omitted fields stay as they are."""

    name: Name | None = None
    active: bool | None = None


class PriceCreate(BaseModel):
    """A new price, effective now or from a future (or past) moment."""

    price: Money
    valid_from: AwareDatetime | None = None
    """Defaults to now."""

    @field_validator("price")
    @classmethod
    def _not_negative(cls, price: Money) -> Money:
        if price.amount < 0:
            msg = "a price cannot be negative"
            raise ValueError(msg)
        return price

    def effective_from(self, now: datetime) -> datetime:
        """When the price takes effect.

        Args:
            now: The current time.

        Returns:
            ``valid_from`` if given, otherwise ``now``.
        """
        return self.valid_from or now


class ProductCreate(BaseModel):
    """A new product."""

    sku: Code
    name: ProductName
    barcode: Code | None = None
    brand_id: EntityId | None = None
    vat_rate: VatRate
    container: ContainerLink | None = None
    """Set for products sold in returnable containers. Cannot be changed later."""


class ProductUpdate(BaseModel):
    """Changes to a product; omitted fields stay as they are.

    The SKU, brand and container link are fixed once a product exists:
    sales and container balances depend on them. Create a new product instead.
    """

    name: ProductName | None = None
    barcode: Code | None = None
    """Send ``null`` explicitly to remove the barcode."""
    vat_rate: VatRate | None = None
    active: bool | None = None
