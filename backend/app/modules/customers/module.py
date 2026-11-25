# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the customers module plugs into the application."""

from app.core.app import Module
from app.modules.customers._models import Base
from app.modules.customers._router import router

MODULE = Module(name="customers", router=router, metadata=Base.metadata)
