# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the company module plugs into the application."""

from app.core.app import Module
from app.modules.company._models import Base
from app.modules.company._router import router

MODULE = Module(name="company", router=router, metadata=Base.metadata)
