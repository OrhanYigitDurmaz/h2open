# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the company module. Other modules get them via ``api``."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class DepositRefundPolicy(StrEnum):
    """How much deposit a customer gets back when returning a container for good."""

    PAID_AMOUNT = "paid_amount"
    """What the customer paid for that container (oldest deposit first)."""
    CURRENT_PRICE = "current_price"
    """Today's deposit price for the container type."""
    NONE = "none"
    """Nothing; deposits are not refunded."""


class SettingsView(BaseModel):
    """Company-wide settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    deposit_refund_policy: DepositRefundPolicy
    walk_in_sales_enabled: bool
    """Whether orders without a registered customer are allowed."""
    walk_in_deposits_allowed: bool
    """Whether walk-in customers may take new containers by paying a deposit.

    Their deposits cannot be refunded later, since nobody's balance records
    them. Same-brand swaps are always allowed for walk-ins.
    """
    negative_stock_allowed: bool
    """Whether stock may go below zero.

    When allowed, sales never wait for paperwork: a negative level just
    shows that a receipt or a count is missing. When not, a sale or other
    removal that would go below zero is refused.
    """
