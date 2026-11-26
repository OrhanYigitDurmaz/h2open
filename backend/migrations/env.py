# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alembic environment: migrates the schema of every module in ``app.main``.

Run from ``backend/``::

    uv run alembic revision --autogenerate -m "catalog: add products"
    uv run alembic upgrade head

Autogenerate does not create Postgres schemas; a module's first migration
must start with ``op.execute("CREATE SCHEMA ...")``.
"""

import asyncio
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import outbox
from app.core.settings import load_settings
from app.main import MODULES

if TYPE_CHECKING:
    from sqlalchemy import Connection, MetaData

TARGET_METADATA: list[MetaData] = [
    outbox.METADATA,
    *(module.metadata for module in MODULES if module.metadata is not None),
]
MODULE_SCHEMAS = {metadata.schema for metadata in TARGET_METADATA}


def include_name(name: str | None, type_: str, _parent_names: object) -> bool:
    """Limit autogenerate to the schemas that modules own.

    Args:
        name: The object's name.
        type_: The kind of object, e.g. ``"schema"`` or ``"table"``.
        _parent_names: Names of the enclosing objects (unused).

    Returns:
        Whether Alembic should compare this object.
    """
    return type_ != "schema" or name in MODULE_SCHEMAS


def run_migrations(connection: Connection) -> None:
    """Run the pending migrations on one connection.

    Args:
        connection: An open database connection.
    """
    context.configure(
        connection=connection,
        target_metadata=TARGET_METADATA,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    """Connect to the configured database and migrate it."""
    engine = create_async_engine(load_settings().database_url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    msg = "offline (--sql) migrations are not supported"
    raise SystemExit(msg)
asyncio.run(main())
