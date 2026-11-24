# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="h2open")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the service is up.

    Returns:
        A status payload, always ``{"status": "ok"}``.
    """
    return {"status": "ok"}
