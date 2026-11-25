# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI dependencies that identify the caller. Private; use ``api``."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.db import SessionDep
from app.core.errors import PermissionDeniedError, UnauthenticatedError
from app.modules.identity import _service
from app.modules.identity._views import Actor, Role

_bearer = HTTPBearer(auto_error=False, description="The token from /auth/login.")


async def current_actor(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Actor:
    """The logged-in user making this request.

    Returns:
        The user and their login.

    Raises:
        UnauthenticatedError: No token was sent.
    """
    if credentials is None:
        msg = "log in first: send Authorization: Bearer <token>"
        raise UnauthenticatedError(msg)
    return await _service.authenticate(session, credentials.credentials)


CurrentActor = Annotated[Actor, Depends(current_actor)]


def admin_actor(actor: CurrentActor) -> Actor:
    """The logged-in user, who must be an admin.

    Returns:
        The admin.

    Raises:
        PermissionDeniedError: The user is not an admin.
    """
    if not actor.has(Role.ADMIN):
        msg = "only admins can do this"
        raise PermissionDeniedError(msg)
    return actor


AdminActor = Annotated[Actor, Depends(admin_actor)]
