# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assemble the FastAPI application from modules."""

import asyncio
import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI

from app.core.errors import DomainError, domain_error_handler
from app.core.outbox import Dispatcher, run_forever

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Sequence

    from sqlalchemy import MetaData

    from app.core.db import AppState, Database
    from app.core.events import EventBus


@dataclass(frozen=True, slots=True, kw_only=True)
class Module:
    """What a business module contributes to the application.

    Each module package exposes one ``Module`` instance.

    Attributes:
        name: Unique module name, e.g. ``"inventory"``.
        router: The module's HTTP endpoints, if any.
        subscribe: Registers the module's event handlers on the bus.
        metadata: The module's tables, for migrations.
    """

    name: str
    router: APIRouter | None = None
    subscribe: Callable[[EventBus], None] | None = None
    metadata: MetaData | None = None


def health() -> dict[str, str]:
    """Report that the service is up.

    Returns:
        A status payload, always ``{"status": "ok"}``.
    """
    return {"status": "ok"}


class DuplicateModuleError(ValueError):
    """Raised when two modules share a name."""

    def __init__(self, name: str) -> None:
        """Build the error message.

        Args:
            name: The repeated module name.
        """
        super().__init__(f"module {name!r} is registered twice")


def create_app(
    modules: Sequence[Module],
    *,
    event_bus: EventBus,
    database: Database,
    dispatch_events: bool = True,
) -> FastAPI:
    """Build the application and wire every module into it.

    Args:
        modules: The modules to include.
        event_bus: The bus that module handlers subscribe to.
        database: The database; its connections are closed on shutdown.
        dispatch_events: Run the outbox dispatcher in the background while
            the app runs. Tests turn it off and dispatch by hand.

    Returns:
        The configured application.

    Raises:
        DuplicateModuleError: If two modules have the same name.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[AppState]:
        dispatcher: asyncio.Task[None] | None = None
        if dispatch_events:
            dispatcher = asyncio.create_task(
                run_forever(Dispatcher(database, event_bus))
            )
        try:
            yield {"database": database}
        finally:
            if dispatcher is not None:
                _ = dispatcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await dispatcher
            await database.dispose()

    app = FastAPI(title="h2open", lifespan=lifespan)
    # The decorator form accepts a handler typed for DomainError specifically.
    _ = app.exception_handler(DomainError)(domain_error_handler)

    app.add_api_route("/health", health)

    seen: set[str] = set()
    for module in modules:
        if module.name in seen:
            raise DuplicateModuleError(module.name)
        seen.add(module.name)
        if module.router is not None:
            app.include_router(module.router)
        if module.subscribe is not None:
            module.subscribe(event_bus)
    return app
