# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Users, logins and sessions. Private to this module."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
)
from app.core.ids import new_id
from app.modules.identity._models import (
    SECURITY_SETTINGS_ROW_ID,
    SecuritySettings,
    Session,
    User,
    UserRole,
)
from app.modules.identity._passwords import DUMMY_HASH, hash_password, verify_password
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
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.ids import EntityId
    from app.modules.identity._schemas import (
        LoginRequest,
        PasswordChange,
        PasswordReset,
        SecuritySettingsUpdate,
        UserCreate,
        UserUpdate,
    )

DEFAULT_SECURITY = SecuritySettingsView(
    session_lifetime_days=30, max_failed_logins=5, lockout_minutes=15
)
TOUCH_INTERVAL = timedelta(minutes=1)
"""How stale ``last_used_at`` may get before a request updates it."""
LOGIN_FAILED = "wrong username or password, or the account is locked for a while"
NOT_CHANGED = "the current password is wrong, or the account is locked for a while"


def _now() -> datetime:
    return datetime.now(UTC)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        username=user.username,
        name=user.name,
        roles=sorted((row.role for row in user.roles), key=list(Role).index),
        active=user.active,
        on_shift=user.on_shift,
    )


async def _load(
    session: AsyncSession, user_id: EntityId, *, lock: bool = False
) -> User:
    """Load a user with roles.

    Args:
        session: The caller's database session.
        user_id: The user.
        lock: Lock the user's row until the transaction ends, so that
            concurrent requests can't lose each other's failure counts.

    Returns:
        The user.

    Raises:
        NotFoundError: No such user.
    """
    query = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
        .execution_options(populate_existing=True)
    )
    user = await session.scalar(query.with_for_update(of=User) if lock else query)
    if user is None:
        msg = f"user {user_id} not found"
        raise NotFoundError(msg)
    return user


async def _revoke_all(session: AsyncSession, user_id: EntityId) -> None:
    _ = await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def _release_push_token(session: AsyncSession, fcm_token: str | None) -> None:
    """Detach a push token from other live logins (same phone, new login)."""
    if fcm_token is not None:
        _ = await session.execute(
            update(Session)
            .where(Session.fcm_token == fcm_token, Session.revoked_at.is_(None))
            .values(fcm_token=None)
        )


def _set_roles(user: User, roles: Iterable[Role]) -> None:
    wanted = set(roles)
    for row in list(user.roles):
        if row.role in wanted:
            wanted.discard(row.role)
        else:
            user.roles.remove(row)
    user.roles.extend(UserRole(role=role) for role in sorted(wanted))


# Logging in and out


def _locked(user: User | None, now: datetime) -> bool:
    return (
        user is not None and user.locked_until is not None and user.locked_until > now
    )


def _record_failure(user: User, now: datetime, rules: SecuritySettingsView) -> None:
    user.failed_logins += 1
    if user.failed_logins >= rules.max_failed_logins:
        user.failed_logins = 0
        user.locked_until = now + timedelta(minutes=rules.lockout_minutes)


async def _check_credentials(
    session: AsyncSession, data: LoginRequest, rules: SecuritySettingsView
) -> User | None:
    """Find the user and check the password, counting failures.

    Returns:
        The active user whose password matched, or ``None`` if anything is
        wrong. Callers must not say which part was wrong.
    """
    now = _now()
    # Locked until the transaction ends: parallel attempts then count one by
    # one instead of all reading, and writing back, the same failure count.
    user = await session.scalar(
        select(User)
        .where(User.username == data.username)
        .options(selectinload(User.roles))
        .with_for_update(of=User)
    )
    matches = await verify_password(
        data.password, DUMMY_HASH if user is None else user.password_hash
    )
    if user is None or not user.active or _locked(user, now) or not matches:
        if user is not None and not _locked(user, now):
            _record_failure(user, now, rules)
        return None
    user.failed_logins = 0
    user.locked_until = None
    return user


async def login(session: AsyncSession, data: LoginRequest) -> LoginResult | None:
    """Log in with a username and password.

    A failed attempt returns ``None`` instead of raising, so the request's
    transaction still commits the failure count used for lockouts.

    Returns:
        A new token (shown only now) and the user, or ``None`` on failure.
    """
    rules = await get_security_settings(session)
    user = await _check_credentials(session, data, rules)
    if user is None:
        return None
    await _release_push_token(session, data.fcm_token)
    token = secrets.token_urlsafe(32)
    now = _now()
    row = Session(
        id=new_id(),
        user_id=user.id,
        token_hash=_token_hash(token),
        platform=data.platform,
        client_name=data.client_name,
        fcm_token=data.fcm_token,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=rules.session_lifetime_days),
    )
    session.add(row)
    await session.flush()
    return LoginResult(token=token, expires_at=row.expires_at, user=_user_view(user))


