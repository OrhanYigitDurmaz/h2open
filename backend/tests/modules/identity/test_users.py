# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for user administration, permissions and the command-line tool."""

import runpy
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from app import cli
from app.core.ids import new_id
from app.modules.identity.api import Actor, Role, UserView
from tests.modules.auth import CREDENTIAL, bearer, login, make_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database

USERS = TypeAdapter(list[UserView])
FRESH_CREDENTIAL = "brand new passphrase"


def test_admin_manages_users(client: TestClient) -> None:
    """Admins add, list, rename, re-role and deactivate users."""
    response = client.post(
        "/users",
        json={
            "username": "Ali.Driver",
            "name": "Ali",
            "password": FRESH_CREDENTIAL,
            "roles": ["driver", "staff"],
        },
    )
    assert response.status_code == HTTPStatus.CREATED
    ali = UserView.model_validate_json(response.content)
    assert (ali.username, ali.roles) == ("ali.driver", [Role.STAFF, Role.DRIVER])

    names = [u.username for u in USERS.validate_json(client.get("/users").content)]
    assert names == ["admin", "ali.driver"]

    token = login(client, "ali.driver", FRESH_CREDENTIAL)
    response = client.patch(
        f"/users/{ali.id}", json={"name": "Ali Kaya", "roles": ["driver"]}
    )
    updated = UserView.model_validate_json(response.content)
    assert (updated.name, updated.roles) == ("Ali Kaya", [Role.DRIVER])
    assert client.get("/auth/me", headers=bearer(token)).status_code == HTTPStatus.OK

    response = client.patch(f"/users/{ali.id}", json={"active": False})
    assert UserView.model_validate_json(response.content).active is False
    assert client.get("/auth/me", headers=bearer(token)).status_code == (
        HTTPStatus.UNAUTHORIZED
    )
    reactivated = client.patch(f"/users/{ali.id}", json={"active": True})
    assert UserView.model_validate_json(reactivated.content).active is True


def test_user_errors(client: TestClient) -> None:
    """Taken usernames conflict; bad input is rejected; unknown users 404."""
    body = {
        "username": "admin",
        "name": "X",
        "password": FRESH_CREDENTIAL,
        "roles": ["staff"],
    }
    assert client.post("/users", json=body).status_code == HTTPStatus.CONFLICT
    bad_inputs: list[dict[str, object]] = [
        {"username": "a b"},
        {"username": "ab"},
        {"password": "too short"},
        {"roles": []},
        {"roles": ["owner"]},
    ]
    for bad in bad_inputs:
        response = client.post("/users", json={**body, "username": "new", **bad})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT, bad
    missing = new_id()
    assert (
        client.patch(f"/users/{missing}", json={}).status_code == HTTPStatus.NOT_FOUND
    )
    assert (
        client.put(
            f"/users/{missing}/password", json={"new_password": FRESH_CREDENTIAL}
        ).status_code
        == HTTPStatus.NOT_FOUND
    )
    assert client.get(f"/users/{missing}/sessions").status_code == HTTPStatus.NOT_FOUND


def test_last_admin_cannot_be_removed(client: TestClient, database: Database) -> None:
    """There is always at least one active admin."""
    admin = Actor.model_validate_json(client.get("/auth/me").content).user
    for change in ({"active": False}, {"roles": ["staff"]}):
        response = client.patch(f"/users/{admin.id}", json=change)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
        assert "at least one active admin" in response.json()["detail"]

    _ = make_user(database, "second", {Role.ADMIN})
    response = client.patch(f"/users/{admin.id}", json={"roles": ["staff"]})
    assert response.status_code == HTTPStatus.OK


def test_admin_resets_a_password(client: TestClient, database: Database) -> None:
    """A reset sets the new password, unlocks, and ends every login."""
    user = make_user(database, "ayse", {Role.STAFF})
    token = login(client, "ayse")
    response = client.put(
        f"/users/{user.id}/password", json={"new_password": FRESH_CREDENTIAL}
    )
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert client.get("/auth/me", headers=bearer(token)).status_code == (
        HTTPStatus.UNAUTHORIZED
    )
    _ = login(client, "ayse", FRESH_CREDENTIAL)


@pytest.mark.parametrize(
    "call",
    [
        ("GET", "/users", None),
        ("POST", "/catalog/brands", {"name": "Brand X"}),
        ("PATCH", "/company/settings", {"walk_in_sales_enabled": False}),
    ],
)
def test_staff_cannot_administer(
    client: TestClient,
    database: Database,
    call: tuple[str, str, dict[str, object] | None],
) -> None:
    """Users, catalog changes and settings are for admins only."""
    _ = make_user(database, "ayse", {Role.STAFF, Role.DRIVER})
    headers = bearer(login(client, "ayse"))
    method, url, body = call
    response = client.request(method, url, json=body, headers=headers)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["code"] == "forbidden"


def test_staff_can_work(client: TestClient, database: Database) -> None:
    """Everyone logged in can read the catalog and handle customers."""
    _ = make_user(database, "ayse", {Role.STAFF})
    headers = bearer(login(client, "ayse"))
    assert client.get("/catalog/products", headers=headers).status_code == HTTPStatus.OK
    assert client.get("/company/settings", headers=headers).status_code == HTTPStatus.OK
    created = client.post("/customers", json={"name": "Walk-in Ltd"}, headers=headers)
    assert created.status_code == HTTPStatus.CREATED


# Command-line tool


def run_cli(
    monkeypatch: pytest.MonkeyPatch, args: list[str], passwords: tuple[str, str]
) -> int:
    """Run the CLI with the two password prompts answered.

    Returns:
        The exit code.
    """
    answers = iter(passwords)
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(answers))
    return cli.main(args)


ARGS = ["create-user", "--username", "boss", "--name", "The Boss", "--role", "admin"]


@pytest.mark.usefixtures("database")
def test_cli_creates_the_first_admin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first admin is created on the server, password asked twice."""
    code = run_cli(monkeypatch, [*ARGS, "--role", "staff"], (CREDENTIAL, CREDENTIAL))
    assert code == 0
    assert capsys.readouterr().out == "created boss (admin, staff)\n"

    code = run_cli(monkeypatch, ARGS, (CREDENTIAL, CREDENTIAL))
    assert code == 1
    assert "taken" in capsys.readouterr().err


@pytest.mark.usefixtures("database")
def test_cli_rejects_bad_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mismatched or weak passwords are refused with a clear message."""
    assert run_cli(monkeypatch, ARGS, (CREDENTIAL, "different")) == 1
    assert "do not match" in capsys.readouterr().err
    assert run_cli(monkeypatch, ARGS, ("short", "short")) == 1
    assert "password" in capsys.readouterr().err


@pytest.mark.usefixtures("database")
# runpy warns because the test module already imported app.cli; harmless here.
@pytest.mark.filterwarnings("ignore:'app.cli' found in sys.modules:RuntimeWarning")
def test_cli_runs_as_a_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """``python -m app.cli`` exits with the command's exit code."""
    answers = iter((CREDENTIAL, CREDENTIAL))
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(answers))
    monkeypatch.setattr("sys.argv", ["app.cli", *ARGS])
    with pytest.raises(SystemExit) as exit_info:
        _ = runpy.run_module("app.cli", run_name="__main__", alter_sys=True)
    assert exit_info.value.code == 0
