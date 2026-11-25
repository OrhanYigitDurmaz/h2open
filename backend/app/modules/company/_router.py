# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the company module. Private to this module."""

from fastapi import APIRouter, Depends

from app.core.db import SessionDep
from app.modules.company import _service
from app.modules.company._schemas import SettingsUpdate
from app.modules.company._views import SettingsView
from app.modules.identity import api as identity

router = APIRouter(
    prefix="/company",
    tags=["company"],
    dependencies=[Depends(identity.current_actor)],
)
ADMIN = [Depends(identity.admin_actor)]
"""Changing settings is for admins; everyone logged in can read them."""


@router.get("/settings")
async def get_settings(session: SessionDep) -> SettingsView:
    """Read the company settings.

    Returns:
        The settings in effect.
    """
    return await _service.get_settings(session)


@router.patch("/settings", dependencies=ADMIN)
async def update_settings(session: SessionDep, data: SettingsUpdate) -> SettingsView:
    """Change company settings.

    Returns:
        The settings in effect afterwards.
    """
    return await _service.update_settings(session, data)