async def authenticate(session: AsyncSession, token: str) -> Actor:
    """Find the live login a token belongs to.

    Returns:
        The user and their login.

    Raises:
        UnauthenticatedError: The token is unknown, expired or revoked, or
            the user was deactivated.
    """
    now = _now()
    row = await session.scalar(
        select(Session).where(
            Session.token_hash == _token_hash(token),
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
    )
    if row is None:
        msg = "log in again: the token is unknown, expired or revoked"
        raise UnauthenticatedError(msg)
    user = await _load(session, row.user_id)
    if not user.active:
        msg = "this account is deactivated"
        raise UnauthenticatedError(msg)
    if now - row.last_used_at > TOUCH_INTERVAL:
        row.last_used_at = now
    return Actor(user=_user_view(user), session_id=row.id)


async def logout(session: AsyncSession, actor: Actor) -> None:
    """End the current login; its phone stops getting push messages."""
    _ = await session.execute(
        update(Session).where(Session.id == actor.session_id).values(revoked_at=_now())
    )


async def set_push_token(
    session: AsyncSession, actor: Actor, fcm_token: str | None
) -> None:
    """Replace (or clear) the current login's push token."""
    await _release_push_token(session, fcm_token)
    _ = await session.execute(
        update(Session)
        .where(Session.id == actor.session_id)
        .values(fcm_token=fcm_token)
    )


def _set_shift(user: User, *, on_shift: bool) -> None:
    """Start or end a driver's shift.

    Raises:
        DomainError: Starting a shift for someone who is not a driver.
    """
    if on_shift and Role.DRIVER not in {row.role for row in user.roles}:
        msg = "only drivers have shifts"
        raise DomainError(msg)
    user.on_shift = on_shift


async def set_shift(session: AsyncSession, actor: Actor, *, on_shift: bool) -> UserView:
    """Start or end your own shift.

    Returns:
        You, with the new shift status.

    Raises:
        PermissionDeniedError: You are not a driver.
    """
    if not actor.has(Role.DRIVER):
        msg = "only drivers have shifts"
        raise PermissionDeniedError(msg)
    user = await _load(session, actor.id)
    _set_shift(user, on_shift=on_shift)
    await session.flush()
    return _user_view(user)


async def change_password(
    session: AsyncSession, actor: Actor, data: PasswordChange
) -> bool:
    """Change one's own password; other logins are ended.

    Wrong current passwords count towards the lockout like failed logins,
    so a stolen token can't be used to guess the password. A locked account
    can't change its password until the lockout ends.

    Returns:
        Whether the password was changed. ``False`` means the current
        password was wrong or the account is locked; the caller must still
        commit, to keep the failure count.
    """
    now = _now()
    user = await _load(session, actor.id, lock=True)
    if _locked(user, now):
        return False
    if not await verify_password(data.current_password, user.password_hash):
        _record_failure(user, now, await get_security_settings(session))
        return False
    user.failed_logins = 0
    user.password_hash = await hash_password(data.new_password)
    _ = await session.execute(
        update(Session)
        .where(
            Session.user_id == user.id,
            Session.id != actor.session_id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    return True


async def sessions(session: AsyncSession, user_id: EntityId) -> list[SessionView]:
    """List a user's live logins, newest first.

    Returns:
        The logins.
    """
    _ = await _load(session, user_id)
    rows = await session.scalars(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > _now(),
        )
        .order_by(Session.created_at.desc())
    )
    return [
        SessionView(
            id=row.id,
            platform=row.platform,
            client_name=row.client_name,
            has_push_token=row.fcm_token is not None,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
        )
        for row in rows
    ]


async def _push_targets(
    session: AsyncSession, *conditions: ColumnElement[bool]
) -> list[PushTarget]:
    rows = await session.execute(
        select(Session.user_id, Session.id, Session.fcm_token)
        .join(User, User.id == Session.user_id)
        .where(
            User.active,
            Session.revoked_at.is_(None),
            Session.expires_at > _now(),
            Session.fcm_token.is_not(None),
            *conditions,
        )
        .order_by(Session.created_at)
    )
    return [
        PushTarget(user_id=user_id, session_id=session_id, fcm_token=fcm_token)
        for user_id, session_id, fcm_token in rows
        if fcm_token is not None
    ]


async def push_targets(
    session: AsyncSession, role: Role, *, on_shift_only: bool = False
) -> list[PushTarget]:
    """Phones of active users with a role that are logged in with a push token.

    Returns:
        One target per live login with a push token.
    """
    has_role = (
        select(UserRole.user_id)
        .where(UserRole.user_id == User.id, UserRole.role == role)
        .exists()
    )
    conditions: list[ColumnElement[bool]] = [has_role]
    if on_shift_only:
        conditions.append(User.on_shift.is_(True))
    return await _push_targets(session, *conditions)


async def user_push_targets(
    session: AsyncSession, user_id: EntityId
) -> list[PushTarget]:
    """One active user's logged-in phones with a push token.

    Returns:
        One target per live login with a push token.
    """
    return await _push_targets(session, User.id == user_id)


async def drivers_on_shift(session: AsyncSession) -> list[UserView]:
    """Active drivers who are on shift.

    Returns:
        The drivers, by username.
    """
    users = await session.scalars(
        select(User)
        .options(selectinload(User.roles))
        .where(
            User.active,
            User.on_shift,
            select(UserRole.user_id)
            .where(UserRole.user_id == User.id, UserRole.role == Role.DRIVER)
            .exists(),
        )
        .order_by(User.username)
    )
    return [_user_view(user) for user in users]


async def forget_push_token(session: AsyncSession, fcm_token: str) -> None:
    """Stop using a push token Firebase says is no longer valid."""
    _ = await session.execute(
        update(Session).where(Session.fcm_token == fcm_token).values(fcm_token=None)
    )


# User administration


async def create_user(session: AsyncSession, data: UserCreate) -> UserView:
    """Add a user.

    Returns:
        The new user.

    Raises:
        ConflictError: The username is taken.
    """
    user = User(
        id=new_id(),
        username=data.username,
        name=data.name,
        password_hash=await hash_password(data.password),
        created_at=_now(),
    )
    _set_roles(user, data.roles)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as error:
        msg = f"the username {data.username!r} is taken"
        raise ConflictError(msg) from error
    return _user_view(await _load(session, user.id))


async def list_users(session: AsyncSession) -> list[UserView]:
    """List every user by username.

    Returns:
        The users.
    """
    users = await session.scalars(
        select(User).options(selectinload(User.roles)).order_by(User.username)
    )
    return [_user_view(user) for user in users]


async def update_user(
    session: AsyncSession, user_id: EntityId, data: UserUpdate
) -> UserView:
    """Rename a user, change their roles, or (de)activate them.

    Returns:
        The updated user.
    """
    user = await _load(session, user_id)
    if data.name is not None:
        user.name = data.name
    if data.roles is not None:
        _set_roles(user, data.roles)
    if data.active is not None:
        user.active = data.active
        if not data.active:
            await _revoke_all(session, user_id)
    if data.on_shift is not None:
        _set_shift(user, on_shift=data.on_shift)
    if not user.active or Role.DRIVER not in {row.role for row in user.roles}:
        user.on_shift = False
    await session.flush()
    await _require_an_admin(session)
    return _user_view(await _load(session, user_id))


async def _require_an_admin(session: AsyncSession) -> None:
    """Never leave the system without an active admin.

    Raises:
        DomainError: The change would remove the last active admin.
    """
    admins = await session.scalar(
        select(func.count())
        .select_from(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(User.active, UserRole.role == Role.ADMIN)
    )
    if not admins:
        msg = "at least one active admin must remain"
        raise DomainError(msg)


async def reset_password(
    session: AsyncSession, user_id: EntityId, data: PasswordReset
) -> None:
    """Set a user's password (e.g. they forgot it) and log them out everywhere."""
    user = await _load(session, user_id)
    user.password_hash = await hash_password(data.new_password)
    user.failed_logins = 0
    user.locked_until = None
    await _revoke_all(session, user_id)


# Login rules


def _security_view(row: SecuritySettings | None) -> SecuritySettingsView:
    if row is None:
        return DEFAULT_SECURITY
    return SecuritySettingsView(
        session_lifetime_days=row.session_lifetime_days,
        max_failed_logins=row.max_failed_logins,
        lockout_minutes=row.lockout_minutes,
    )


async def get_security_settings(session: AsyncSession) -> SecuritySettingsView:
    """Read the login rules, with defaults for anything never set.

    Returns:
        The rules in effect.
    """
    return _security_view(await session.get(SecuritySettings, SECURITY_SETTINGS_ROW_ID))


async def update_security_settings(
    session: AsyncSession, data: SecuritySettingsUpdate
) -> SecuritySettingsView:
    """Change the login rules.

    Returns:
        The rules in effect afterwards.
    """
    row = await session.get(SecuritySettings, SECURITY_SETTINGS_ROW_ID)
    if row is None:
        row = SecuritySettings(
            id=SECURITY_SETTINGS_ROW_ID,
            session_lifetime_days=DEFAULT_SECURITY.session_lifetime_days,
            max_failed_logins=DEFAULT_SECURITY.max_failed_logins,
            lockout_minutes=DEFAULT_SECURITY.lockout_minutes,
        )
        session.add(row)
    if data.session_lifetime_days is not None:
        row.session_lifetime_days = data.session_lifetime_days
    if data.max_failed_logins is not None:
        row.max_failed_logins = data.max_failed_logins
    if data.lockout_minutes is not None:
        row.lockout_minutes = data.lockout_minutes
    await session.flush()
    return _security_view(row)
