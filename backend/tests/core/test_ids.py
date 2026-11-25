# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for identifiers."""

from app.core.ids import new_id

UUID_VERSION_7 = 7


def test_new_id_is_uuid7() -> None:
    """IDs are version 7 UUIDs."""
    assert new_id().version == UUID_VERSION_7


def test_new_ids_sort_by_creation() -> None:
    """Later IDs sort after earlier ones."""
    ids = [new_id() for _ in range(100)]
    assert ids == sorted(ids)
