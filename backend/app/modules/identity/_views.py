# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read models of the identity module. Other modules get them via ``api``."""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.ids import EntityId


class Role(StrEnum):
    """What a user may do. A user can have several roles."""

    ADMIN = "admin"
    """Manages users, the catalog and company settings."""
    STAFF = "staff"
    """Works the POS: customers, orders, containers."""
    DRIVER = "driver"
    """Delivers orders; receives call pushes on their phone."""


class Platform(StrEnum):
    """What a login is from."""

    WEB = "web"
    ANDROID = "android"
    DESKTOP = "desktop"
    """The Windows/Linux POS app."""


class _View(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class UserView(_View):
    """A user account. Never includes the password hash."""

    id: EntityId
    username: str
    name: str
    roles: list[Role]
    active: bool
    on_shift: bool
    """Drivers only: working now, so they can claim orders."""


class Actor(_View):
    """The logged-in user making the current request."""

    user: UserView
    session_id: EntityId

    @property
    def id(self) -> EntityId:
        """The user's ID, recorded as "who did it".

        Returns:
            The user ID.
        """
        return self.user.id

    def has(self, role: Role) -> bool:
        """Whether the user has a role.

        Returns:
            True if the user has ``role``.
        """
        return role in self.user.roles


class LoginResult(_View):
    """A new login. The token is shown only once."""

    token: str
    """Send as ``Authorization: Bearer <token>``."""
    expires_at: datetime
    user: UserView


class SessionView(_View):
    """An active login of a user."""

    id: EntityId
    platform: Platform
    client_name: str | None
    has_push_token: bool
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime


class SecuritySettingsView(_View):
    """Login rules that admins can adjust."""

    session_lifetime_days: int
    """How long a login lasts. Changes apply to new logins only."""
    max_failed_logins: int
    """Consecutive wrong passwords that lock an account."""
    lockout_minutes: int
    """How long a locked account stays locked."""


class PushTarget(_View):
    """A logged-in phone that can receive push messages."""

    user_id: EntityId
    session_id: EntityId
    fcm_token: str
