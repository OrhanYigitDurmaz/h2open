# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the identity module plugs into the application."""

from app.core.app import Module
from app.modules.identity._models import Base
from app.modules.identity._router import router

MODULE = Module(name="identity", router=router, metadata=Base.metadata)
