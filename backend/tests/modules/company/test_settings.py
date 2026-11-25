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
        deposit_refund_policy=DepositRefundPolicy.PAID_AMOUNT
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


def test_unknown_policy_is_rejected(client: TestClient) -> None:
    """Only the three policies are accepted."""
    response = client.patch("/company/settings", json={"deposit_refund_policy": "half"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
