# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the notifications module. Private to this module."""

from fastapi import APIRouter, Depends

from app.core.db import SessionDep
from app.core.push import PushStatus, get_sender
from app.modules.identity import api as identity
from app.modules.notifications._push import PushReport, push

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(identity.current_actor)],
)

TEST_TTL = 60


@router.get("/status", dependencies=[Depends(identity.admin_actor)])
def status() -> PushStatus:
    """Whether push messages are configured, and if not, why. Admins only.

    Returns:
        The status.
    """
    return get_sender().status


@router.post("/test")
async def test(session: SessionDep, actor: identity.CurrentActor) -> PushReport:
    """Send a test message to your own logged-in phones.

    The app shows it, so you can check notifications work end to end.

    Returns:
        How many phones got it.
    """
    targets = await identity.user_push_targets(session, actor.id)
    return await push(session, targets, {"type": "test"}, ttl_seconds=TEST_TTL)
