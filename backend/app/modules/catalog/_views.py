# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the catalog. Private; other modules get them via ``api``."""

from datetime import datetime
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, PositiveInt

from app.core.ids import EntityId
from app.core.money import Money


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class BrandView(_View):
    """A brand."""

    id: EntityId
    name: str
    active: bool


class ContainerTypeView(_View):
    """A returnable container type and its current deposit."""

    id: EntityId
    brand_id: EntityId
    name: str
    active: bool
    deposit: Money | None
    """The deposit in effect now; ``None`` if no price is set yet."""


class ContainerLink(_View):
    """How a product uses returnable containers."""

    container_type_id: EntityId
    quantity: PositiveInt
    """Containers per unit sold, usually 1."""


class ProductView(_View):
    """A product and its current price."""

    id: EntityId
    sku: str
    name: str
    barcode: str | None
    brand_id: EntityId | None
    vat_rate: Decimal
    """VAT percentage, e.g. ``20`` for 20 %."""
    container: ContainerLink | None
    """Set when the product comes in returnable containers."""
    active: bool
    price: Money | None
    """The sale price in effect now, VAT included; ``None`` if not priced yet."""


class PriceView(_View):
    """One entry in a price history."""

    price: Money
    valid_from: datetime
