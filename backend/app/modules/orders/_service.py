# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Order logic. Private to this module."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, NoReturn

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core import outbox
from app.core.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.ids import new_id
from app.core.money import Money
from app.modules.accounts import api as accounts
from app.modules.catalog import api as catalog
from app.modules.company import api as company
from app.modules.containers import api as containers
from app.modules.customers import api as customers
from app.modules.identity import api as identity
from app.modules.inventory import api as inventory
from app.modules.orders._events import (
    DeliveryClaimed,
    DeliveryReturnedToPool,
    OrderCancelled,
    OrderChanged,
    OrderCompleted,
    OrderEvent,
    OrderPlaced,
)
from app.modules.orders._models import ClaimEvent, Order, OrderLine, OrderReturn
from app.modules.orders._views import (
    ClaimAction,
    ClaimEventView,
    ContainerReturnView,
    DeliveryAddressView,
    Fulfilment,
    OrderAlerts,
    OrderLineView,
    OrderStatus,
    OrderView,
    PaymentMethod,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.orders._schemas import (
        LineIn,
        OrderCancel,
        OrderCompletion,
        OrderCreate,
        OrderSearch,
        OrderUpdate,
        Release,
        TakeBack,
    )

HUNDRED = Decimal(100)


def _now() -> datetime:
    return datetime.now(UTC)


def _sum(values: Iterable[Money | None]) -> Money | None:
    total: Money | None = None
    for value in values:
        if value is not None:
            total = value if total is None else total + value
    return total


# Views


def _line_view(line: OrderLine) -> OrderLineView:
    quantity = (
        line.ordered_quantity
        if line.delivered_quantity is None
        else line.delivered_quantity
    )
    total = (Money(amount=line.unit_price, currency=line.currency) * quantity).rounded()
    vat = Money(
        amount=total.amount * line.vat_rate / (HUNDRED + line.vat_rate),
        currency=total.currency,
    ).rounded()
    return OrderLineView(
        id=line.id,
        product_id=line.product_id,
        sku=line.sku,
        name=line.name,
        unit_price=Money(amount=line.unit_price, currency=line.currency),
        vat_rate=line.vat_rate,
        container_type_id=line.container_type_id,
        container_quantity=line.container_quantity,
        ordered_quantity=line.ordered_quantity,
        delivered_quantity=line.delivered_quantity,
        total=total,
        vat=vat,
    )


def _deposit(order: Order, amount: Decimal | None) -> Money | None:
    if amount is None or order.deposit_currency is None:
        return None
    return Money(amount=amount, currency=order.deposit_currency)


def _address_view(order: Order) -> DeliveryAddressView | None:
    if order.address is None:
        return None
    return DeliveryAddressView(
        address_id=order.address_id,
        address=order.address,
        directions=order.directions,
        latitude=order.latitude,
        longitude=order.longitude,
    )


def _order_view(order: Order) -> OrderView:
    lines = [_line_view(line) for line in order.lines]
    goods = _sum(line.total for line in lines)
    charged = _deposit(order, order.deposit_charged)
    refunded = _deposit(order, order.deposit_refunded)
    return OrderView(
        id=order.id,
        number=order.number,
        customer_id=order.customer_id,
        channel=order.channel,
        fulfilment=order.fulfilment,
        status=order.status,
        payment_method=order.payment_method,
        address=_address_view(order),
        notes=order.notes,
        lines=lines,
        returns=[
            ContainerReturnView(
                container_type_id=row.container_type_id,
                expected_quantity=row.expected_quantity,
                returned_quantity=row.returned_quantity,
            )
            for row in order.returns
        ],
        goods_total=goods,
        vat_total=_sum(line.vat for line in lines),
        deposit_charged=charged,
        deposit_refunded=refunded,
        total=_sum([goods, charged, None if refunded is None else refunded * -1]),
        override_reason=order.override_reason,
        exchange_id=order.exchange_id,
        created_at=order.created_at,
        created_by=order.created_by,
        completed_at=order.completed_at,
        completed_by=order.completed_by,
        cancelled_at=order.cancelled_at,
        cancelled_by=order.cancelled_by,
        cancel_reason=order.cancel_reason,
        claimed_by=order.claimed_by,
        claimed_at=order.claimed_at,
        waiting_since=order.pooled_at,
    )


# Loading


async def _load(
    session: AsyncSession, order_id: EntityId, *, lock: bool = False
) -> Order:
    """Load an order with its lines and returns, fresh from the database.

    Args:
        session: The caller's database session.
        order_id: The order.
        lock: Lock the order's row until the transaction ends.

    Returns:
        The order.

    Raises:
        NotFoundError: No such order.
    """
    query = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.lines), selectinload(Order.returns))
        .execution_options(populate_existing=True)
    )
    order = await session.scalar(query.with_for_update(of=Order) if lock else query)
    if order is None:
        msg = f"order {order_id} not found"
        raise NotFoundError(msg)
    return order


