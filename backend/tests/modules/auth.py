# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers to create users and log in during tests."""

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING

from app.modules.identity import api as identity

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

CREDENTIAL = "correct horse battery"
"""The password of every user made by :func:`make_user`."""


def make_user(
    database: Database, username: str, roles: set[identity.Role]
) -> identity.UserView:
    """Create a user directly, with :data:`CREDENTIAL`.

    Returns:
        The user.
    """

    async def create() -> identity.UserView:
        async with database.transaction() as session:
            data = identity.UserCreate(
                username=username,
                name=username.title(),
                password=CREDENTIAL,
                roles=roles,
            )
            return await identity.create_user(session, data)

    return asyncio.run(create())


def login(client: TestClient, username: str, password: str = CREDENTIAL) -> str:
    """Log in through the API.

    Returns:
        The bearer token.
    """
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == HTTPStatus.OK, response.text
    return identity.LoginResult.model_validate_json(response.content).token


def bearer(token: str) -> dict[str, str]:
    """An Authorization header.

    Returns:
        The header.
    """
    return {"Authorization": f"Bearer {token}"}
