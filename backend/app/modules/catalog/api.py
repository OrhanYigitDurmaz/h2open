# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the catalog module.

Other modules may import this file (and only this file) to read products,
brands and container types. The views here are also the HTTP responses.
"""

from typing import TYPE_CHECKING

from app.modules.catalog import _service
from app.modules.catalog._views import (
    BrandView,
    ContainerLink,
    ContainerTypeView,
    PriceView,
    ProductView,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.core.money import Money

__all__ = [
    "BrandView",
    "ContainerLink",
    "ContainerTypeView",
    "PriceView",
    "ProductView",
    "get_deposit",
    "get_product",
]


async def get_product(session: AsyncSession, product_id: EntityId) -> ProductView:
    """Look up one product with its current price.

    Args:
        session: The caller's database session.
        product_id: The product to look up.

    Returns:
        The product.
    """
    return await _service.get_product(session, product_id)


async def get_deposit(
    session: AsyncSession, container_type_id: EntityId, at: datetime
) -> Money | None:
    """Look up the deposit for a container type at a point in time.

    Args:
        session: The caller's database session.
        container_type_id: The container type.
        at: When the deposit is charged.

    Returns:
        The deposit in effect at ``at``, or ``None`` if none was set yet.
    """
    return await _service.deposit_at(session, container_type_id, at)
