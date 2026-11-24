# Parameter Models

Group related inputs with `Annotated[Model, Query()]`, `Header()`, `Cookie()`
or `Form()`. Several models can sit next to individual parameters and
dependencies. Don't write dependency wrappers just to pack fields into a model.

Each model validates on its own. Request fields stay flat: there are no keys
named after the function parameters.

## Multiple and optional models

```python
from datetime import date
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI()


class Pagination(BaseModel):
    limit: int = Field(10, ge=1)
    offset: int = Field(0, ge=0)


class DateRange(BaseModel):
    start: date
    end: date


@app.get("/items/")
def read_items(
    pagination: Annotated[Pagination, Query()],
    date_range: Annotated[DateRange | None, Query()] = None,
    search: str | None = None,
) -> ItemPage: ...
```

- Make a group optional with `Model | None` **and** `= None`. `| None` alone
  still makes it required.
- With the default `extra="ignore"`, sending neither `start` nor `end` leaves
  `date_range` as `None`, even if `limit` or `search` is sent.
- Sending either field triggers validation and then both are required. Keep
  required fields required when making the group optional.
- The same pattern works with `Header()`, `Cookie()` and `Form()`.

## Extra fields and shared names

A model's `extra` setting applies to every field submitted in the same
location, including sibling parameters and dependencies (and files, for forms).

- `extra="ignore"` (default) lets independent groups coexist.
- `extra="forbid"` rejects sibling fields outside the model.
- `extra="allow"` includes siblings as extras. That makes an optional model
  count as present and triggers its required fields. For header models,
  ordinary headers like `Host` count too.

Shared names or aliases are validated by every model that declares them, so
keep their types and constraints compatible, or use distinct names.

## Forms and unions

Forms need `python-multipart` (included in `fastapi[standard]`). Form models
combine with other form models, single `Form` parameters and `File`
parameters. File uploads need `multipart/form-data`.

Optional discriminated unions work too:
`contact: Annotated[Person | Company | None, Form(discriminator="kind")] = None`,
with a distinct `Literal` value for `kind` in each model.

An empty submitted value counts as supplying the field and is validated.
Omitted booleans use their default or fail as missing; give HTML checkboxes a
`False` default.

Docs: https://fastapi.tiangolo.com/tutorial/query-param-models/ and
https://fastapi.tiangolo.com/tutorial/request-form-models/
