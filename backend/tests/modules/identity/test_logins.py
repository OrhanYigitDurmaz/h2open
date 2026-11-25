# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for logging in and out, tokens, lockouts and push tokens."""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter
from sqlalchemy import text

from app.modules.identity import api as identity
from app.modules.identity.api import Actor, LoginResult, Role, SessionView
from tests.modules.auth import CREDENTIAL, bearer, login, make_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response

    from app.core.db import Database

SESSIONS = TypeAdapter(list[SessionView])
WRONG = "not the right one"
LOCKING_ATTEMPTS = 5


def attempt(
    client: TestClient, username: str, password: str, **extra: object
) -> Response:
    """Try to log in without credentials attached.

    Returns:
        The raw response.
    """
    return client.post(
        "/auth/login",
        json={"username": username, "password": password, **extra},
        headers={"Authorization": ""},
    )


def sql(database: Database, statement: str, **params: object) -> None:
    """Run a raw SQL statement against the test database."""

    async def run() -> None:
        async with database.transaction() as session:
            _ = await session.execute(text(statement), params)

    asyncio.run(run())


def me(client: TestClient, token: str) -> Response:
    """Ask who is logged in with a token.

    Returns:
        The raw response.
    """
    return client.get("/auth/me", headers=bearer(token))


def test_login_and_me(client: TestClient, database: Database) -> None:
    """Usernames are case-insensitive; the token identifies the user."""
    user = make_user(database, "ayse", {Role.STAFF, Role.DRIVER})
    response = attempt(client, "  AYSE ", CREDENTIAL, client_name="POS 1")
    result = LoginResult.model_validate_json(response.content)
    assert result.user == user
    assert result.expires_at > datetime.now(UTC) + timedelta(days=29)

    actor = Actor.model_validate_json(me(client, result.token).content)
    assert actor.user == user
    assert actor.has(Role.DRIVER)
    assert not actor.has(Role.ADMIN)


@pytest.mark.parametrize(
    ("username", "password"), [("ayse", WRONG), ("nobody", CREDENTIAL)]
)
def test_failed_login_does_not_say_why(
    client: TestClient, database: Database, username: str, password: str
) -> None:
    """Wrong password and unknown user look exactly the same."""
    _ = make_user(database, "ayse", {Role.STAFF})
    response = attempt(client, username, password)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"] == (
        "wrong username or password, or the account is locked for a while"
    )


def test_lockout_after_five_failures(client: TestClient, database: Database) -> None:
    """Five wrong passwords lock the account; it unlocks after 15 minutes."""
    _ = make_user(database, "ayse", {Role.STAFF})
    for _ in range(LOCKING_ATTEMPTS):
        assert attempt(client, "ayse", WRONG).status_code == HTTPStatus.UNAUTHORIZED
    locked = attempt(client, "ayse", CREDENTIAL)
    assert locked.status_code == HTTPStatus.UNAUTHORIZED

    sql(
        database,
        "UPDATE identity.users SET locked_until = now() - interval '1 second'",
    )
    assert attempt(client, "ayse", CREDENTIAL).status_code == HTTPStatus.OK


def test_success_resets_the_failure_count(
    client: TestClient, database: Database
) -> None:
    """Failures only lock when they are consecutive."""
    _ = make_user(database, "ayse", {Role.STAFF})
    for _ in range(LOCKING_ATTEMPTS - 1):
        _ = attempt(client, "ayse", WRONG)
    assert attempt(client, "ayse", CREDENTIAL).status_code == HTTPStatus.OK
    for _ in range(LOCKING_ATTEMPTS - 1):
        _ = attempt(client, "ayse", WRONG)
    assert attempt(client, "ayse", CREDENTIAL).status_code == HTTPStatus.OK


@pytest.mark.parametrize(
    "stored", ["garbage", "argon2$1$1$1$AAAA$AAAA", "scrypt$x$1$1$AAAA$AAAA"]
)
def test_malformed_password_hash_never_matches(
    client: TestClient, database: Database, stored: str
) -> None:
    """A corrupted or foreign hash fails safely instead of crashing."""
    _ = make_user(database, "ayse", {Role.STAFF})
    sql(database, "UPDATE identity.users SET password_hash = :stored", stored=stored)
    assert attempt(client, "ayse", CREDENTIAL).status_code == HTTPStatus.UNAUTHORIZED


