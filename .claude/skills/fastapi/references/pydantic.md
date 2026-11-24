# Pydantic

## No Ellipsis

A parameter or field without a default is already required. Don't write `...`:

```python
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float = Field(gt=0)


@app.post("/items/")
def create_item(item: Item, project_id: Annotated[int, Query()]) -> Item:
    return item
```

Not this:

```python
# DO NOT DO THIS
class Item(BaseModel):
    name: str = ...
    price: float = Field(..., gt=0)


@app.post("/items/")
def create_item(item: Item, project_id: Annotated[int, Query(...)]) -> Item: ...
```

## No `RootModel`

Use annotated types with Pydantic validation instead. FastAPI creates a
`TypeAdapter` for them, so no wrapper model is needed:

```python
from typing import Annotated

from fastapi import Body
from pydantic import Field


@app.post("/items/")
def create_items(
    items: Annotated[list[int], Field(min_length=1), Body()],
) -> list[int]:
    return items
```

Not this:

```python
# DO NOT DO THIS
class ItemList(RootModel[Annotated[list[int], Field(min_length=1)]]):
    pass
```