async def _load_open(session: AsyncSession, order_id: EntityId) -> Order:
    """Load an order that can still change, and lock it.

    The lock lasts until the transaction ends, so two requests changing the
    same order (say, a double-tapped "complete") take turns, and the second
    sees what the first did instead of completing the order again.

    Returns:
        The order.

    Raises:
        ConflictError: The order is already completed or cancelled.
    """
    order = await _load(session, order_id, lock=True)
    if order.status is not OrderStatus.OPEN:
        msg = f"order #{order.number} is {order.status.value} and cannot change"
        raise ConflictError(msg)
    return order


async def _save(session: AsyncSession, order: Order) -> OrderView:
    await session.flush()
    return _order_view(await _load(session, order.id))


async def _announce(
    session: AsyncSession,
    order: Order,
    event_class: type[OrderEvent],
    actor_id: EntityId,
) -> OrderView:
    """Write the order and announce what happened to it, via the outbox.

    Returns:
        The order as stored.
    """
    await session.flush()
    event = event_class(
        order_id=order.id,
        number=order.number,
        fulfilment=order.fulfilment,
        claimed_by=order.claimed_by,
        actor_id=actor_id,
    )
    await outbox.publish(session, event)
    return _order_view(await _load(session, order.id))


# Rules shared by create, update and complete


async def _customer(
    session: AsyncSession, customer_id: EntityId | None
) -> customers.CustomerView | None:
    """Check who the order is for.

    Returns:
        The customer, or ``None`` for a walk-in.

    Raises:
        DomainError: Walk-ins are disabled, or the customer is inactive.
    """
    if customer_id is None:
        settings = await company.get_settings(session)
        if not settings.walk_in_sales_enabled:
            msg = "walk-in sales are disabled; choose or register a customer"
            raise DomainError(msg)
        return None
    customer = await customers.get_customer(session, customer_id)
    if not customer.active:
        msg = f"customer {customer.name!r} is inactive"
        raise DomainError(msg)
    return customer


def _check_payment(customer_id: EntityId | None, method: PaymentMethod) -> None:
    """On-account sales need someone to send the bill to.

    Raises:
        DomainError: An on-account sale without a customer.
    """
    if customer_id is None and method is PaymentMethod.ON_ACCOUNT:
        msg = "on-account (veresiye) sales need a registered customer"
        raise DomainError(msg)


def _set_address(
    order: Order, customer: customers.CustomerView | None, address_id: EntityId
) -> None:
    """Copy one of the customer's addresses onto the order.

    Raises:
        NotFoundError: The customer has no such address.
    """
    addresses = [] if customer is None else customer.addresses
    for address in addresses:
        if address.id == address_id:
            order.address_id = address.id
            order.address = address.address
            order.directions = address.directions
            order.latitude = address.latitude
            order.longitude = address.longitude
            return
    msg = f"the customer has no address {address_id}"
    raise NotFoundError(msg)


async def _new_line(
    session: AsyncSession, product_id: EntityId, ordered: int, delivered: int | None
) -> OrderLine:
    """A line for a product at today's price.

    Returns:
        The line.

    Raises:
        DomainError: The product is inactive or has no price.
    """
    product = await catalog.get_product(session, product_id)
    if not product.active or product.price is None:
        msg = f"{product.name!r} is not for sale (inactive or no price)"
        raise DomainError(msg)
    return OrderLine(
        id=new_id(),
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        unit_price=product.price.amount,
        currency=product.price.currency,
        vat_rate=product.vat_rate,
        container_type_id=None
        if product.container is None
        else product.container.container_type_id,
        container_quantity=None
        if product.container is None
        else product.container.quantity,
        ordered_quantity=ordered,
        delivered_quantity=delivered,
    )


