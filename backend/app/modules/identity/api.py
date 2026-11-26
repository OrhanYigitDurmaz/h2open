# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the identity module.

Other modules protect their endpoints with these dependencies:

- ``CurrentActor``: any logged-in user; use ``actor.id`` to record who did it.
- ``AdminActor``: logged-in admins only.
- ``current_actor`` / ``admin_actor``: the same, for a whole router via
  ``APIRouter(dependencies=[Depends(api.current_actor)])``.
"""

from typing import TYPE_CHECKING

from app.modules.identity import _service
from app.modules.identity._auth import (
    AdminActor,
    CurrentActor,
    admin_actor,
    current_actor,
)
from app.modules.identity._schemas import UserCreate
from app.modules.identity._views import (
    Actor,
    LoginResult,
    PushTarget,
    Role,
    SecuritySettingsView,
    SessionView,
    UserView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId

__all__ = [
    "Actor",
    "AdminActor",
    "CurrentActor",
    "LoginResult",
    "PushTarget",
    "Role",
    "SecuritySettingsView",
    "SessionView",
    "UserCreate",
    "UserView",
    "admin_actor",
    "create_user",
    "current_actor",
    "forget_push_token",
    "push_targets",
    "user_push_targets",
]


async def create_user(session: AsyncSession, data: UserCreate) -> UserView:
    """Add a user, e.g. the first admin from the command line.

    Args:
        session: The caller's database session.
        data: The new user.

    Returns:
        The new user.
    """
    return await _service.create_user(session, data)


async def push_targets(
    session: AsyncSession, role: Role, *, on_shift_only: bool = False
) -> list[PushTarget]:
    """Logged-in phones of active users with a role, for push messages.

    Args:
        session: The caller's database session.
        role: Usually ``Role.DRIVER``, for incoming-call notifications.
        on_shift_only: Only users who are on shift right now.

    Returns:
        One target per live login with a push token.
    """
    return await _service.push_targets(session, role, on_shift_only=on_shift_only)


async def user_push_targets(
    session: AsyncSession, user_id: EntityId
) -> list[PushTarget]:
    """One active user's logged-in phones, for push messages meant for them.

    Args:
        session: The caller's database session.
        user_id: The user.

    Returns:
        One target per live login with a push token.
    """
    return await _service.user_push_targets(session, user_id)


async def forget_push_token(session: AsyncSession, fcm_token: str) -> None:
    """Stop sending to a token Firebase reports as unregistered.

    Args:
        session: The caller's database session.
        fcm_token: The dead token.
    """
    await _service.forget_push_token(session, fcm_token)
