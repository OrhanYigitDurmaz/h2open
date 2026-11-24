"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="h2open")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the service is up."""
    return {"status": "ok"}
