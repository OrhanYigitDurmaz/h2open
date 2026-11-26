# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the telephony module. Private to this module."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.db import SessionDep
from app.core.ids import EntityId
from app.modules.identity import api as identity
from app.modules.telephony import _service
from app.modules.telephony._schemas import CallSearch, SettingsUpdate
from app.modules.telephony._views import CallView, TelephonySettingsView

router = APIRouter(tags=["telephony"], dependencies=[Depends(identity.current_actor)])
ADMIN = [Depends(identity.admin_actor)]
"""Changing how calls ring is for admins; everyone logged in can read it."""


@router.get("/telephony/settings")
async def get_settings(session: SessionDep) -> TelephonySettingsView:
    """Read how incoming calls are rung.

    Returns:
        The settings in effect.
    """
    return await _service.get_settings(session)


@router.patch("/telephony/settings", dependencies=ADMIN)
async def update_settings(
    session: SessionDep, data: SettingsUpdate
) -> TelephonySettingsView:
    """Change how incoming calls are rung.

    Returns:
        The settings in effect afterwards.
    """
    return await _service.update_settings(session, data)


@router.get("/calls")
async def list_calls(
    session: SessionDep, search: Annotated[CallSearch, Query()]
) -> list[CallView]:
    """The call log, newest first; ``status=missed`` lists calls to return.

    Returns:
        The matching calls.
    """
    return await _service.list_calls(session, search)


@router.get("/calls/active")
async def active_calls(session: SessionDep) -> list[CallView]:
    """Calls ringing or in progress, for the POS's incoming-call popup.

    Returns:
        The calls, oldest first, with the caller's customer if known.
    """
    return await _service.active_calls(session)


@router.get("/calls/{call_id}")
async def get_call(session: SessionDep, call_id: EntityId) -> CallView:
    """Get one call.

    Returns:
        The call.
    """
    return await _service.get_call(session, call_id)
