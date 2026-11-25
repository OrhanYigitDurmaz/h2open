# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the containers module plugs into the application."""

from app.core.app import Module
from app.modules.containers._models import Base
from app.modules.containers._router import router

MODULE = Module(name="containers", router=router, metadata=Base.metadata)
