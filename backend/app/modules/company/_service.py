# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Company settings logic. Private to this module."""

from typing import TYPE_CHECKING

from app.modules.company._models import SETTINGS_ROW_ID, Settings
from app.modules.company._views import DepositRefundPolicy, SettingsView

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.company._schemas import SettingsUpdate

DEFAULTS = SettingsView(
    deposit_refund_policy=DepositRefundPolicy.PAID_AMOUNT,
    walk_in_sales_enabled=True,
    walk_in_deposits_allowed=False,
    negative_stock_allowed=True,
    unclaimed_alert_minutes=15,
    uncompleted_alert_minutes=120,
)


def _view(row: Settings | None) -> SettingsView:
    if row is None:
        return DEFAULTS
    return SettingsView(
        deposit_refund_policy=row.deposit_refund_policy,
        walk_in_sales_enabled=row.walk_in_sales_enabled,
        walk_in_deposits_allowed=row.walk_in_deposits_allowed,
        negative_stock_allowed=row.negative_stock_allowed,
        unclaimed_alert_minutes=row.unclaimed_alert_minutes,
        uncompleted_alert_minutes=row.uncompleted_alert_minutes,
    )


async def get_settings(session: AsyncSession) -> SettingsView:
    """Read the settings, falling back to defaults for anything never set.

    Returns:
        The settings in effect.
    """
    return _view(await session.get(Settings, SETTINGS_ROW_ID))


async def update_settings(session: AsyncSession, data: SettingsUpdate) -> SettingsView:
    """Change settings.

    Returns:
        The settings in effect afterwards.
    """
    row = await session.get(Settings, SETTINGS_ROW_ID)
    if row is None:
        row = Settings(
            id=SETTINGS_ROW_ID,
            deposit_refund_policy=DEFAULTS.deposit_refund_policy,
            walk_in_sales_enabled=DEFAULTS.walk_in_sales_enabled,
            walk_in_deposits_allowed=DEFAULTS.walk_in_deposits_allowed,
            negative_stock_allowed=DEFAULTS.negative_stock_allowed,
            unclaimed_alert_minutes=DEFAULTS.unclaimed_alert_minutes,
            uncompleted_alert_minutes=DEFAULTS.uncompleted_alert_minutes,
        )
        session.add(row)
    if data.deposit_refund_policy is not None:
        row.deposit_refund_policy = data.deposit_refund_policy
    if data.walk_in_sales_enabled is not None:
        row.walk_in_sales_enabled = data.walk_in_sales_enabled
    if data.walk_in_deposits_allowed is not None:
        row.walk_in_deposits_allowed = data.walk_in_deposits_allowed
    if data.negative_stock_allowed is not None:
        row.negative_stock_allowed = data.negative_stock_allowed
    if data.unclaimed_alert_minutes is not None:
        row.unclaimed_alert_minutes = data.unclaimed_alert_minutes
    if data.uncompleted_alert_minutes is not None:
        row.uncompleted_alert_minutes = data.uncompleted_alert_minutes
    await session.flush()
    return _view(row)
