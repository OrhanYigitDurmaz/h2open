# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keeping the backend connected to Asterisk. Private to this module."""

import asyncio
import logging
from typing import TYPE_CHECKING

from websockets.exceptions import WebSocketException

from app.core.ari import AriClient, AriConnection, AriError, Asterisk
from app.core.settings import load_settings
from app.modules.telephony._controller import CallController

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.db import Database

logger = logging.getLogger(__name__)

APP = "h2open"
"""Our Stasis application; the dialplan sends calls to Stasis(h2open,...)."""


def connection() -> AriConnection | None:
    """Where Asterisk is, from the settings.

    Returns:
        The connection, or ``None`` if ARI credentials are not set.
    """
    settings = load_settings()
    if settings.ari_username is None or settings.ari_password is None:
        return None
    return AriConnection(
        url=settings.ari_url,
        username=settings.ari_username,
        password=settings.ari_password.get_secret_value(),
        app=APP,
    )


async def run_calls(
    database: Database,
    *,
    connect: Callable[[AriConnection], Asterisk] = AriClient,
    pause: float = 5.0,
) -> None:
    """Handle calls for as long as the app runs, reconnecting when needed.

    Args:
        database: Where calls are logged.
        connect: Makes the ARI client; tests replace it.
        pause: Seconds to wait before reconnecting.
    """
    where = connection()
    if where is None:
        logger.warning("phone calls are off: ARI_USERNAME/ARI_PASSWORD not set")
        return
    client = connect(where)
    controller = CallController(database, client)
    while True:
        await controller.start()
        try:
            await client.follow(controller.handle)
            logger.warning("Asterisk closed the event stream; reconnecting")
        except OSError, WebSocketException, AriError:
            logger.exception("lost Asterisk at %s; reconnecting", where.url)
        await asyncio.sleep(pause)
