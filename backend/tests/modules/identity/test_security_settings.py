# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the adjustable login rules."""

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.api import LoginResult, Role, SecuritySettingsView
from tests.modules.auth import CREDENTIAL, bearer, login, make_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

URL = "/security/settings"
WRONG = "not the right one"
HOUR = 60


def settings(client: TestClient, **changes: object) -> SecuritySettingsView:
    """Change the login rules.

    Returns:
        The rules afterwards.
    """
    response = client.patch(URL, json=changes)
    assert response.status_code == HTTPStatus.OK, response.text
    return SecuritySettingsView.model_validate_json(response.content)


def test_defaults(client: TestClient) -> None:
    """30-day logins; five failures lock for 15 minutes."""
    response = client.get(URL)
    assert SecuritySettingsView.model_validate_json(response.content) == (
        SecuritySettingsView(
            session_lifetime_days=30, max_failed_logins=5, lockout_minutes=15
        )
    )


def test_admin_changes_the_rules(client: TestClient) -> None:
    """Each rule changes on its own; an empty update keeps them."""
    changed = settings(client, session_lifetime_days=7, max_failed_logins=3)
    assert (changed.session_lifetime_days, changed.max_failed_logins) == (7, 3)
    changed = settings(client, lockout_minutes=HOUR)
    assert (changed.lockout_minutes, changed.session_lifetime_days) == (HOUR, 7)
    assert settings(client) == changed
    stored = client.get(URL)
    assert SecuritySettingsView.model_validate_json(stored.content) == changed


@pytest.mark.parametrize(
    "bad",
    [
        {"session_lifetime_days": 0},
        {"session_lifetime_days": 366},
        {"max_failed_logins": 2},
        {"lockout_minutes": 0},
    ],
)
def test_out_of_range_rules(client: TestClient, bad: dict[str, object]) -> None:
    """Rules stay within sensible limits."""
    assert client.patch(URL, json=bad).status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_new_logins_use_the_lifetime(client: TestClient, database: Database) -> None:
    """A shorter lifetime applies to the next login."""
    _ = settings(client, session_lifetime_days=1)
    _ = make_user(database, "ayse", {Role.STAFF})
    response = client.post(
        "/auth/login", json={"username": "ayse", "password": CREDENTIAL}
    )
    expires = LoginResult.model_validate_json(response.content).expires_at
    assert expires - datetime.now(UTC) < timedelta(days=1)


def test_lockout_follows_the_rules(client: TestClient, database: Database) -> None:
    """Three failures lock when the limit is three."""
    _ = settings(client, max_failed_logins=3)
    _ = make_user(database, "ayse", {Role.STAFF})
    for _ in range(3):
        _ = client.post("/auth/login", json={"username": "ayse", "password": WRONG})
    locked = client.post(
        "/auth/login", json={"username": "ayse", "password": CREDENTIAL}
    )
    assert locked.status_code == HTTPStatus.UNAUTHORIZED


def test_staff_cannot_see_or_change_rules(
    client: TestClient, database: Database
) -> None:
    """Login rules are for admins only."""
    _ = make_user(database, "ayse", {Role.STAFF})
    headers = bearer(login(client, "ayse"))
    assert client.get(URL, headers=headers).status_code == HTTPStatus.FORBIDDEN
    patch = client.patch(URL, json={"lockout_minutes": 1}, headers=headers)
    assert patch.status_code == HTTPStatus.FORBIDDEN