async def _set_lines(session: AsyncSession, order: Order, lines: list[LineIn]) -> None:
    order.lines.clear()
    for line in lines:
        order.lines.append(
            await _new_line(session, line.product_id, line.quantity, None)
        )


def _containers(lines: Iterable[OrderLine], *, delivered: bool) -> Counter[EntityId]:
    """Returnable containers in the lines, by type.

    Returns:
        Containers per type, for ordered or delivered quantities.
    """
    counts: Counter[EntityId] = Counter()
    for line in lines:
        if line.container_type_id is not None and line.container_quantity:
            quantity = line.delivered_quantity if delivered else line.ordered_quantity
            counts[line.container_type_id] += (quantity or 0) * line.container_quantity
    return counts


def _set_expected_returns(
    order: Order, explicit: list[containers.ContainerCount] | None
) -> None:
    expected: Mapping[EntityId, int] = (
        _containers(order.lines, delivered=False)
        if explicit is None
        else {count.container_type_id: count.quantity for count in explicit}
    )
    # Update rows in place: deleting and re-inserting a type would clash
    # with the one-row-per-type constraint, since inserts are flushed first.
    remaining = {
        type_id: quantity for type_id, quantity in expected.items() if quantity
    }
    for row in list(order.returns):
        if row.container_type_id in remaining:
            row.expected_quantity = remaining.pop(row.container_type_id)
        else:
            order.returns.remove(row)
    order.returns.extend(
        OrderReturn(id=new_id(), container_type_id=type_id, expected_quantity=quantity)
        for type_id, quantity in sorted(remaining.items())
    )


# Create, read, update, cancel


async def create_order(
    session: AsyncSession, data: OrderCreate, actor_id: EntityId
) -> OrderView:
    """Take a new order, recording who took it.

    Returns:
        The open order.
    """
    customer = await _customer(session, data.customer_id)
    _check_payment(data.customer_id, data.payment_method)
    order = Order(
        id=new_id(),
        customer_id=data.customer_id,
        channel=data.channel,
        fulfilment=data.fulfilment,
        status=OrderStatus.OPEN,
        payment_method=data.payment_method,
        notes=data.notes,
        created_at=_now(),
        created_by=actor_id,
    )
    if data.fulfilment is Fulfilment.DELIVERY:
        order.pooled_at = order.created_at
    if data.address_id is not None:
        _set_address(order, customer, data.address_id)
    await _set_lines(session, order, data.lines)
    _set_expected_returns(order, data.expected_returns)
    session.add(order)
    return await _announce(session, order, OrderPlaced, actor_id)


async def get_order(session: AsyncSession, order_id: EntityId) -> OrderView:
    """Look up one order.

    Returns:
        The order.
    """
    return _order_view(await _load(session, order_id))


async def list_orders(session: AsyncSession, search: OrderSearch) -> list[OrderView]:
    """List orders, newest first.

    Returns:
        Up to ``search.limit`` orders.
    """
    query = (
        select(Order)
        .options(selectinload(Order.lines), selectinload(Order.returns))
        .order_by(Order.number.desc())
        .limit(search.limit)
    )
    if search.status is not None:
        query = query.where(Order.status == search.status)
    if search.fulfilment is not None:
        query = query.where(Order.fulfilment == search.fulfilment)
    if search.customer_id is not None:
        query = query.where(Order.customer_id == search.customer_id)
    if search.claimed_by is not None:
        query = query.where(Order.claimed_by == search.claimed_by)
    return [_order_view(order) for order in await session.scalars(query)]


async def update_order(
    session: AsyncSession, order_id: EntityId, data: OrderUpdate, actor_id: EntityId
) -> OrderView:
    """Change an open order.

    Returns:
        The updated order.

    Raises:
        DomainError: Pickup orders have no address to change.
    """
    order = await _load_open(session, order_id)
    if data.lines is not None:
        await _set_lines(session, order, data.lines)
    if data.lines is not None or data.expected_returns is not None:
        _set_expected_returns(order, data.expected_returns)
    if data.payment_method is not None:
        _check_payment(order.customer_id, data.payment_method)
        order.payment_method = data.payment_method
    if data.address_id is not None:
        if order.fulfilment is not Fulfilment.DELIVERY:
            msg = "pickup orders have no delivery address"
            raise DomainError(msg)
        _set_address(
            order, await _customer(session, order.customer_id), data.address_id
        )
    if "notes" in data.model_fields_set:
        order.notes = data.notes
    return await _announce(session, order, OrderChanged, actor_id)


