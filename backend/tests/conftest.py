# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared test fixtures.

Tests run against a real Postgres (start it with ``docker compose up -d``).
They use a separate ``<POSTGRES_DB>_test`` database, recreated and migrated
at the start of every run, so the development database is never touched.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, NullPool, create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import Database
from app.core.settings import load_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import URL

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def pytest_configure() -> None:
    """Point every database connection in this test run at the test database."""
    database = load_settings().postgres_db
    if not database.endswith("_test"):
        os.environ["POSTGRES_DB"] = f"{database}_test"


def _recreate(admin: Engine, database: str) -> None:
    name = admin.dialect.identifier_preparer.quote(database)
    with admin.connect() as connection:
        _ = connection.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        _ = connection.execute(text(f"CREATE DATABASE {name}"))


@pytest.fixture(scope="session")
def database_url() -> Iterator[URL]:
    """Create the test database, migrate it to the latest revision, drop it after.

    Yields:
        The test database's URL.
    """
    url = load_settings().database_url
    admin = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    _recreate(admin, str(url.database))
    command.upgrade(Config(toml_file=str(PYPROJECT)), "head")
    yield url
    with admin.connect() as connection:
        name = admin.dialect.identifier_preparer.quote(str(url.database))
        _ = connection.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def database(database_url: URL) -> Iterator[Database]:
    """A database for one test; every table is emptied afterwards.

    Connections are not pooled, so the database works from any event loop,
    including the one ``TestClient`` runs the app in.

    Yields:
        The database.
    """
    yield Database(create_async_engine(database_url, poolclass=NullPool))
    engine = create_engine(database_url, poolclass=NullPool)
    with engine.begin() as connection:
        inspector = inspect(connection)
        preparer = engine.dialect.identifier_preparer
        tables = [
            f"{preparer.quote(schema)}.{preparer.quote(name)}"
            for schema in inspector.get_schema_names()
            if schema != "information_schema"
            for name in inspector.get_table_names(schema=schema)
            if name != "alembic_version"
        ]
        if tables:
            _ = connection.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )
    engine.dispose()
