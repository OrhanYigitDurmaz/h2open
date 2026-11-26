# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP endpoints of the identity module. Private to this module."""

from http import HTTPStatus

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.db import SessionDep
from app.core.errors import UnauthenticatedError, error_response
from app.core.ids import EntityId
from app.modules.identity import _service
from app.modules.identity._auth import CurrentActor, admin_actor
from app.modules.identity._schemas import (
    LoginRequest,
    PasswordChange,
    PasswordReset,
    PushTokenUpdate,
    SecuritySettingsUpdate,
    ShiftUpdate,
    UserCreate,
    UserUpdate,
)
from app.modules.identity._views import (
    Actor,
    LoginResult,
    SecuritySettingsView,
    SessionView,
    UserView,
)

auth = APIRouter(prefix="/auth", tags=["auth"])
users = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(admin_actor)])
security = APIRouter(
    prefix="/security", tags=["security"], dependencies=[Depends(admin_actor)]
)
router = APIRouter()


@auth.post(
    "/login",
    response_model=LoginResult,
    responses={HTTPStatus.UNAUTHORIZED: {"description": "Login failed."}},
)
async def login(session: SessionDep, data: LoginRequest) -> LoginResult | JSONResponse:
    """Log in and get a token.

    Repeated failures lock the account for a while (see /security/settings).

    Returns:
        The token and the user, or a 401 that never says what was wrong.
    """
    result = await _service.login(session, data)
    if result is None:
        # Returned, not raised: the transaction must commit the failure count.
        return error_response(UnauthenticatedError(_service.LOGIN_FAILED))
    return result


@auth.post("/logout", status_code=HTTPStatus.NO_CONTENT)
async def logout(session: SessionDep, actor: CurrentActor) -> None:
    """End this login; its phone stops getting push messages."""
    await _service.logout(session, actor)


@auth.get("/me")
async def me(actor: CurrentActor) -> Actor:
    """Who is logged in.

    Returns:
        The user and the login's ID.
    """
    return actor


@auth.put("/me/push-token", status_code=HTTPStatus.NO_CONTENT)
async def set_push_token(
    session: SessionDep, actor: CurrentActor, data: PushTokenUpdate
) -> None:
    """Set or clear this login's Firebase token (for call notifications)."""
    await _service.set_push_token(session, actor, data.fcm_token)


@auth.put("/me/shift")
async def set_shift(
    session: SessionDep, actor: CurrentActor, data: ShiftUpdate
) -> UserView:
    """Drivers start or end their shift; on shift, they can claim orders.

    Returns:
        You, with the new shift status.
    """
    return await _service.set_shift(session, actor, on_shift=data.on_shift)


@auth.put("/me/password", status_code=HTTPStatus.NO_CONTENT)
async def change_password(
    session: SessionDep, actor: CurrentActor, data: PasswordChange
) -> None:
    """Change your password. Your other logins are ended."""
    await _service.change_password(session, actor, data)


@users.post("", status_code=HTTPStatus.CREATED)
async def create_user(session: SessionDep, data: UserCreate) -> UserView:
    """Add a user (admins only).

    Returns:
        The new user.
    """
    return await _service.create_user(session, data)


@users.get("")
async def list_users(session: SessionDep) -> list[UserView]:
    """List users (admins only).

    Returns:
        Every user, by username.
    """
    return await _service.list_users(session)


@users.patch("/{user_id}")
async def update_user(
    session: SessionDep, user_id: EntityId, data: UserUpdate
) -> UserView:
    """Rename, change roles, or (de)activate a user (admins only).

    Returns:
        The updated user.
    """
    return await _service.update_user(session, user_id, data)


@users.put("/{user_id}/password", status_code=HTTPStatus.NO_CONTENT)
async def reset_password(
    session: SessionDep, user_id: EntityId, data: PasswordReset
) -> None:
    """Set a user's password and log them out everywhere (admins only)."""
    await _service.reset_password(session, user_id, data)


@users.get("/{user_id}/sessions")
async def sessions(session: SessionDep, user_id: EntityId) -> list[SessionView]:
    """A user's live logins (admins only).

    Returns:
        The logins, newest first.
    """
    return await _service.sessions(session, user_id)


@security.get("/settings")
async def get_security_settings(session: SessionDep) -> SecuritySettingsView:
    """Read the login rules (admins only).

    Returns:
        The rules in effect.
    """
    return await _service.get_security_settings(session)


@security.patch("/settings")
async def update_security_settings(
    session: SessionDep, data: SecuritySettingsUpdate
) -> SecuritySettingsView:
    """Change the login rules (admins only). New lifetimes apply to new logins.

    Returns:
        The rules in effect afterwards.
    """
    return await _service.update_security_settings(session, data)


router.include_router(auth)
router.include_router(users)
router.include_router(security)