async def cancel_order(
    session: AsyncSession, order_id: EntityId, data: OrderCancel, actor_id: EntityId
) -> OrderView:
    """Cancel an open order, recording who did it.

    Returns:
        The cancelled order.
    """
    order = await _load_open(session, order_id)
    order.status = OrderStatus.CANCELLED
    order.pooled_at = None
    order.cancelled_at = _now()
    order.cancel_reason = data.reason
    order.cancelled_by = actor_id
    return await _announce(session, order, OrderCancelled, actor_id)


# Completion


async def _apply_delivered(
    session: AsyncSession, order: Order, lines: list[LineIn]
) -> None:
    """Record what was actually delivered; new products get today's price."""
    delivered = {line.product_id: line.quantity for line in lines}
    for line in order.lines:
        line.delivered_quantity = delivered.pop(line.product_id, 0)
    for product_id, quantity in delivered.items():
        order.lines.append(await _new_line(session, product_id, 0, quantity))


def _apply_returned(
    order: Order, returned: list[containers.ContainerCount] | None
) -> Counter[EntityId]:
    """Record the empties that came back.

    Returns:
        Returned empties per container type.
    """
    actual: Counter[EntityId] = Counter(
        {row.container_type_id: row.expected_quantity for row in order.returns}
        if returned is None
        else {count.container_type_id: count.quantity for count in returned}
    )
    for row in order.returns:
        row.returned_quantity = actual[row.container_type_id]
    expected = {row.container_type_id for row in order.returns}
    order.returns.extend(
        OrderReturn(
            id=new_id(),
            container_type_id=type_id,
            expected_quantity=0,
            returned_quantity=quantity,
        )
        for type_id, quantity in sorted(actual.items())
        if type_id not in expected
    )
    return actual


def _counts(counter: Counter[EntityId]) -> list[containers.ContainerCount]:
    return [
        containers.ContainerCount(container_type_id=type_id, quantity=quantity)
        for type_id, quantity in sorted(counter.items())
        if quantity
    ]


async def _exchange_containers(
    session: AsyncSession,
    order: Order,
    returned: Counter[EntityId],
    actor_id: EntityId,
) -> None:
    """Hand the container side of the order to the containers module."""
    delivered = _counts(_containers(order.lines, delivered=True))
    back = _counts(returned)
    if not delivered and not back:
        return
    result = await containers.exchange(
        session,
        containers.ExchangeCreate(
            customer_id=order.customer_id,
            delivered=delivered,
            returned=back,
            override_reason=order.override_reason,
            note=f"Order #{order.number}",
        ),
        actor_id,
    )
    order.exchange_id = result.exchange_id
    for money in (result.deposit_charged, result.deposit_refunded):
        if money is not None:
            order.deposit_currency = money.currency
    order.deposit_charged = _amount(result.deposit_charged)
    order.deposit_refunded = _amount(result.deposit_refunded)


def _amount(money: Money | None) -> Decimal | None:
    return None if money is None else money.amount


async def _take_from_stock(
    session: AsyncSession, order: Order, actor_id: EntityId
) -> None:
    """Take the delivered goods out of stock."""
    _ = await inventory.record(
        session,
        [
            inventory.StockChange(
                kind=inventory.ItemKind.PRODUCT,
                item_id=line.product_id,
                change=-(line.delivered_quantity or 0),
            )
            for line in order.lines
        ],
        inventory.Source(
            inventory.MovementReason.SALE,
            actor_id,
            source_id=order.id,
            note=f"Order #{order.number}",
        ),
    )


async def _charge_account(
    session: AsyncSession, order: Order, data: OrderCompletion, actor_id: EntityId
) -> None:
    """Put an on-account order's total on the customer's account."""
    if (
        order.payment_method is not PaymentMethod.ON_ACCOUNT
        or order.customer_id is None
    ):
        return
    charge = accounts.OrderCharge(
        customer_id=order.customer_id,
        order_id=order.id,
        total=_order_view(order).total,
        override_reason=data.credit_override_reason,
    )
    _ = await accounts.charge(session, charge, actor_id)


