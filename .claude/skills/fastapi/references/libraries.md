# Related Libraries

These are the upstream guide's library suggestions. Several come from
FastAPI's own author. They're reasonable defaults, but none is installed yet:
suggest them when they fit, and ask before adding any dependency.

## Asyncer: mixing async and blocking code

Upstream prefers Asyncer over raw AnyIO, asyncio or `run_in_threadpool()`.
Install with `uv add asyncer`.

```python
from asyncer import asyncify, syncify


@app.get("/a")
async def read_a() -> Greeting:
    # run blocking code from async code, in a worker thread
    return Greeting(message=await asyncify(do_blocking_work)(name="World"))


@app.get("/b")
def read_b() -> Greeting:
    # run async code from sync code
    return Greeting(message=syncify(do_async_work)(name="World"))
```

## SQLModel: SQL databases

Built on SQLAlchemy and Pydantic, so one model class serves as both the table
and the validation schema. Upstream prefers it over plain SQLAlchemy. Weigh
that against needing SQLAlchemy features SQLModel doesn't expose.

## HTTPX: calling other HTTP APIs

Supports both sync and async. Prefer it over Requests (which is sync only).
HTTPX is already installed as part of `fastapi[standard]`, and FastAPI's
`TestClient` is built on it.
