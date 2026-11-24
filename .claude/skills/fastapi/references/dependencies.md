# Dependency Injection

Use a dependency when the logic:

- can't be expressed as Pydantic validation,
- depends on external resources or could block,
- is needed by other dependencies (sub-dependency),
- is shared across endpoints (auth, early errors, etc.),
- needs cleanup (DB sessions, file handles) via `yield`,
- needs request data (headers, query parameters, etc.).

Apply shared dependencies at the router level with
`APIRouter(dependencies=[Depends(...)])`.

## `yield` and `scope`

With the default scope `"request"`, the code after `yield` runs after the
response has been sent:

```python
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends


def get_db() -> Iterator[DBSession]:
    db = DBSession()
    try:
        yield db
    finally:
        db.close()


DBDep = Annotated[DBSession, Depends(get_db)]
```

Use `scope="function"` to run the cleanup after the response data is
generated but before it is sent to the client:

```python
def get_username() -> Iterator[str]:
    try:
        yield "Rick"
    finally:
        logger.info("Clean up before the response is sent")


UserNameDep = Annotated[str, Depends(get_username, scope="function")]
```

## Limit dependency concurrency

Use `max_concurrency` when concurrent calls could exhaust a shared resource
such as a connection pool:

```python
DBDep = Annotated[DBSession, Depends(get_db, max_concurrency=5)]
```

- Put the limit on the dependency that owns the resource; its
  sub-dependencies run before the limit applies.
- Pick the number from the resource's real capacity, leaving room for other
  users of it. FastAPI doesn't detect pool sizes. `None` (default) means no limit.
- Declare one `Annotated` alias and reuse it. Every new `Depends()` object is
  a separate limit, even for the same function.
- Waiting calls don't occupy worker threads. With `yield`, the slot is held
  until cleanup finishes (timing set by `scope`); without it, until the
  function returns.
- The limit is per worker process; account for this with several workers.
- Before limiting nested resource dependencies, check a request can't hold
  one slot while waiting for another. See
  https://fastapi.tiangolo.com/advanced/advanced-dependencies/#dependencies-that-need-more-than-one-resource

## Function dependencies over class dependencies

Avoid using a class directly as a dependency (`Depends()` with no argument on
a class). Write a function that returns the instance:

```python
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends


@dataclass
class Paginator:
    offset: int = 0
    limit: int = 100
    q: str | None = None


def get_paginator(offset: int = 0, limit: int = 100, q: str | None = None) -> Paginator:
    return Paginator(offset=offset, limit=limit, q=q)


PaginatorDep = Annotated[Paginator, Depends(get_paginator)]
```

Not this:

```python
# DO NOT DO THIS
@app.get("/items/")
def read_items(paginator: Annotated[Paginator, Depends()]) -> Page: ...
```
