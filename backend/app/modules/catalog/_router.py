# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the catalog. Private to this module."""

from http import HTTPStatus

from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.catalog import _service
from app.modules.catalog._schemas import (
    BrandCreate,
    BrandUpdate,
    ContainerTypeCreate,
    ContainerTypeUpdate,
    PriceCreate,
    ProductCreate,
    ProductUpdate,
)
from app.modules.catalog._views import (
    BrandView,
    ContainerTypeView,
    PriceView,
    ProductView,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("/brands", status_code=HTTPStatus.CREATED)
async def create_brand(session: SessionDep, data: BrandCreate) -> BrandView:
    """Add a brand.

    Returns:
        The new brand.
    """
    return await _service.create_brand(session, data)


@router.get("/brands")
async def list_brands(session: SessionDep) -> list[BrandView]:
    """List brands.

    Returns:
        Every brand, by name.
    """
    return await _service.list_brands(session)


@router.patch("/brands/{brand_id}")
async def update_brand(
    session: SessionDep, brand_id: EntityId, data: BrandUpdate
) -> BrandView:
    """Rename or (de)activate a brand.

    Returns:
        The updated brand.
    """
    return await _service.update_brand(session, brand_id, data)


@router.post("/container-types", status_code=HTTPStatus.CREATED)
async def create_container_type(
    session: SessionDep, data: ContainerTypeCreate
) -> ContainerTypeView:
    """Add a returnable container type to a brand.

    Returns:
        The new container type.
    """
    return await _service.create_container_type(session, data)


@router.get("/container-types")
async def list_container_types(session: SessionDep) -> list[ContainerTypeView]:
    """List container types with their current deposits.

    Returns:
        Every container type, by name.
    """
    return await _service.list_container_types(session)


@router.patch("/container-types/{container_type_id}")
async def update_container_type(
    session: SessionDep, container_type_id: EntityId, data: ContainerTypeUpdate
) -> ContainerTypeView:
    """Rename or (de)activate a container type.

    Returns:
        The updated container type.
    """
    return await _service.update_container_type(session, container_type_id, data)


@router.post(
    "/container-types/{container_type_id}/deposits", status_code=HTTPStatus.CREATED
)
async def add_deposit_price(
    session: SessionDep, container_type_id: EntityId, data: PriceCreate
) -> PriceView:
    """Set a new deposit, now or from a given moment.

    Returns:
        The new deposit history entry.
    """
    return await _service.add_deposit_price(session, container_type_id, data)


@router.get("/container-types/{container_type_id}/deposits")
async def deposit_history(
    session: SessionDep, container_type_id: EntityId
) -> list[PriceView]:
    """List a container type's deposits, newest first.

    Returns:
        The deposit history.
    """
    return await _service.deposit_history(session, container_type_id)


@router.post("/products", status_code=HTTPStatus.CREATED)
async def create_product(session: SessionDep, data: ProductCreate) -> ProductView:
    """Add a product.

    Returns:
        The new product.
    """
    return await _service.create_product(session, data)


@router.get("/products")
async def list_products(session: SessionDep) -> list[ProductView]:
    """List products with their current prices.

    Returns:
        Every product, by name.
    """
    return await _service.list_products(session)


@router.get("/products/{product_id}")
async def get_product(session: SessionDep, product_id: EntityId) -> ProductView:
    """Get one product with its current price.

    Returns:
        The product.
    """
    return await _service.get_product(session, product_id)


@router.patch("/products/{product_id}")
async def update_product(
    session: SessionDep, product_id: EntityId, data: ProductUpdate
) -> ProductView:
    """Change a product's name, barcode, VAT rate or active flag.

    Returns:
        The updated product.
    """
    return await _service.update_product(session, product_id, data)


@router.post("/products/{product_id}/prices", status_code=HTTPStatus.CREATED)
async def add_product_price(
    session: SessionDep, product_id: EntityId, data: PriceCreate
) -> PriceView:
    """Set a new price, now or from a given moment.

    Returns:
        The new price history entry.
    """
    return await _service.add_product_price(session, product_id, data)


@router.get("/products/{product_id}/prices")
async def price_history(session: SessionDep, product_id: EntityId) -> list[PriceView]:
    """List a product's prices, newest first.

    Returns:
        The price history.
    """
    return await _service.price_history(session, product_id)
