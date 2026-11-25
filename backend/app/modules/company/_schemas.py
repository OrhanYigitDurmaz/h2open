# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the company endpoints. Private to this module."""

from pydantic import BaseModel

from app.modules.company._views import DepositRefundPolicy


class SettingsUpdate(BaseModel):
    """Changes to the settings; omitted fields stay as they are."""

    deposit_refund_policy: DepositRefundPolicy | None = None
    walk_in_sales_enabled: bool | None = None
    walk_in_deposits_allowed: bool | None = None
