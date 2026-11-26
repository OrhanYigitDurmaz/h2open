# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the telephony module plugs into the application."""

from app.core.app import Module
from app.modules.telephony._models import Base
from app.modules.telephony._router import router
from app.modules.telephony._runner import run_calls

MODULE = Module(name="telephony", router=router, metadata=Base.metadata, task=run_calls)