async def complete_order(
    session: AsyncSession, order_id: EntityId, data: OrderCompletion, actor_id: EntityId
) -> OrderView:
    """Record what was handed over and finalise the order, by ``actor_id``.

    Returns:
        The completed order with final totals.

    Raises:
        DomainError: Nothing was delivered or returned.
    """
    order = await _load_open(session, order_id)
    if data.payment_method is not None:
        _check_payment(order.customer_id, data.payment_method)
        order.payment_method = data.payment_method
    if data.lines is None:
        for line in order.lines:
            line.delivered_quantity = line.ordered_quantity
    else:
        await _apply_delivered(session, order, data.lines)
    returned = _apply_returned(order, data.returned)
    if not any(line.delivered_quantity for line in order.lines) and not any(
        returned.values()
    ):
        msg = "nothing was delivered or returned; cancel the order instead"
        raise DomainError(msg)
    order.override_reason = data.override_reason
    await _exchange_containers(session, order, returned, actor_id)
    await _take_from_stock(session, order, actor_id)
    await _charge_account(session, order, data, actor_id)
    order.completed_by = actor_id
    order.pooled_at = None
    order.status = OrderStatus.COMPLETED
    order.completed_at = _now()
    return await _announce(session, order, OrderCompleted, actor_id)


def _is_staff(actor: identity.Actor) -> bool:
    return actor.has(identity.Role.STAFF) or actor.has(identity.Role.ADMIN)


async def complete_as(
    session: AsyncSession,
    order_id: EntityId,
    data: OrderCompletion,
    actor: identity.Actor,
) -> OrderView:
    """Complete an order on behalf of a logged-in user.

    Staff complete any order; a driver only the deliveries they hold.

    Returns:
        The completed order.

    Raises:
        PermissionDeniedError: A driver completing an order they don't hold.
    """
    if not _is_staff(actor):
        order = await _load_open(session, order_id)
        if order.claimed_by != actor.id:
            msg = f"claim order #{order.number} before completing it"
            raise PermissionDeniedError(msg)
    return await complete_order(session, order_id, data, actor.id)


# The delivery pool


def _event(
    order: Order, action: ClaimAction, driver_id: EntityId, actor_id: EntityId
) -> ClaimEvent:
    return ClaimEvent(
        id=new_id(),
        order_id=order.id,
        action=action,
        driver_id=driver_id,
        recorded_by=actor_id,
        occurred_at=_now(),
    )


async def _why_not_claimed(
    session: AsyncSession, order_id: EntityId, actor: identity.Actor
) -> NoReturn:
    """Explain why a claim found nothing to take.

    Raises:
        DomainError: The order is a pickup.
        ConflictError: Someone already holds it.
    """
    order = await _load_open(session, order_id)
    if order.fulfilment is not Fulfilment.DELIVERY:
        msg = f"order #{order.number} is a pickup, not a delivery"
        raise DomainError(msg)
    who = "you" if order.claimed_by == actor.id else "another driver"
    msg = f"order #{order.number} is already held by {who}"
    raise ConflictError(msg)


async def claim(
    session: AsyncSession, order_id: EntityId, actor: identity.Actor
) -> OrderView:
    """Take a delivery from the pool.

    The order is taken with one conditional update, so when two drivers
    tap the same order at once exactly one gets it.

    Returns:
        The order, now held by the driver.

    Raises:
        PermissionDeniedError: Not a driver.
        DomainError: The driver is not on shift.
    """
    if not actor.has(identity.Role.DRIVER):
        msg = "only drivers claim deliveries"
        raise PermissionDeniedError(msg)
    if not actor.user.on_shift:
        msg = "start your shift to claim deliveries"
        raise DomainError(msg)
    taken = await session.scalar(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == OrderStatus.OPEN,
            Order.fulfilment == Fulfilment.DELIVERY,
            Order.claimed_by.is_(None),
        )
        .values(claimed_by=actor.id, claimed_at=_now(), pooled_at=None)
        .returning(Order.id)
    )
    if taken is None:
        await _why_not_claimed(session, order_id, actor)
    order = await _load(session, order_id)
    session.add(_event(order, ClaimAction.CLAIMED, actor.id, actor.id))
    return await _announce(session, order, DeliveryClaimed, actor.id)


