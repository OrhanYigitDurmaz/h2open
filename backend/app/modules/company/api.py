# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the company module."""

from typing import TYPE_CHECKING

from app.modules.company import _service
from app.modules.company._views import DepositRefundPolicy, SettingsView

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["DepositRefundPolicy", "SettingsView", "get_settings"]


async def get_settings(session: AsyncSession) -> SettingsView:
    """Read the company settings.

    Args:
        session: The caller's database session.

    Returns:
        The settings in effect.
    """
    return await _service.get_settings(session)
