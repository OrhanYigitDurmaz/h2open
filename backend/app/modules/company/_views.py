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
