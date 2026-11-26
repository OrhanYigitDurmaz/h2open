# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database access shared by all modules.

Each module owns one Postgres schema and declares its tables on its own
``MetaData`` from :func:`module_metadata`. Modules never join or reference
another module's tables; they store the other entity's ID instead.

Every request that asks for :data:`SessionDep` runs in one transaction that
commits when the endpoint returns and rolls back if it raises.
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Self, TypedDict, cast

from fastapi import Depends, Request
from sqlalchemy import Enum, MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from enum import StrEnum

    from sqlalchemy import URL

# Predictable constraint names, so Alembic migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def module_metadata(schema: str) -> MetaData:
    """Create the metadata for one module's tables.

    Args:
        schema: The Postgres schema the module owns, e.g. ``"catalog"``.

    Returns:
        Metadata that puts every table in ``schema``.
    """
    return MetaData(schema=schema, naming_convention=NAMING_CONVENTION)


def enum_column(enum: type[StrEnum], name: str) -> Enum:
    """The column type for a string enum, the same in every module.

    Members are stored by name in a ``VARCHAR(20)`` with a CHECK constraint,
    not as a Postgres enum type, so adding a member is a simple migration.

    Args:
        enum: The enum class.
        name: The constraint's name, e.g. ``"order_status"``.

    Returns:
        The column type.
    """
    return Enum(enum, name=name, native_enum=False, create_constraint=True, length=20)


class Database:
    """A connection pool plus a factory for transactional sessions."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Wrap an engine.

        Args:
            engine: The async engine to draw connections from.
        """
        self.engine: AsyncEngine = engine
        self._sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

    @classmethod
    def connect(cls, url: URL) -> Self:
        """Create a database for a URL. No connection is opened yet.

        Args:
            url: Where the database is.

        Returns:
            The database.
        """
        return cls(create_async_engine(url, pool_pre_ping=True))

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession]:
        """Open a session in a transaction.

        Commits when the block exits normally, rolls back if it raises.

        Yields:
            The session.
        """
        async with self._sessions() as session, session.begin():
            yield session

    async def dispose(self) -> None:
        """Close every pooled connection."""
        await self.engine.dispose()


class AppState(TypedDict):
    """Objects the application creates at startup, available on each request."""

    database: Database


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: a session in a transaction for one request.

    Args:
        request: The current request.

    Yields:
        The session.
    """
    # Starlette stores what the lifespan yielded (an AppState) in scope["state"].
    # FastAPI rejects the typed Request[AppState] annotation, hence the cast.
    state = cast("AppState", request.scope["state"])
    async with state["database"].transaction() as session:
        # Safe: FastAPI wraps yield deps in asynccontextmanager, closed per request.
        yield session  # ruff: ignore[yield-in-context-manager-in-async-generator]


SessionDep = Annotated[AsyncSession, Depends(get_session)]
