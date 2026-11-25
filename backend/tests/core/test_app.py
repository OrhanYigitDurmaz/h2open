# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for application assembly and error handling."""

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.app import DuplicateModuleError, Module, create_app
from app.core.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    OverrideRequiredError,
)
from app.core.events import EventBus

if TYPE_CHECKING:
    from app.core.db import Database

router = APIRouter(prefix="/demo")


@router.get("/missing")
def missing() -> None:
    """Raise a not-found error.

    Raises:
        NotFoundError: Always.
    """
    msg = "order S-1 not found"
    raise NotFoundError(msg)


@router.get("/conflict")
def conflict() -> None:
    """Raise a conflict error.

    Raises:
        ConflictError: Always.
    """
    msg = "order S-1 was changed by someone else"
    raise ConflictError(msg)


@router.get("/override")
def override() -> None:
    """Raise an override-required error.

    Raises:
        OverrideRequiredError: Always.
    """
    msg = "brand mismatch"
    raise OverrideRequiredError(msg)


@router.get("/rule")
def rule() -> None:
    """Raise a generic business rule error.

    Raises:
        DomainError: Always.
    """
    msg = "cannot confirm an empty order"
    raise DomainError(msg)


def test_modules_are_wired_in(database: Database) -> None:
    """A module's router is mounted and its subscribe hook gets the bus."""
    bus = EventBus()
    subscribed: list[EventBus] = []
    app = create_app(
        [Module(name="demo", router=router, subscribe=subscribed.append)],
        event_bus=bus,
        database=database,
    )
    assert subscribed == [bus]
    client = TestClient(app)
    response = client.get("/demo/missing")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"code": "not_found", "detail": "order S-1 not found"}


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/demo/conflict", HTTPStatus.CONFLICT, "conflict"),
        ("/demo/override", HTTPStatus.CONFLICT, "override_required"),
        ("/demo/rule", HTTPStatus.UNPROCESSABLE_CONTENT, "business_rule_violated"),
    ],
)
def test_domain_errors_map_to_responses(
    path: str, status: HTTPStatus, code: str, database: Database
) -> None:
    """Each domain error type has its own status and code."""
    app = create_app(
        [Module(name="demo", router=router)], event_bus=EventBus(), database=database
    )
    client = TestClient(app)
    response = client.get(path)
    assert response.status_code == status
    assert response.json()["code"] == code


def test_module_without_router_or_handlers(database: Database) -> None:
    """A module may contribute nothing yet."""
    app = create_app([Module(name="empty")], event_bus=EventBus(), database=database)
    assert TestClient(app).get("/health").status_code == HTTPStatus.OK


def test_duplicate_module_names_are_rejected(database: Database) -> None:
    """Two modules cannot share a name."""
    with pytest.raises(DuplicateModuleError, match="'demo'"):
        _ = create_app(
            [Module(name="demo"), Module(name="demo")],
            event_bus=EventBus(),
            database=database,
        )
