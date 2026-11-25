# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for database sessions, transactions and settings."""

import asyncio
from http import HTTPStatus

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, literal, select, table, text

from app.core.app import Module, create_app
from app.core.db import Database, SessionDep, module_metadata
from app.core.events import EventBus
from app.core.settings import Settings

SPECIAL_CHARACTERS = "p@ss/w:rd"

router = APIRouter(prefix="/db")


@router.get("/ping")
async def ping(session: SessionDep) -> dict[str, int]:
    """Run a query through the request's session.

    Returns:
        The query result.
    """
    value = await session.scalar(select(literal(1)))
    assert value is not None
    return {"value": value}


@pytest.fixture
def scratch(database: Database) -> None:
    """Create a throwaway table; the database fixture empties it after the test."""

    async def create() -> None:
        async with database.transaction() as session:
            _ = await session.execute(
                text("CREATE TABLE IF NOT EXISTS public.scratch (value int)")
            )

    asyncio.run(create())


def count_scratch_rows(database: Database) -> int:
    """Count the rows in the scratch table.

    Returns:
        The number of rows.
    """

    async def count() -> int:
        async with database.transaction() as session:
            query = select(func.count()).select_from(table("scratch", schema="public"))
            value = await session.scalar(query)
            assert value is not None
            return value

    return asyncio.run(count())


def test_session_dependency_runs_queries(database: Database) -> None:
    """Endpoints get a working session; startup and shutdown run cleanly."""
    app = create_app(
        [Module(name="db", router=router)], event_bus=EventBus(), database=database
    )
    with TestClient(app) as client:
        response = client.get("/db/ping")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"value": 1}


@pytest.mark.usefixtures("scratch")
def test_transaction_commits(database: Database) -> None:
    """A transaction that finishes normally is committed."""

    async def insert() -> None:
        async with database.transaction() as session:
            _ = await session.execute(text("INSERT INTO public.scratch VALUES (1)"))

    asyncio.run(insert())
    assert count_scratch_rows(database) == 1


@pytest.mark.usefixtures("scratch")
def test_transaction_rolls_back_on_error(database: Database) -> None:
    """A transaction that raises leaves nothing behind."""

    async def insert_then_fail() -> None:
        async with database.transaction() as session:
            _ = await session.execute(text("INSERT INTO public.scratch VALUES (1)"))
            msg = "boom"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError):
        asyncio.run(insert_then_fail())
    assert count_scratch_rows(database) == 0


def test_module_metadata_uses_schema_and_naming_convention() -> None:
    """Module tables land in the module's schema with predictable names."""
    metadata = module_metadata("catalog")
    assert metadata.schema == "catalog"
    assert metadata.naming_convention.get("pk") == "pk_%(table_name)s"


def test_database_url_escapes_password() -> None:
    """Special characters in the password survive URL building."""
    settings = Settings(postgres_password=SecretStr(SPECIAL_CHARACTERS))
    url = settings.database_url
    assert url.drivername == "postgresql+psycopg"
    assert url.password == SPECIAL_CHARACTERS
    assert "p%40ss%2Fw%3Ard" in url.render_as_string(hide_password=False)
