# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Identifiers for entities and events.

IDs are UUIDv7: they can be generated anywhere (including offline on a
driver's phone) without asking the database, and they sort by creation
time, which keeps database indexes compact.
"""

from uuid import UUID, uuid7

type EntityId = UUID
"""The identifier of any entity. Modules refer to each other's data by ID."""


def new_id() -> EntityId:
    """Generate a new time-ordered identifier.

    Returns:
        A fresh UUIDv7.
    """
    return uuid7()
