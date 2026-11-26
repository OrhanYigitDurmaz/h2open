# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Identity tables, in the ``identity`` schema. Private to this module."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    String,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.db import enum_column, module_metadata
from app.core.ids import new_id
from app.modules.identity._views import Platform, Role


class Base(DeclarativeBase):
    """Base for identity tables."""

    metadata: ClassVar[MetaData] = module_metadata("identity")


class User(Base):
    """A person who logs in. Deactivated, never deleted."""

    __tablename__: str = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    """Stored lower-case; logins are case-insensitive."""
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)
    on_shift: Mapped[bool] = mapped_column(default=False, server_default=false())
    """Drivers on shift see the order pool and can claim orders."""
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[UserRole]] = relationship(
        order_by="UserRole.role", cascade="all, delete-orphan"
    )


class UserRole(Base):
    """One role of one user."""

    __tablename__: str = "user_roles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey(User.id), primary_key=True)
    role: Mapped[Role] = mapped_column(
        enum_column(Role, "role"),
        primary_key=True,
    )


SECURITY_SETTINGS_ROW_ID = 1


class SecuritySettings(Base):
    """The single row of login rules. Missing means all defaults."""

    __tablename__: str = "security_settings"
    __table_args__: tuple[CheckConstraint, ...] = (
        CheckConstraint(f"id = {SECURITY_SETTINGS_ROW_ID}", name="single_row"),
        CheckConstraint(
            "session_lifetime_days BETWEEN 1 AND 365", name="session_lifetime_range"
        ),
        CheckConstraint("max_failed_logins BETWEEN 3 AND 20", name="max_failed_range"),
        CheckConstraint("lockout_minutes BETWEEN 1 AND 1440", name="lockout_range"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    session_lifetime_days: Mapped[int] = mapped_column()
    max_failed_logins: Mapped[int] = mapped_column()
    lockout_minutes: Mapped[int] = mapped_column()


class Session(Base):
    """One login. Only a hash of its token is stored.

    A phone's FCM token lives on its login, so logging out (or being
    deactivated) also stops push messages to that phone.
    """

    __tablename__: str = "sessions"
    __table_args__: tuple[Index] = (
        # A phone's push token belongs to at most one live login.
        Index(
            "uq_sessions_fcm_token_live",
            "fcm_token",
            unique=True,
            postgresql_where=text("fcm_token IS NOT NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[UUID] = mapped_column(ForeignKey(User.id), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    platform: Mapped[Platform] = mapped_column(enum_column(Platform, "platform"))
    client_name: Mapped[str | None] = mapped_column(String(100))
    fcm_token: Mapped[str | None] = mapped_column(String(4096))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
