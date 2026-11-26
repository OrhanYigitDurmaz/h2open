# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the purchasing module plugs into the application."""

from app.core.app import Module
from app.modules.purchasing._models import Base
from app.modules.purchasing._router import router

MODULE = Module(name="purchasing", router=router, metadata=Base.metadata)
