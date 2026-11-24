# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the health endpoint."""

from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """The health endpoint returns 200 with an ok status."""
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}
