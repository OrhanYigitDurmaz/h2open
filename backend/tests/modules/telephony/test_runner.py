# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for staying connected to Asterisk."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from websockets.exceptions import InvalidHandshake

from app.core.ari import AriConnection, AriError
from app.modules.telephony import api as telephony
from tests.modules.telephony.fakes import FakeAri, started

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.core.ari import AriEvent
    from app.core.db import Database


CREDENTIAL = "from-the-env"
ATTEMPTS = 4
"""Three failures, then one connection that closes normally."""


class StopError(Exception):
    """Ends the runner's loop in a test."""


@dataclass
class FlakyAsterisk(FakeAri):
    """Drops the connection in each way it can, ends once, then stops."""

    failures: list[Exception] = field(
        default_factory=lambda: [OSError("refused"), InvalidHandshake(), AriError("x")]
    )
    follows: int = 0
    connected_to: list[AriConnection] = field(default_factory=list)

    async def follow(self, handle: Callable[[AriEvent], Awaitable[None]]) -> None:
        """Fail, then deliver one event and close, then stop the test.

        Raises:
            StopError: When every case has been tried.
        """
        self.follows += 1
        if self.failures:
            raise self.failures.pop(0)
        if self.follows == ATTEMPTS:
            await handle(started("stray", "nothing"))
            return
        raise StopError


def test_phone_calls_are_off_without_credentials(
    database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests (and deployments without Asterisk) skip call handling."""
    assert telephony.connection() is None
    with caplog.at_level(logging.WARNING):
        asyncio.run(telephony.run_calls(database))
    assert "phone calls are off" in caplog.text


def test_reconnects_whatever_goes_wrong(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Refused, bad handshake, ARI errors or a closed stream: try again."""
    monkeypatch.setenv("ARI_USERNAME", "h2open")
    monkeypatch.setenv("ARI_PASSWORD", CREDENTIAL)
    where = telephony.connection()
    assert where == AriConnection(
        url="http://127.0.0.1:8088",
        username="h2open",
        password=CREDENTIAL,
        app=telephony.APP,
    )
    asterisk = FlakyAsterisk()

    def connect(connection: AriConnection) -> FlakyAsterisk:
        asterisk.connected_to.append(connection)
        return asterisk

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(StopError),
    ):
        asyncio.run(telephony.run_calls(database, connect=connect, pause=0))
    assert asterisk.connected_to == [where]
    assert asterisk.follows == ATTEMPTS + 1
    assert caplog.text.count("lost Asterisk") == ATTEMPTS - 1
    assert "closed the event stream" in caplog.text
    assert asterisk.take() == [("hangup", "stray")]
