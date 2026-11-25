# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application entry point: lists the modules that make up h2open."""

from app.core.app import Module, create_app
from app.core.db import Database
from app.core.events import EventBus
from app.core.settings import load_settings
from app.modules.catalog.module import MODULE as CATALOG

MODULES: tuple[Module, ...] = (CATALOG,)

event_bus = EventBus()
database = Database.connect(load_settings().database_url)
app = create_app(MODULES, event_bus=event_bus, database=database)