def test_tokens_must_be_sent_and_live(client: TestClient, database: Database) -> None:
    """Missing, unknown, expired and logged-out tokens are refused."""
    response = client.get("/customers", headers={"Authorization": ""})
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["code"] == "unauthenticated"
    assert me(client, "made-up").status_code == HTTPStatus.UNAUTHORIZED

    _ = make_user(database, "ayse", {Role.STAFF})
    expired = login(client, "ayse")
    sql(database, "UPDATE identity.sessions SET expires_at = now()")
    assert me(client, expired).status_code == HTTPStatus.UNAUTHORIZED

    token = login(client, "ayse")
    logout = client.post("/auth/logout", headers=bearer(token))
    assert logout.status_code == HTTPStatus.NO_CONTENT
    assert me(client, token).status_code == HTTPStatus.UNAUTHORIZED


def test_deactivated_user_is_refused(client: TestClient, database: Database) -> None:
    """Even a live token stops working once the user is deactivated."""
    _ = make_user(database, "ayse", {Role.STAFF})
    token = login(client, "ayse")
    sql(database, "UPDATE identity.users SET active = false WHERE username = 'ayse'")
    response = me(client, token)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert "deactivated" in response.json()["detail"]
    assert attempt(client, "ayse", CREDENTIAL).status_code == HTTPStatus.UNAUTHORIZED


def test_last_used_is_refreshed(client: TestClient, database: Database) -> None:
    """Using a token updates when it was last used (at most once a minute)."""
    user = make_user(database, "ayse", {Role.STAFF})
    token = login(client, "ayse")
    sql(
        database,
        "UPDATE identity.sessions SET last_used_at = now() - interval '1 hour'",
    )
    assert me(client, token).status_code == HTTPStatus.OK
    response = client.get(f"/users/{user.id}/sessions")
    [live] = SESSIONS.validate_json(response.content)
    assert datetime.now(UTC) - live.last_used_at < timedelta(minutes=1)


def test_push_tokens_follow_the_phone(client: TestClient, database: Database) -> None:
    """A phone's token moves to its newest login and stops at logout."""
    driver = make_user(database, "ali", {Role.DRIVER})
    _ = make_user(database, "ayse", {Role.STAFF})
    phone = {"platform": "android", "client_name": "Pixel", "fcm_token": "fcm-1"}
    old = LoginResult.model_validate_json(
        attempt(client, "ali", CREDENTIAL, **phone).content
    ).token
    new = LoginResult.model_validate_json(
        attempt(client, "ali", CREDENTIAL, **phone).content
    ).token
    staff_phone: dict[str, object] = {"fcm_token": "fcm-staff"}
    _ = attempt(client, "ayse", CREDENTIAL, **staff_phone)

    def targets() -> list[tuple[object, str]]:
        async def run() -> list[identity.PushTarget]:
            async with database.transaction() as session:
                return await identity.push_targets(session, Role.DRIVER)

        return [(t.user_id, t.fcm_token) for t in asyncio.run(run())]

    assert targets() == [(driver.id, "fcm-1")]
    sessions = SESSIONS.validate_json(
        client.get(f"/users/{driver.id}/sessions").content
    )
    assert [s.has_push_token for s in sessions] == [True, False]

    put = client.put(
        "/auth/me/push-token", json={"fcm_token": "fcm-2"}, headers=bearer(old)
    )
    assert put.status_code == HTTPStatus.NO_CONTENT
    assert targets() == [(driver.id, "fcm-2"), (driver.id, "fcm-1")]
    _ = client.put("/auth/me/push-token", json={"fcm_token": None}, headers=bearer(old))
    assert targets() == [(driver.id, "fcm-1")]

    _ = client.put(
        "/auth/me/push-token", json={"fcm_token": "fcm-3"}, headers=bearer(new)
    )
    _ = client.post("/auth/logout", headers=bearer(new))
    assert targets() == []


def test_change_own_password(client: TestClient, database: Database) -> None:
    """Changing your password keeps this login and ends the others."""
    _ = make_user(database, "ayse", {Role.STAFF})
    other = login(client, "ayse")
    token = login(client, "ayse")
    url = "/auth/me/password"
    wrong = client.put(
        url,
        json={"current_password": WRONG, "new_password": "a much better one"},
        headers=bearer(token),
    )
    assert wrong.status_code == HTTPStatus.UNAUTHORIZED
    short = client.put(
        url,
        json={"current_password": CREDENTIAL, "new_password": "short"},
        headers=bearer(token),
    )
    assert short.status_code == HTTPStatus.UNPROCESSABLE_CONTENT

    done = client.put(
        url,
        json={"current_password": CREDENTIAL, "new_password": "a much better one"},
        headers=bearer(token),
    )
    assert done.status_code == HTTPStatus.NO_CONTENT
    assert me(client, token).status_code == HTTPStatus.OK
    assert me(client, other).status_code == HTTPStatus.UNAUTHORIZED
    assert attempt(client, "ayse", "a much better one").status_code == HTTPStatus.OK
