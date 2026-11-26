# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the inventory module plugs into the application."""

from app.core.app import Module
from app.modules.inventory._models import Base
from app.modules.inventory._router import router

MODULE = Module(name="inventory", router=router, metadata=Base.metadata)