async def _return_to_pool(
    session: AsyncSession, order: Order, event: ClaimEvent
) -> OrderView:
    """Put a held delivery back in the pool and announce it.

    Returns:
        The order, back in the pool.
    """
    session.add(event)
    order.claimed_by = None
    order.claimed_at = None
    order.pooled_at = _now()
    await session.flush()
    await outbox.publish(
        session,
        DeliveryReturnedToPool(
            order_id=order.id,
            number=order.number,
            fulfilment=order.fulfilment,
            claimed_by=None,
            actor_id=event.recorded_by,
            previous_driver=event.driver_id,
            taken_back=event.action is ClaimAction.TAKEN_BACK,
            reason=event.reason,
        ),
    )
    return await _save(session, order)


async def release(
    session: AsyncSession, order_id: EntityId, data: Release, actor: identity.Actor
) -> OrderView:
    """A driver puts a delivery they hold back in the pool.

    Returns:
        The order, back in the pool.

    Raises:
        PermissionDeniedError: The driver does not hold it.
    """
    order = await _load_open(session, order_id)
    if order.claimed_by != actor.id:
        msg = f"you don't hold order #{order.number}"
        raise PermissionDeniedError(msg)
    event = _event(order, ClaimAction.RELEASED, actor.id, actor.id)
    event.reason = data.reason
    return await _return_to_pool(session, order, event)


async def take_back(
    session: AsyncSession, order_id: EntityId, data: TakeBack, actor: identity.Actor
) -> OrderView:
    """Staff take a delivery away from its driver, back into the pool.

    Returns:
        The order, back in the pool.

    Raises:
        PermissionDeniedError: Not staff.
        DomainError: No driver holds it.
    """
    if not _is_staff(actor):
        msg = "only staff can take deliveries back from drivers"
        raise PermissionDeniedError(msg)
    order = await _load_open(session, order_id)
    if order.claimed_by is None:
        msg = f"no driver holds order #{order.number}"
        raise DomainError(msg)
    event = _event(order, ClaimAction.TAKEN_BACK, order.claimed_by, actor.id)
    event.reason = data.reason
    return await _return_to_pool(session, order, event)


def _open_deliveries() -> Select[Order]:
    return (
        select(Order)
        .options(selectinload(Order.lines), selectinload(Order.returns))
        .where(
            Order.status == OrderStatus.OPEN,
            Order.fulfilment == Fulfilment.DELIVERY,
        )
    )


async def pool(session: AsyncSession) -> list[OrderView]:
    """Deliveries waiting for a driver, longest-waiting first.

    Returns:
        The orders.
    """
    query = (
        _open_deliveries()
        .where(Order.claimed_by.is_(None))
        .order_by(Order.pooled_at, Order.number)
    )
    return [_order_view(order) for order in await session.scalars(query)]


async def held(session: AsyncSession, driver_id: EntityId) -> list[OrderView]:
    """Deliveries a driver holds, in the order they were claimed.

    Returns:
        The orders.
    """
    query = (
        _open_deliveries()
        .where(Order.claimed_by == driver_id)
        .order_by(Order.claimed_at, Order.number)
    )
    return [_order_view(order) for order in await session.scalars(query)]


async def claim_history(
    session: AsyncSession, order_id: EntityId
) -> list[ClaimEventView]:
    """Who has held a delivery, oldest first.

    Returns:
        The claim events.
    """
    _ = await _load(session, order_id)
    rows = await session.scalars(
        select(ClaimEvent)
        .where(ClaimEvent.order_id == order_id)
        .order_by(ClaimEvent.id)
    )
    return [
        ClaimEventView(
            id=row.id,
            order_id=row.order_id,
            action=row.action,
            driver_id=row.driver_id,
            recorded_by=row.recorded_by,
            reason=row.reason,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]


async def alerts(session: AsyncSession) -> OrderAlerts:
    """Deliveries waiting or held too long, per the company settings.

    Returns:
        The late deliveries, longest-waiting first.
    """
    settings = await company.get_settings(session)
    now = _now()
    unclaimed = (
        _open_deliveries()
        .where(
            Order.claimed_by.is_(None),
            Order.pooled_at
            <= now - timedelta(minutes=settings.unclaimed_alert_minutes),
        )
        .order_by(Order.pooled_at, Order.number)
    )
    uncompleted = (
        _open_deliveries()
        .where(
            Order.claimed_at
            <= now - timedelta(minutes=settings.uncompleted_alert_minutes),
        )
        .order_by(Order.claimed_at, Order.number)
    )
    return OrderAlerts(
        unclaimed=[_order_view(o) for o in await session.scalars(unclaimed)],
        uncompleted=[_order_view(o) for o in await session.scalars(uncompleted)],
    )
