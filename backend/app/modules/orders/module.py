# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the orders module plugs into the application."""

from app.core.app import Module
from app.modules.orders._models import Base
from app.modules.orders._router import router

MODULE = Module(name="orders", router=router, metadata=Base.metadata)
