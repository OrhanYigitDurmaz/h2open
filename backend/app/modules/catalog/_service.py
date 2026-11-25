# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Catalog business logic. Private to this module."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.money import Money
from app.modules.catalog._models import (
    Base,
    Brand,
    ContainerType,
    DepositPrice,
    Product,
    ProductPrice,
)
from app.modules.catalog._views import (
    BrandView,
    ContainerLink,
    ContainerTypeView,
    PriceView,
    ProductView,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.catalog._schemas import (
        BrandCreate,
        BrandUpdate,
        ContainerTypeCreate,
        ContainerTypeUpdate,
        PriceCreate,
        ProductCreate,
        ProductUpdate,
    )


def _now() -> datetime:
    return datetime.now(UTC)


async def _get[M: Base](
    session: AsyncSession, model: type[M], entity_id: EntityId
) -> M:
    entity = await session.get(model, entity_id)
    if entity is None:
        msg = f"{model.__name__} {entity_id} not found"
        raise NotFoundError(msg)
    return entity


async def _flush(session: AsyncSession, conflict: str) -> None:
    """Write pending changes, turning unique-constraint violations into conflicts.

    Raises:
        ConflictError: A unique value (name, SKU, barcode, ...) is taken.
    """
    try:
        await session.flush()
    except IntegrityError as error:
        raise ConflictError(conflict) from error


def _price_view(row: DepositPrice | ProductPrice) -> PriceView:
    return PriceView(
        price=Money(amount=row.amount, currency=row.currency),
        valid_from=row.valid_from,
    )


# Brands


def _brand_view(brand: Brand) -> BrandView:
    return BrandView(id=brand.id, name=brand.name, active=brand.active)


async def create_brand(session: AsyncSession, data: BrandCreate) -> BrandView:
    """Add a brand.

    Returns:
        The new brand.
    """
    brand = Brand(name=data.name)
    session.add(brand)
    await _flush(session, f"brand {data.name!r} already exists")
    return _brand_view(brand)


async def list_brands(session: AsyncSession) -> list[BrandView]:
    """List every brand by name.

    Returns:
        The brands.
    """
    brands = await session.scalars(select(Brand).order_by(Brand.name))
    return [_brand_view(brand) for brand in brands]


async def update_brand(
    session: AsyncSession, brand_id: EntityId, data: BrandUpdate
) -> BrandView:
    """Rename or (de)activate a brand.

    Returns:
        The updated brand.
    """
    brand = await _get(session, Brand, brand_id)
    if data.name is not None:
        brand.name = data.name
    if data.active is not None:
        brand.active = data.active
    await _flush(session, f"brand {data.name!r} already exists")
    return _brand_view(brand)


# Container types and deposits


async def deposit_at(
    session: AsyncSession, container_type_id: EntityId, at: datetime
) -> Money | None:
    """Find the deposit in effect for a container type at a moment.

    Returns:
        The deposit, or ``None`` if none was set by then.
    """
    deposits = await _deposits_at(session, [container_type_id], at)
    return deposits.get(container_type_id)


async def _deposits_at(
    session: AsyncSession, container_type_ids: Sequence[EntityId], at: datetime
) -> dict[EntityId, Money]:
    rows = await session.scalars(
        select(DepositPrice)
        .where(
            DepositPrice.container_type_id.in_(container_type_ids),
            DepositPrice.valid_from <= at,
        )
        .order_by(DepositPrice.container_type_id, DepositPrice.valid_from.desc())
        .ext(distinct_on(DepositPrice.container_type_id))
    )
    return {
        row.container_type_id: Money(amount=row.amount, currency=row.currency)
        for row in rows
    }


def _container_type_view(
    container_type: ContainerType, deposit: Money | None
) -> ContainerTypeView:
    return ContainerTypeView(
        id=container_type.id,
        brand_id=container_type.brand_id,
        name=container_type.name,
        active=container_type.active,
        deposit=deposit,
    )


async def create_container_type(
    session: AsyncSession, data: ContainerTypeCreate
) -> ContainerTypeView:
    """Add a container type to a brand.

    Returns:
        The new container type, with no deposit yet.
    """
    _ = await _get(session, Brand, data.brand_id)
    container_type = ContainerType(brand_id=data.brand_id, name=data.name)
    session.add(container_type)
    await _flush(session, f"the brand already has a container type {data.name!r}")
    return _container_type_view(container_type, None)


async def list_container_types(session: AsyncSession) -> list[ContainerTypeView]:
    """List every container type with its current deposit.

    Returns:
        The container types, ordered by name.
    """
    container_types = list(
        await session.scalars(select(ContainerType).order_by(ContainerType.name))
    )
    deposits = await _deposits_at(
        session, [container_type.id for container_type in container_types], _now()
    )
    return [
        _container_type_view(container_type, deposits.get(container_type.id))
        for container_type in container_types
    ]


async def update_container_type(
    session: AsyncSession, container_type_id: EntityId, data: ContainerTypeUpdate
) -> ContainerTypeView:
    """Rename or (de)activate a container type.

    Returns:
        The updated container type.
    """
    container_type = await _get(session, ContainerType, container_type_id)
    if data.name is not None:
        container_type.name = data.name
    if data.active is not None:
        container_type.active = data.active
    await _flush(session, f"the brand already has a container type {data.name!r}")
    return _container_type_view(
        container_type, await deposit_at(session, container_type_id, _now())
    )


async def add_deposit_price(
    session: AsyncSession, container_type_id: EntityId, data: PriceCreate
) -> PriceView:
    """Set a new deposit for a container type.

    Deposits already charged keep the amount recorded at the time.

    Returns:
        The new history entry.
    """
    _ = await _get(session, ContainerType, container_type_id)
    row = DepositPrice(
        container_type_id=container_type_id,
        amount=data.price.amount,
        currency=data.price.currency,
        valid_from=data.effective_from(_now()),
    )
    session.add(row)
    await _flush(session, "a deposit already starts at that moment")
    return _price_view(row)


async def deposit_history(
    session: AsyncSession, container_type_id: EntityId
) -> list[PriceView]:
    """List a container type's deposits, newest first.

    Returns:
        The history, including scheduled future changes.
    """
    _ = await _get(session, ContainerType, container_type_id)
    rows = await session.scalars(
        select(DepositPrice)
        .where(DepositPrice.container_type_id == container_type_id)
        .order_by(DepositPrice.valid_from.desc())
    )
    return [_price_view(row) for row in rows]


# Products and prices


async def _prices_at(
    session: AsyncSession, product_ids: Sequence[EntityId], at: datetime
) -> dict[EntityId, Money]:
    rows = await session.scalars(
        select(ProductPrice)
        .where(ProductPrice.product_id.in_(product_ids), ProductPrice.valid_from <= at)
        .order_by(ProductPrice.product_id, ProductPrice.valid_from.desc())
        .ext(distinct_on(ProductPrice.product_id))
    )
    return {
        row.product_id: Money(amount=row.amount, currency=row.currency) for row in rows
    }


def _product_view(product: Product, price: Money | None) -> ProductView:
    container = None
    if product.container_type_id is not None and product.container_quantity:
        container = ContainerLink(
            container_type_id=product.container_type_id,
            quantity=product.container_quantity,
        )
    return ProductView(
        id=product.id,
        sku=product.sku,
        name=product.name,
        barcode=product.barcode,
        brand_id=product.brand_id,
        vat_rate=product.vat_rate,
        container=container,
        active=product.active,
        price=price,
    )


async def _check_container(
    session: AsyncSession, link: ContainerLink, brand_id: EntityId | None
) -> None:
    """Check that a product can be sold in this container type.

    Raises:
        DomainError: The container type is inactive or of another brand.
    """
    container_type = await _get(session, ContainerType, link.container_type_id)
    if not container_type.active:
        msg = f"container type {container_type.name!r} is inactive"
        raise DomainError(msg)
    if container_type.brand_id != brand_id:
        msg = "a product in returnable containers must have the container's brand"
        raise DomainError(msg)


async def create_product(session: AsyncSession, data: ProductCreate) -> ProductView:
    """Add a product, optionally sold in returnable containers.

    Returns:
        The new product, with no price yet.
    """
    if data.brand_id is not None:
        _ = await _get(session, Brand, data.brand_id)
    if data.container is not None:
        await _check_container(session, data.container, data.brand_id)
    product = Product(
        sku=data.sku,
        name=data.name,
        barcode=data.barcode,
        brand_id=data.brand_id,
        vat_rate=data.vat_rate,
        container_type_id=data.container.container_type_id if data.container else None,
        container_quantity=data.container.quantity if data.container else None,
    )
    session.add(product)
    await _flush(session, "the SKU or barcode is already used by another product")
    return _product_view(product, None)


async def get_product(session: AsyncSession, product_id: EntityId) -> ProductView:
    """Look up one product with its current price.

    Returns:
        The product.
    """
    product = await _get(session, Product, product_id)
    prices = await _prices_at(session, [product_id], _now())
    return _product_view(product, prices.get(product_id))


async def list_products(session: AsyncSession) -> list[ProductView]:
    """List every product with its current price.

    Returns:
        The products, ordered by name.
    """
    products = list(await session.scalars(select(Product).order_by(Product.name)))
    prices = await _prices_at(session, [product.id for product in products], _now())
    return [_product_view(product, prices.get(product.id)) for product in products]


async def update_product(
    session: AsyncSession, product_id: EntityId, data: ProductUpdate
) -> ProductView:
    """Change a product's name, barcode, VAT rate or active flag.

    Returns:
        The updated product.
    """
    product = await _get(session, Product, product_id)
    if data.name is not None:
        product.name = data.name
    if "barcode" in data.model_fields_set:
        product.barcode = data.barcode
    if data.vat_rate is not None:
        product.vat_rate = data.vat_rate
    if data.active is not None:
        product.active = data.active
    await _flush(session, "the barcode is already used by another product")
    return await get_product(session, product_id)


async def add_product_price(
    session: AsyncSession, product_id: EntityId, data: PriceCreate
) -> PriceView:
    """Set a new sale price for a product.

    Returns:
        The new history entry.
    """
    _ = await _get(session, Product, product_id)
    row = ProductPrice(
        product_id=product_id,
        amount=data.price.amount,
        currency=data.price.currency,
        valid_from=data.effective_from(_now()),
    )
    session.add(row)
    await _flush(session, "a price already starts at that moment")
    return _price_view(row)


async def price_history(session: AsyncSession, product_id: EntityId) -> list[PriceView]:
    """List a product's prices, newest first.

    Returns:
        The history, including scheduled future changes.
    """
    _ = await _get(session, Product, product_id)
    rows = await session.scalars(
        select(ProductPrice)
        .where(ProductPrice.product_id == product_id)
        .order_by(ProductPrice.valid_from.desc())
    )
    return [_price_view(row) for row in rows]
