# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the purchasing module. Private to this module."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.identity import api as identity
from app.modules.purchasing import _service
from app.modules.purchasing._schemas import (
    PaymentCreate,
    PaymentSearch,
    ReceiptCreate,
    ReceiptSearch,
    SupplierCreate,
    SupplierUpdate,
    Void,
)
from app.modules.purchasing._views import (
    ReceiptView,
    SupplierBalanceView,
    SupplierPaymentView,
    SupplierView,
)

router = APIRouter(
    prefix="/purchasing",
    tags=["purchasing"],
    dependencies=[Depends(identity.current_actor)],
)
ADMIN = [Depends(identity.admin_actor)]
"""Managing suppliers is for admins; everyone logged in can read them."""


@router.post("/suppliers", status_code=HTTPStatus.CREATED, dependencies=ADMIN)
async def create_supplier(session: SessionDep, data: SupplierCreate) -> SupplierView:
    """Add a supplier.

    Returns:
        The new supplier.
    """
    return await _service.create_supplier(session, data)


@router.get("/suppliers")
async def list_suppliers(session: SessionDep) -> list[SupplierView]:
    """List suppliers.

    Returns:
        Every supplier, by name.
    """
    return await _service.list_suppliers(session)


@router.get("/suppliers/{supplier_id}")
async def get_supplier(session: SessionDep, supplier_id: EntityId) -> SupplierView:
    """Get one supplier.

    Returns:
        The supplier.
    """
    return await _service.get_supplier(session, supplier_id)


@router.patch("/suppliers/{supplier_id}", dependencies=ADMIN)
async def update_supplier(
    session: SessionDep, supplier_id: EntityId, data: SupplierUpdate
) -> SupplierView:
    """Change a supplier's details or (de)activate it.

    Returns:
        The updated supplier.
    """
    return await _service.update_supplier(session, supplier_id, data)


@router.get("/suppliers/{supplier_id}/balance")
async def supplier_balance(
    session: SessionDep, supplier_id: EntityId
) -> SupplierBalanceView:
    """What we owe a supplier, and whose containers are where.

    Returns:
        The balance.
    """
    return await _service.balance(session, supplier_id)


@router.post("/receipts", status_code=HTTPStatus.CREATED)
async def create_receipt(
    session: SessionDep, actor: identity.CurrentActor, data: ReceiptCreate
) -> ReceiptView:
    """Enter a supplier's official receipt; its goods go into stock.

    Returns:
        The receipt. A 422 means the lines don't add up to the printed total
        or the container counts don't fit together.
    """
    return await _service.create_receipt(session, data, actor.id)


@router.get("/receipts")
async def list_receipts(
    session: SessionDep, search: Annotated[ReceiptSearch, Query()]
) -> list[ReceiptView]:
    """List receipts, newest first, optionally filtered.

    Returns:
        The matching receipts.
    """
    return await _service.list_receipts(session, search)


@router.get("/receipts/{receipt_id}")
async def get_receipt(session: SessionDep, receipt_id: EntityId) -> ReceiptView:
    """Get one receipt.

    Returns:
        The receipt.
    """
    return await _service.get_receipt(session, receipt_id)


@router.post("/receipts/{receipt_id}/void")
async def void_receipt(
    session: SessionDep, actor: identity.AdminActor, receipt_id: EntityId, data: Void
) -> ReceiptView:
    """Void a receipt entered by mistake; its stock moves are reversed. Admins only.

    Returns:
        The voided receipt.
    """
    return await _service.void_receipt(session, receipt_id, data, actor.id)


@router.post("/payments", status_code=HTTPStatus.CREATED)
async def create_payment(
    session: SessionDep, actor: identity.CurrentActor, data: PaymentCreate
) -> SupplierPaymentView:
    """Record money paid to a supplier, optionally against one receipt.

    Returns:
        The payment.
    """
    return await _service.create_payment(session, data, actor.id)


@router.get("/payments")
async def list_payments(
    session: SessionDep, search: Annotated[PaymentSearch, Query()]
) -> list[SupplierPaymentView]:
    """List payments, newest first, optionally filtered.

    Returns:
        The matching payments.
    """
    return await _service.list_payments(session, search)


@router.post("/payments/{payment_id}/void")
async def void_payment(
    session: SessionDep, actor: identity.AdminActor, payment_id: EntityId, data: Void
) -> SupplierPaymentView:
    """Void a payment entered by mistake. Admins only.

    Returns:
        The voided payment.
    """
    return await _service.void_payment(session, payment_id, data, actor.id)
