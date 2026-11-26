# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request bodies for the identity endpoints. Private to this module."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.modules.identity._views import Platform, Role

type Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=50,
        # Checked before lower-casing, so capitals are accepted (and stored
        # lower-case).
        pattern=r"^[A-Za-z0-9._-]+$",
    ),
]
type Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
type Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
"""At least 10 characters; long passphrases are welcome."""
type FcmToken = Annotated[str, StringConstraints(min_length=1, max_length=4096)]
type Roles = Annotated[set[Role], Field(min_length=1)]


class LoginRequest(BaseModel):
    """Credentials, and optionally which app is logging in."""

    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True)]
    password: Annotated[str, StringConstraints(max_length=128)]
    platform: Platform = Platform.WEB
    client_name: Annotated[str, StringConstraints(max_length=100)] | None = None
    """E.g. "POS 1" or the phone model."""
    fcm_token: FcmToken | None = None
    """The phone's Firebase token, for call notifications."""


class PushTokenUpdate(BaseModel):
    """A new Firebase token for this login (Android refreshes them)."""

    fcm_token: FcmToken | None
    """``null`` stops push messages to this login."""


class ShiftUpdate(BaseModel):
    """A driver starting or ending their shift."""

    on_shift: bool


class PasswordChange(BaseModel):
    """A user changing their own password."""

    current_password: Annotated[str, StringConstraints(max_length=128)]
    new_password: Password


class UserCreate(BaseModel):
    """A new user account."""

    username: Username
    name: Name
    password: Password
    roles: Roles


class UserUpdate(BaseModel):
    """Changes to a user; omitted fields stay as they are.

    Deactivating a user logs them out everywhere.
    """

    name: Name | None = None
    roles: Roles | None = None
    active: bool | None = None
    on_shift: bool | None = None
    """E.g. ``false`` to end a shift a driver forgot to end."""


class SecuritySettingsUpdate(BaseModel):
    """Changes to the login rules; omitted fields stay as they are."""

    session_lifetime_days: Annotated[int, Field(ge=1, le=365)] | None = None
    max_failed_logins: Annotated[int, Field(ge=3, le=20)] | None = None
    lockout_minutes: Annotated[int, Field(ge=1, le=1440)] | None = None


class PasswordReset(BaseModel):
    """An admin setting a new password; the user is logged out everywhere."""

    new_password: Password
