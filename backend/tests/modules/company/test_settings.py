# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for company settings."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from app.modules.company.api import DepositRefundPolicy, SettingsView

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_defaults_until_changed(client: TestClient) -> None:
    """Before anything is saved, deposits are refunded at the paid amount."""
    response = client.get("/company/settings")
    assert response.status_code == HTTPStatus.OK
    assert SettingsView.model_validate_json(response.content) == SettingsView(
        deposit_refund_policy=DepositRefundPolicy.PAID_AMOUNT,
        walk_in_sales_enabled=True,
        walk_in_deposits_allowed=False,
        negative_stock_allowed=True,
        unclaimed_alert_minutes=15,
        uncompleted_alert_minutes=120,
    )


def test_change_refund_policy(client: TestClient) -> None:
    """The refund policy can be changed; an empty update keeps it."""
    for policy in ("current_price", "none"):
        response = client.patch(
            "/company/settings", json={"deposit_refund_policy": policy}
        )
        assert response.status_code == HTTPStatus.OK
        assert (
            SettingsView.model_validate_json(response.content).deposit_refund_policy
            == policy
        )

    kept = client.patch("/company/settings", json={})
    assert (
        SettingsView.model_validate_json(kept.content).deposit_refund_policy == "none"
    )
    stored = client.get("/company/settings")
    assert (
        SettingsView.model_validate_json(stored.content).deposit_refund_policy == "none"
    )


def test_change_walk_in_limits(client: TestClient) -> None:
    """Walk-in sales and walk-in deposits are switched independently."""
    response = client.patch(
        "/company/settings",
        json={"walk_in_sales_enabled": False, "walk_in_deposits_allowed": True},
    )
    settings = SettingsView.model_validate_json(response.content)
    assert (settings.walk_in_sales_enabled, settings.walk_in_deposits_allowed) == (
        False,
        True,
    )


def test_change_negative_stock(client: TestClient) -> None:
    """Negative stock can be forbidden."""
    response = client.patch("/company/settings", json={"negative_stock_allowed": False})
    assert SettingsView.model_validate_json(
        response.content
    ).negative_stock_allowed is (False)


def test_change_delivery_alerts(client: TestClient) -> None:
    """Both delivery alert thresholds are adjustable, from 1 minute to a day."""
    response = client.patch(
        "/company/settings",
        json={"unclaimed_alert_minutes": 10, "uncompleted_alert_minutes": 90},
    )
    settings = SettingsView.model_validate_json(response.content)
    assert (settings.unclaimed_alert_minutes, settings.uncompleted_alert_minutes) == (
        10,
        90,
    )
    for bad in (0, 1441):
        response = client.patch(
            "/company/settings", json={"unclaimed_alert_minutes": bad}
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_unknown_policy_is_rejected(client: TestClient) -> None:
    """Only the three policies are accepted."""
    response = client.patch("/company/settings", json={"deposit_refund_policy": "half"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
