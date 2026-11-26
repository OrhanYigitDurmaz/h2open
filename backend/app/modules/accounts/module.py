# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the accounts module plugs into the application."""

from app.core.app import Module
from app.modules.accounts._models import Base
from app.modules.accounts._router import router

MODULE = Module(name="accounts", router=router, metadata=Base.metadata)
