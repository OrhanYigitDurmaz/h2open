# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the company endpoints. Private to this module."""

from typing import Annotated

from pydantic import BaseModel, Field

from app.modules.company._views import DepositRefundPolicy


class SettingsUpdate(BaseModel):
    """Changes to the settings; omitted fields stay as they are."""

    deposit_refund_policy: DepositRefundPolicy | None = None
    walk_in_sales_enabled: bool | None = None
    walk_in_deposits_allowed: bool | None = None
    negative_stock_allowed: bool | None = None
    unclaimed_alert_minutes: Annotated[int, Field(ge=1, le=1440)] | None = None
    uncompleted_alert_minutes: Annotated[int, Field(ge=1, le=1440)] | None = None
