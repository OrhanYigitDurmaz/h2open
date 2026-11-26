# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public interface of the telephony module.

``CallController`` and ``run_calls`` handle live calls; the module runs them
in the background, and tests drive them with a fake Asterisk.
"""

from app.modules.telephony._controller import CallController
from app.modules.telephony._events import DriversRung
from app.modules.telephony._runner import APP, connection, run_calls
from app.modules.telephony._views import (
    CallStatus,
    CallView,
    EndReason,
    RingStrategy,
    TelephonySettingsView,
)

__all__ = [
    "APP",
    "CallController",
    "CallStatus",
    "CallView",
    "DriversRung",
    "EndReason",
    "RingStrategy",
    "TelephonySettingsView",
    "connection",
    "run_calls",
]
