# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the purchasing module. Other modules get them via ``api``."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId
from app.core.money import Money


class LineKind(StrEnum):
    """What a line on a supplier's receipt is for."""

    GOODS = "goods"
    """Products that go into stock, e.g. 50 x Brand A 19 L water."""
    CONTAINER_PURCHASE = "container_purchase"
    """New containers bought outright; they arrive full, on a goods line."""
    CONTAINER_RENEWAL = "container_renewal"
    """A fee for swapping an old empty for a new container (arrives full)."""
    OTHER = "other"
    """Anything else on the receipt: transport, pallets, a discount line."""


class SupplierPaymentMethod(StrEnum):
    """How we paid a supplier."""

    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(StrEnum):
    """How much of a receipt is paid."""

    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class SupplierView(_View):
    """Someone we buy from."""

    id: EntityId
    name: str
    tax_number: str | None
    phone: str | None
    notes: str | None
    active: bool


class ReceiptLineView(_View):
    """One line of a receipt, as printed on it."""

    id: EntityId
    kind: LineKind
    product_id: EntityId | None
    container_type_id: EntityId | None
    description: str
    quantity: int
    net_amount: Money
    """The line amount before VAT."""
    vat_rate: Decimal
    vat_amount: Money
    total: Money
    """Net plus VAT."""
    unit_cost: Money
    """What one unit cost us, VAT included."""


class ContainerFlowView(_View):
    """What happened with one container type on a receipt."""

    container_type_id: EntityId
    full_in: int
    """Full containers received on goods lines."""
    empties_out: int
    """Empties handed to the supplier, including the old ones renewed."""
    purchased: int
    """Containers bought outright (ours now)."""
    renewed: int
    """Old containers swapped for new ones for a fee."""
    balance_change: int
    """How many more of the supplier's containers we hold afterwards."""


class ReceiptView(_View):
    """A supplier's official receipt (invoice) as entered."""

    id: EntityId
    supplier_id: EntityId
    document_number: str
    issued_on: date
    lines: list[ReceiptLineView]
    containers: list[ContainerFlowView]
    net_total: Money
    vat_total: Money
    total: Money
    """The total printed on the receipt; what we owe."""
    paid: Money
    outstanding: Money
    payment_status: PaymentStatus
    notes: str | None
    received_at: datetime
    recorded_by: EntityId
    voided_at: datetime | None
    voided_by: EntityId | None
    void_reason: str | None


class SupplierPaymentView(_View):
    """Money we paid a supplier."""

    id: EntityId
    supplier_id: EntityId
    receipt_id: EntityId | None
    """The receipt it pays, if it was for one in particular."""
    amount: Money
    method: SupplierPaymentMethod
    paid_on: date
    reference: str | None
    recorded_at: datetime
    recorded_by: EntityId
    voided_at: datetime | None
    voided_by: EntityId | None
    void_reason: str | None


class ContainerHolding(_View):
    """Containers of one type held between us and a supplier."""

    container_type_id: EntityId
    quantity: int
    """Positive: we hold that many of the supplier's containers.
    Negative: the supplier holds that many of ours."""


class SupplierBalanceView(_View):
    """Where we stand with a supplier."""

    supplier_id: EntityId
    payable: list[Money]
    """What we still owe, one entry per currency; negative if we overpaid."""
    containers: list[ContainerHolding]
