---
name: fastapi
description: FastAPI and Pydantic conventions for the h2open backend. Use when writing or reviewing FastAPI code in backend/, including path operations, routers, dependencies, Pydantic models, request/response types, request body limits and streaming (JSON Lines, SSE, bytes).
---

# FastAPI in h2open

Adapted from the official FastAPI agent skill bundled with FastAPI 0.165.0
(MIT, © Sebastián Ramírez; see `LICENSE-fastapi`). Changes from the original:
examples rewritten to pass this project's strict ruff and basedpyright
settings, FastAPI Cloud and `ty` guidance removed, and project rules added.

## Project rules come first

Code in `backend/` must pass `/verify`: ruff `select = ["ALL"]` (preview),
basedpyright `typeCheckingMode = "all"`, pytest with 100% branch coverage.
In practice:

- Every file starts with the two-line copyright and SPDX header.
- Every module, class and public function has a Google-style docstring
  (`Args:`, `Returns:`, `Raises:` where they apply).
- Every parameter and return value is annotated. No bare `dict` or `list`;
  use `dict[str, str]`, a Pydantic model, or a `TypedDict`.
- No `Any`. Where the upstream guide uses `-> Any`, use the real internal type.
- Every new endpoint gets tests that cover all its branches.
- Type checking is basedpyright, not `ty`. Deployment is this repo's own
  Docker setup, not FastAPI Cloud.
- Ask before adding a new dependency (including the libraries suggested in
  [the libraries reference](references/libraries.md)).

The examples below omit the copyright header and docstrings to stay short.
Real code needs both.

## Quick reference

- Parameters and dependencies: `Annotated[...]`, never `...` (Ellipsis) as a default.
  See [the Pydantic reference](references/pydantic.md).
- Dependencies: `Annotated[T, Depends(fn)]` aliases; `yield` with `scope`,
  `max_concurrency`, function dependencies over class dependencies.
  See [the dependency reference](references/dependencies.md).
- Responses: declare a return type; use `response_model` only when the public
  schema differs from what you return. See [the response reference](references/responses.md).
- Parameter models: group query/header/cookie/form inputs into models.
  See [the parameter models reference](references/parameter-models.md).
- Routing: prefix, tags and shared dependencies go on the `APIRouter`; one HTTP
  method per function. See [the path operation reference](references/path-operations.md).
- Request body limits: `max_body_size` and `form_limits` (FastAPI >= 0.165.0).
- Streaming: return type plus `yield`; SSE via `EventSourceResponse`.
  See [the streaming reference](references/streaming.md).
- API clients for the frontend: generate them from the OpenAPI schema and
  regenerate when the API changes; don't hand-edit generated files.

## Run the app with the `fastapi` CLI

```bash
uv run fastapi dev app/main.py   # development, with reload
uv run fastapi run app/main.py   # production
```

Upstream prefers declaring the entrypoint once in `pyproject.toml`
(`[tool.fastapi] entrypoint = "app.main:app"`) so the path can be dropped.
Suggest it if it isn't there yet; don't add it silently.

## Use `Annotated`

Use `Annotated` for every parameter declaration (`Path`, `Query`, `Header`,
`Cookie`, `Body`, `Form`, `File`) and every dependency. It keeps signatures
usable outside FastAPI and lets types be reused.

```python
from typing import Annotated

from fastapi import FastAPI, Path, Query
from pydantic import BaseModel

app = FastAPI()


class ItemOut(BaseModel):
    item_id: int
    q: str | None


@app.get("/items/{item_id}")
def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
) -> ItemOut:
    return ItemOut(item_id=item_id, q=q)
```

For dependencies, create a reusable type alias:

```python
from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import BaseModel

app = FastAPI()


class User(BaseModel):
    username: str


def get_current_user() -> User:
    return User(username="johndoe")


CurrentUserDep = Annotated[User, Depends(get_current_user)]


@app.get("/users/me")
def read_me(current_user: CurrentUserDep) -> User:
    return current_user
```

## No Ellipsis

Don't use `...` as a default for required parameters or model fields. A field
without a default is already required: `name: str`, `Field(gt=0)`,
`Annotated[int, Query()]`.

## Return types over `response_model`

Declare a return type. FastAPI uses it to validate, filter, document and
serialize the response, and Pydantic serializes on the Rust side. Use
`response_model=` only when the public schema differs from the internal
object you return (for example, to strip secret fields).

Don't use `ORJSONResponse` or `UJSONResponse`; they're deprecated and a
declared return type is faster anyway.

## Routers

Put `prefix`, `tags` and shared `dependencies` on the `APIRouter` itself, not
in `include_router()`. One function per HTTP method; never
`@app.api_route(methods=[...])` with branching on `request.method`.

## Request body limits (FastAPI >= 0.165.0)

Without a configured limit, request bodies are unlimited. Set a default on
the app and raise or lower it per router or path operation:

```python
app = FastAPI(max_body_size=1 * 1024 * 1024)  # 1 MiB default
uploads = APIRouter(prefix="/uploads", max_body_size=100 * 1024 * 1024)
```

- The limit covers the whole body, including files and multipart overhead,
  and counts bytes actually received (a `Content-Length` check is not a
  substitute). Oversized requests get `413 Content Too Large`.
- `None` inherits from the router or app; `0` allows only an empty body.
- Middleware that reads the body before routing is bound by the app limit,
  even if the endpoint allows more.
- `form_limits` with `max_fields`, `max_files`, `max_part_size` limits form
  parsing; each key inherits independently. `max_part_size` applies to text
  fields; use `max_body_size` for a total limit that includes files.

If the installed FastAPI is older than 0.165.0, these parameters don't exist;
check `uv tree --depth 1` before using them.

## Async vs sync

Use `async def` only when everything awaited inside is truly non-blocking.
When in doubt, use plain `def`: FastAPI runs it in a threadpool so it won't
block the event loop. The same applies to dependencies. Never call blocking
code (file I/O, `requests`, sync DB drivers, `time.sleep`) inside `async def`.

## Pydantic: no `RootModel`

Use plain annotated types instead of `RootModel`; FastAPI wraps them in a
`TypeAdapter` automatically:

```python
@app.post("/items/")
def create_items(
    items: Annotated[list[int], Field(min_length=1), Body()],
) -> list[int]:
    return items
```

## Serving built frontend assets

`app.frontend("/", directory="dist")` and `router.frontend(...)` serve a
static build with SPA fallback, at lower priority than API routes; prefer
them over mounting `StaticFiles`. Note: h2open's frontend currently uses
`@sveltejs/adapter-bun` and runs its own server, so this only applies if it
switches to a static build.

## OpenTelemetry

Prefer FastAPI's native OpenTelemetry support (included in
`fastapi[standard]`). Enable automatic setup with
`FASTAPI_OTEL_AUTO_CONFIGURE=true` and set `OTEL_SERVICE_NAME` and
`OTEL_EXPORTER_OTLP_ENDPOINT` (plus `OTEL_EXPORTER_OTLP_HEADERS` if the
collector needs auth). For custom setup use `FastAPI(telemetry={...})`.
See https://fastapi.tiangolo.com/advanced/opentelemetry/.
