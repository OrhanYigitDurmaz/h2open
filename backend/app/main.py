# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application entry point: lists the modules that make up h2open."""

from app.core.app import Module, create_app
from app.core.db import Database
from app.core.events import EventBus
from app.core.settings import load_settings
from app.modules.catalog.module import MODULE as CATALOG
from app.modules.company.module import MODULE as COMPANY
from app.modules.containers.module import MODULE as CONTAINERS
from app.modules.customers.module import MODULE as CUSTOMERS
from app.modules.identity.module import MODULE as IDENTITY
from app.modules.inventory.module import MODULE as INVENTORY
from app.modules.notifications.module import MODULE as NOTIFICATIONS
from app.modules.orders.module import MODULE as ORDERS
from app.modules.purchasing.module import MODULE as PURCHASING
from app.modules.telephony.module import MODULE as TELEPHONY

MODULES: tuple[Module, ...] = (
    IDENTITY,
    CATALOG,
    COMPANY,
    CUSTOMERS,
    INVENTORY,
    CONTAINERS,
    ORDERS,
    PURCHASING,
    TELEPHONY,
    NOTIFICATIONS,
)

event_bus = EventBus()
database = Database.connect(load_settings().database_url)
app = create_app(MODULES, event_bus=event_bus, database=database)
