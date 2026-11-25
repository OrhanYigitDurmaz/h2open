# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the catalog plugs into the application."""

from app.core.app import Module
from app.modules.catalog._models import Base
from app.modules.catalog._router import router

MODULE = Module(name="catalog", router=router, metadata=Base.metadata)
