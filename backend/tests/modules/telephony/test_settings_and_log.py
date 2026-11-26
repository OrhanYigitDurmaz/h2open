# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the ring settings and the call log endpoints."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from app.core.ids import new_id
from app.modules.identity.api import Role
from app.modules.telephony.api import RingStrategy, TelephonySettingsView
from tests.modules.auth import bearer, login, make_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.db import Database


def test_defaults_until_changed(client: TestClient) -> None:
    """Shop first, drivers after 15 s, a minute in all, then the message."""
    settings = TelephonySettingsView.model_validate_json(
        client.get("/telephony/settings").content
    )
    assert settings == TelephonySettingsView(
        ring_strategy=RingStrategy.SHOP_FIRST,
        driver_ring_delay_seconds=15,
        ring_timeout_seconds=60,
        shop_endpoints=["PJSIP/desk1", "PJSIP/desk2"],
        driver_endpoint="PJSIP/driver-{username}",
        no_answer_sound="h2open/no-answer",
    )


def test_admins_change_how_calls_ring(client: TestClient) -> None:
    """Every setting can be changed; omitted ones stay; the sound can go."""
    response = client.patch(
        "/telephony/settings",
        json={
            "ring_strategy": "everyone",
            "driver_ring_delay_seconds": 0,
            "ring_timeout_seconds": 45,
            "shop_endpoints": ["PJSIP/desk1"],
            "driver_endpoint": "PJSIP/{username}",
        },
    )
    changed = TelephonySettingsView.model_validate_json(response.content)
    assert (changed.ring_strategy, changed.ring_timeout_seconds) == (
        RingStrategy.EVERYONE,
        45,
    )
    assert changed.no_answer_sound == "h2open/no-answer"
    silent = client.patch("/telephony/settings", json={"no_answer_sound": None})
    assert (
        TelephonySettingsView.model_validate_json(silent.content).no_answer_sound
        is None
    )
    kept = client.patch("/telephony/settings", json={})
    assert TelephonySettingsView.model_validate_json(kept.content).shop_endpoints == [
        "PJSIP/desk1"
    ]


def test_bad_settings_are_refused(client: TestClient, database: Database) -> None:
    """Out-of-range times and odd endpoints are 422; staff cannot change it."""
    bad: list[dict[str, object]] = [
        {"ring_timeout_seconds": 5},
        {"driver_ring_delay_seconds": 301},
        {"shop_endpoints": ["desk1"]},
        {"shop_endpoints": ["PJSIP/desk 1"]},
        # Anything that would dial out through the landline gateway.
        {"shop_endpoints": ["PJSIP/08501234567@mp114"]},
        {"shop_endpoints": ["PJSIP/mp114"]},
        {"driver_endpoint": "Local/08501234567@from-desk"},
        {"driver_endpoint": "SIP/provider/0900"},
        {"no_answer_sound": "../../etc/passwd"},
        {"ring_strategy": "random"},
    ]
    for body in bad:
        response = client.patch("/telephony/settings", json=body)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT, body
    _ = make_user(database, "ayse", {Role.STAFF})
    staff = bearer(login(client, "ayse"))
    assert client.get("/telephony/settings", headers=staff).status_code == HTTPStatus.OK
    response = client.patch("/telephony/settings", json={}, headers=staff)
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_empty_call_log(client: TestClient) -> None:
    """Before any call: empty lists, and unknown calls are 404s."""
    assert client.get("/calls").json() == []
    assert client.get("/calls", params={"status": "missed"}).json() == []
    assert client.get("/calls/active").json() == []
    assert client.get(f"/calls/{new_id()}").status_code == HTTPStatus.NOT_FOUND
