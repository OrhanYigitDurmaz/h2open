# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the notifications module plugs into the application."""

from app.core.app import Module
from app.modules.notifications._handlers import subscribe
from app.modules.notifications._router import router

MODULE = Module(name="notifications", router=router, subscribe=subscribe)
