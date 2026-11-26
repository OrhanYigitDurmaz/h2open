# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Supplier, receipt and payment logic. Private to this module."""

from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.ids import new_id
from app.core.money import Money
from app.modules.catalog import api as catalog
from app.modules.inventory import api as inventory
from app.modules.purchasing._models import (
    Payment,
    Receipt,
    ReceiptContainer,
    ReceiptLine,
    Supplier,
)
from app.modules.purchasing._views import (
    ContainerFlowView,
    ContainerHolding,
    LineKind,
    PaymentStatus,
    ReceiptLineView,
    ReceiptView,
    SupplierBalanceView,
    SupplierPaymentView,
    SupplierView,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.purchasing._schemas import (
        PaymentCreate,
        PaymentSearch,
        ReceiptCreate,
        ReceiptLineIn,
        ReceiptSearch,
        SupplierCreate,
        SupplierUpdate,
        Void,
    )

HUNDRED = Decimal(100)
CENT = Decimal("0.01")


def _now() -> datetime:
    return datetime.now(UTC)


# Suppliers


def _supplier_view(row: Supplier) -> SupplierView:
    return SupplierView(
        id=row.id,
        name=row.name,
        tax_number=row.tax_number,
        phone=row.phone,
        notes=row.notes,
        active=row.active,
    )


async def _supplier(session: AsyncSession, supplier_id: EntityId) -> Supplier:
    """Load a supplier.

    Returns:
        The supplier.

    Raises:
        NotFoundError: No such supplier.
    """
    row = await session.get(Supplier, supplier_id)
    if row is None:
        msg = f"supplier {supplier_id} not found"
        raise NotFoundError(msg)
    return row


async def _check_name_free(
    session: AsyncSession, name: str, supplier_id: EntityId | None = None
) -> None:
    """Supplier names are unique, ignoring case.

    Raises:
        ConflictError: Another supplier has the name.
    """
    query = select(Supplier.id).where(func.lower(Supplier.name) == name.lower())
    if supplier_id is not None:
        query = query.where(Supplier.id != supplier_id)
    if await session.scalar(query) is not None:
        msg = f"a supplier named {name!r} already exists"
        raise ConflictError(msg)


async def create_supplier(session: AsyncSession, data: SupplierCreate) -> SupplierView:
    """Add a supplier.

    Returns:
        The new supplier.
    """
    await _check_name_free(session, data.name)
    row = Supplier(
        id=new_id(),
        name=data.name,
        tax_number=data.tax_number,
        phone=data.phone,
        notes=data.notes,
        active=True,
    )
    session.add(row)
    await session.flush()
    return _supplier_view(row)


async def list_suppliers(session: AsyncSession) -> list[SupplierView]:
    """List suppliers.

    Returns:
        Every supplier, by name.
    """
    rows = await session.scalars(select(Supplier).order_by(Supplier.name))
    return [_supplier_view(row) for row in rows]


async def get_supplier(session: AsyncSession, supplier_id: EntityId) -> SupplierView:
    """Look up one supplier.

    Returns:
        The supplier.
    """
    return _supplier_view(await _supplier(session, supplier_id))


async def update_supplier(
    session: AsyncSession, supplier_id: EntityId, data: SupplierUpdate
) -> SupplierView:
    """Change a supplier's details.

    Returns:
        The updated supplier.
    """
    row = await _supplier(session, supplier_id)
    if data.name is not None:
        await _check_name_free(session, data.name, supplier_id)
        row.name = data.name
    if "tax_number" in data.model_fields_set:
        row.tax_number = data.tax_number
    if "phone" in data.model_fields_set:
        row.phone = data.phone
    if "notes" in data.model_fields_set:
        row.notes = data.notes
    if data.active is not None:
        row.active = data.active
    await session.flush()
    return _supplier_view(row)


# Receipt views


def _line_view(line: ReceiptLine, currency: str) -> ReceiptLineView:
    total = line.net_amount + line.vat_amount
    return ReceiptLineView(
        id=line.id,
        kind=line.kind,
        product_id=line.product_id,
        container_type_id=line.container_type_id,
        description=line.description,
        quantity=line.quantity,
        net_amount=Money(amount=line.net_amount, currency=currency),
        vat_rate=line.vat_rate,
        vat_amount=Money(amount=line.vat_amount, currency=currency),
        total=Money(amount=total, currency=currency),
        unit_cost=Money(amount=total / line.quantity, currency=currency).rounded(4),
    )


def _flow_view(row: ReceiptContainer) -> ContainerFlowView:
    return ContainerFlowView(
        container_type_id=row.container_type_id,
        full_in=row.full_in,
        empties_out=row.empties_out,
        purchased=row.purchased,
        renewed=row.renewed,
        balance_change=row.full_in - row.empties_out - row.purchased,
    )


def _status(total: Decimal, paid: Decimal) -> PaymentStatus:
    if paid >= total:
        return PaymentStatus.PAID
    if paid == 0:
        return PaymentStatus.UNPAID
    return PaymentStatus.PARTIAL


def _receipt_view(receipt: Receipt, paid: Decimal) -> ReceiptView:
    currency = receipt.currency

    def money(amount: Decimal) -> Money:
        return Money(amount=amount, currency=currency)

    lines = [_line_view(line, currency) for line in receipt.lines]
    return ReceiptView(
        id=receipt.id,
        supplier_id=receipt.supplier_id,
        document_number=receipt.document_number,
        issued_on=receipt.issued_on,
        lines=lines,
        containers=[_flow_view(row) for row in receipt.containers],
        net_total=money(sum((line.net_amount for line in receipt.lines), Decimal(0))),
        vat_total=money(sum((line.vat_amount for line in receipt.lines), Decimal(0))),
        total=money(receipt.total),
        paid=money(paid),
        outstanding=money(max(receipt.total - paid, Decimal(0))),
        payment_status=_status(receipt.total, paid),
        notes=receipt.notes,
        received_at=receipt.received_at,
        recorded_by=receipt.recorded_by,
        voided_at=receipt.voided_at,
        voided_by=receipt.voided_by,
        void_reason=receipt.void_reason,
    )


async def _paid(
    session: AsyncSession, receipt_ids: Iterable[EntityId]
) -> dict[EntityId, Decimal]:
    """How much has been paid against each receipt.

    Returns:
        Paid amounts by receipt; receipts without payments are left out.
    """
    rows = await session.execute(
        select(Payment.receipt_id, func.sum(Payment.amount))
        .where(Payment.receipt_id.in_(list(receipt_ids)))
        .where(Payment.voided_at.is_(None))
        .group_by(Payment.receipt_id)
    )
    return {receipt_id: amount for receipt_id, amount in rows if receipt_id}


async def _view(session: AsyncSession, receipt: Receipt) -> ReceiptView:
    paid = await _paid(session, [receipt.id])
    return _receipt_view(receipt, paid.get(receipt.id, Decimal(0)))


async def _load(
    session: AsyncSession, receipt_id: EntityId, *, lock: bool = False
) -> Receipt:
    """Load a receipt with its lines, fresh from the database.

    Returns:
        The receipt.

    Raises:
        NotFoundError: No such receipt.
    """
    query = (
        select(Receipt)
        .where(Receipt.id == receipt_id)
        .options(selectinload(Receipt.lines), selectinload(Receipt.containers))
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    receipt = await session.scalar(query)
    if receipt is None:
        msg = f"receipt {receipt_id} not found"
        raise NotFoundError(msg)
    return receipt


# Entering a receipt


async def _line(session: AsyncSession, data: ReceiptLineIn) -> ReceiptLine:
    """A receipt line, with names and container details from the catalog.

    Returns:
        The line.
    """
    line = ReceiptLine(
        id=new_id(),
        kind=data.kind,
        quantity=data.quantity,
        net_amount=data.net_amount,
        vat_rate=data.vat_rate,
        vat_amount=(data.net_amount * data.vat_rate / HUNDRED).quantize(
            CENT, ROUND_HALF_UP
        ),
    )
    if data.product_id is not None:
        product = await catalog.get_product(session, data.product_id)
        line.product_id = product.id
        line.description = data.description or product.name
        if product.container is not None:
            line.container_type_id = product.container.container_type_id
            line.container_quantity = product.container.quantity
    elif data.container_type_id is not None:
        container_type = await catalog.get_container_type(
            session, data.container_type_id
        )
        line.container_type_id = container_type.id
        line.description = data.description or container_type.name
    else:
        # Other lines always have a description; the schema checks that.
        line.description = data.description or data.kind.value
    return line


def _check_total(lines: list[ReceiptLine], data: ReceiptCreate) -> None:
    """The lines must add up to the printed total.

    VAT is rounded per line, so a receipt that rounds differently may be
    off by up to a kuruş per line; more than that is a typing mistake.

    Raises:
        DomainError: The lines and the printed total disagree.
    """
    computed = sum((line.net_amount + line.vat_amount for line in lines), Decimal(0))
    if abs(computed - data.total) > CENT * len(lines):
        msg = (
            f"the lines add up to {computed} {data.currency} but the receipt"
            f" total is {data.total}; check the amounts and VAT rates"
        )
        raise DomainError(msg)


def _counts(lines: Iterable[ReceiptLine], kind: LineKind) -> Counter[EntityId]:
    counts: Counter[EntityId] = Counter()
    for line in lines:
        if line.kind is kind and line.container_type_id is not None:
            counts[line.container_type_id] += line.quantity * (
                line.container_quantity or 1
            )
    return counts


async def _flows(
    session: AsyncSession, lines: list[ReceiptLine], data: ReceiptCreate
) -> list[ReceiptContainer]:
    """Work out what happened with each container type.

    Returns:
        One row per container type involved.

    Raises:
        DomainError: More containers bought or renewed than arrived full,
            or more renewed than empties handed over.
    """
    full_in = _counts(lines, LineKind.GOODS)
    purchased = _counts(lines, LineKind.CONTAINER_PURCHASE)
    renewed = _counts(lines, LineKind.CONTAINER_RENEWAL)
    empties_out: Counter[EntityId] = Counter(
        {count.container_type_id: count.quantity for count in data.empties_returned}
    )
    rows: list[ReceiptContainer] = []
    for type_id in sorted(full_in | purchased | renewed | empties_out):
        name = (await catalog.get_container_type(session, type_id)).name
        if purchased[type_id] + renewed[type_id] > full_in[type_id]:
            msg = (
                f"{purchased[type_id] + renewed[type_id]} x {name!r} bought or"
                f" renewed, but only {full_in[type_id]} arrived full"
            )
            raise DomainError(msg)
        if renewed[type_id] > empties_out[type_id]:
            msg = (
                f"{renewed[type_id]} x {name!r} renewed, but only"
                f" {empties_out[type_id]} empties were handed over"
            )
            raise DomainError(msg)
        rows.append(
            ReceiptContainer(
                container_type_id=type_id,
                full_in=full_in[type_id],
                empties_out=empties_out[type_id],
                purchased=purchased[type_id],
                renewed=renewed[type_id],
            )
        )
    return rows


async def _check_not_entered(session: AsyncSession, data: ReceiptCreate) -> None:
    """The same document cannot be entered twice.

    Raises:
        ConflictError: It is already entered and not voided.
    """
    existing = await session.scalar(
        select(Receipt.id)
        .where(Receipt.supplier_id == data.supplier_id)
        .where(Receipt.document_number == data.document_number)
        .where(Receipt.voided_at.is_(None))
    )
    if existing is not None:
        msg = (
            f"receipt {data.document_number!r} from this supplier is already"
            f" entered ({existing}); void it first to enter it again"
        )
        raise ConflictError(msg)


def _stock_changes(receipt: Receipt, sign: int) -> list[inventory.StockChange]:
    """Goods in and empties out for a receipt; ``sign=-1`` reverses them.

    Returns:
        The stock changes.
    """
    changes = [
        inventory.StockChange(
            kind=inventory.ItemKind.PRODUCT,
            item_id=line.product_id,
            change=sign * line.quantity,
        )
        for line in receipt.lines
        if line.product_id is not None
    ]
    changes.extend(
        inventory.StockChange(
            kind=inventory.ItemKind.EMPTY,
            item_id=row.container_type_id,
            change=-sign * row.empties_out,
        )
        for row in receipt.containers
    )
    return changes


async def create_receipt(
    session: AsyncSession, data: ReceiptCreate, actor_id: EntityId
) -> ReceiptView:
    """Enter a supplier's receipt and put its goods into stock.

    Returns:
        The receipt.

    Raises:
        DomainError: The supplier is inactive.
    """
    supplier = await _supplier(session, data.supplier_id)
    if not supplier.active:
        msg = f"supplier {supplier.name!r} is inactive"
        raise DomainError(msg)
    await _check_not_entered(session, data)
    lines = [await _line(session, line) for line in data.lines]
    _check_total(lines, data)
    receipt = Receipt(
        id=new_id(),
        supplier_id=supplier.id,
        document_number=data.document_number,
        issued_on=data.issued_on,
        currency=data.currency,
        total=data.total,
        notes=data.notes,
        received_at=_now(),
        recorded_by=actor_id,
        lines=lines,
        containers=await _flows(session, lines, data),
    )
    session.add(receipt)
    await session.flush()
    _ = await inventory.record(
        session,
        _stock_changes(receipt, 1),
        inventory.Source(
            inventory.MovementReason.PURCHASE,
            actor_id,
            source_id=receipt.id,
            note=f"Receipt {receipt.document_number} from {supplier.name}",
        ),
    )
    return await _view(session, await _load(session, receipt.id))


async def get_receipt(session: AsyncSession, receipt_id: EntityId) -> ReceiptView:
    """Look up one receipt.

    Returns:
        The receipt.
    """
    return await _view(session, await _load(session, receipt_id))


async def list_receipts(
    session: AsyncSession, search: ReceiptSearch
) -> list[ReceiptView]:
    """List receipts, newest first.

    Returns:
        Up to ``search.limit`` receipts.
    """
    query = (
        select(Receipt)
        .options(selectinload(Receipt.lines), selectinload(Receipt.containers))
        .order_by(Receipt.issued_on.desc(), Receipt.id.desc())
        .limit(search.limit)
    )
    if search.supplier_id is not None:
        query = query.where(Receipt.supplier_id == search.supplier_id)
    if not search.include_voided:
        query = query.where(Receipt.voided_at.is_(None))
    receipts = list(await session.scalars(query))
    paid = await _paid(session, [receipt.id for receipt in receipts])
    return [
        _receipt_view(receipt, paid.get(receipt.id, Decimal(0))) for receipt in receipts
    ]


async def void_receipt(
    session: AsyncSession, receipt_id: EntityId, data: Void, actor_id: EntityId
) -> ReceiptView:
    """Void a receipt entered by mistake and take its goods back out of stock.

    Returns:
        The voided receipt.

    Raises:
        ConflictError: It is already voided.
        DomainError: Payments were made against it.
    """
    receipt = await _load(session, receipt_id, lock=True)
    if receipt.voided_at is not None:
        msg = f"receipt {receipt.document_number!r} is already voided"
        raise ConflictError(msg)
    if await _paid(session, [receipt.id]):
        msg = "payments were made against this receipt; void them first"
        raise DomainError(msg)
    receipt.voided_at = _now()
    receipt.voided_by = actor_id
    receipt.void_reason = data.reason
    _ = await inventory.record(
        session,
        _stock_changes(receipt, -1),
        inventory.Source(
            inventory.MovementReason.PURCHASE_VOID,
            actor_id,
            source_id=receipt.id,
            note=data.reason,
        ),
    )
    return await _view(session, receipt)


# Payments


def _payment_view(row: Payment) -> SupplierPaymentView:
    return SupplierPaymentView(
        id=row.id,
        supplier_id=row.supplier_id,
        receipt_id=row.receipt_id,
        amount=Money(amount=row.amount, currency=row.currency),
        method=row.method,
        paid_on=row.paid_on,
        reference=row.reference,
        recorded_at=row.recorded_at,
        recorded_by=row.recorded_by,
        voided_at=row.voided_at,
        voided_by=row.voided_by,
        void_reason=row.void_reason,
    )


async def _check_against(
    session: AsyncSession, data: PaymentCreate, receipt_id: EntityId
) -> None:
    """A payment against a receipt must fit what is still owed on it.

    The receipt stays locked until the transaction ends, so two payments
    at once cannot both fit.

    Raises:
        DomainError: Wrong supplier or currency, voided, or overpaid.
    """
    receipt = await _load(session, receipt_id, lock=True)
    if receipt.supplier_id != data.supplier_id:
        msg = "the receipt is from a different supplier"
        raise DomainError(msg)
    if receipt.voided_at is not None:
        msg = f"receipt {receipt.document_number!r} is voided"
        raise DomainError(msg)
    if receipt.currency != data.currency:
        msg = f"the receipt is in {receipt.currency}, not {data.currency}"
        raise DomainError(msg)
    paid = (await _paid(session, [receipt.id])).get(receipt.id, Decimal(0))
    outstanding = receipt.total - paid
    if data.amount > outstanding:
        msg = (
            f"only {outstanding} {receipt.currency} is outstanding on receipt"
            f" {receipt.document_number!r}"
        )
        raise DomainError(msg)


async def create_payment(
    session: AsyncSession, data: PaymentCreate, actor_id: EntityId
) -> SupplierPaymentView:
    """Record money paid to a supplier.

    Returns:
        The payment.
    """
    _ = await _supplier(session, data.supplier_id)
    if data.receipt_id is not None:
        await _check_against(session, data, data.receipt_id)
    row = Payment(
        id=new_id(),
        supplier_id=data.supplier_id,
        receipt_id=data.receipt_id,
        amount=data.amount,
        currency=data.currency,
        method=data.method,
        paid_on=data.paid_on,
        reference=data.reference,
        recorded_at=_now(),
        recorded_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return _payment_view(row)


async def list_payments(
    session: AsyncSession, search: PaymentSearch
) -> list[SupplierPaymentView]:
    """List payments, newest first.

    Returns:
        Up to ``search.limit`` payments.
    """
    query = (
        select(Payment)
        .order_by(Payment.paid_on.desc(), Payment.id.desc())
        .limit(search.limit)
    )
    if search.supplier_id is not None:
        query = query.where(Payment.supplier_id == search.supplier_id)
    if search.receipt_id is not None:
        query = query.where(Payment.receipt_id == search.receipt_id)
    if not search.include_voided:
        query = query.where(Payment.voided_at.is_(None))
    return [_payment_view(row) for row in await session.scalars(query)]


async def void_payment(
    session: AsyncSession, payment_id: EntityId, data: Void, actor_id: EntityId
) -> SupplierPaymentView:
    """Void a payment entered by mistake.

    Returns:
        The voided payment.

    Raises:
        NotFoundError: No such payment.
        ConflictError: It is already voided.
    """
    row = await session.get(Payment, payment_id)
    if row is None:
        msg = f"payment {payment_id} not found"
        raise NotFoundError(msg)
    if row.voided_at is not None:
        msg = "the payment is already voided"
        raise ConflictError(msg)
    row.voided_at = _now()
    row.voided_by = actor_id
    row.void_reason = data.reason
    await session.flush()
    return _payment_view(row)


# Balances


def _per_currency(
    owed: Mapping[str, Decimal], paid: Mapping[str, Decimal]
) -> list[Money]:
    return [
        Money(
            amount=owed.get(currency, Decimal(0)) - paid.get(currency, Decimal(0)),
            currency=currency,
        )
        for currency in sorted(owed.keys() | paid.keys())
    ]


async def balance(session: AsyncSession, supplier_id: EntityId) -> SupplierBalanceView:
    """What we owe a supplier, and whose containers are where.

    Returns:
        The balance.
    """
    _ = await _supplier(session, supplier_id)
    owed: defaultdict[str, Decimal] = defaultdict(Decimal)
    for currency, total in await session.execute(
        select(Receipt.currency, func.sum(Receipt.total))
        .where(Receipt.supplier_id == supplier_id)
        .where(Receipt.voided_at.is_(None))
        .group_by(Receipt.currency)
    ):
        owed[currency] = total
    paid: defaultdict[str, Decimal] = defaultdict(Decimal)
    for currency, total in await session.execute(
        select(Payment.currency, func.sum(Payment.amount))
        .where(Payment.supplier_id == supplier_id)
        .where(Payment.voided_at.is_(None))
        .group_by(Payment.currency)
    ):
        paid[currency] = total
    held = func.sum(
        ReceiptContainer.full_in
        - ReceiptContainer.empties_out
        - ReceiptContainer.purchased
    )
    containers = [
        ContainerHolding(container_type_id=type_id, quantity=quantity)
        for type_id, quantity in await session.execute(
            select(ReceiptContainer.container_type_id, held)
            .join(Receipt)
            .where(Receipt.supplier_id == supplier_id)
            .where(Receipt.voided_at.is_(None))
            .group_by(ReceiptContainer.container_type_id)
            .having(held != 0)
            .order_by(ReceiptContainer.container_type_id)
        )
    ]
    return SupplierBalanceView(
        supplier_id=supplier_id,
        payable=_per_currency(owed, paid),
        containers=containers,
    )
