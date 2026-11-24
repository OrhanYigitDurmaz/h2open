# Path Operations and Routing

## Router configuration belongs on the router

Put `prefix`, `tags` and shared `dependencies` on the `APIRouter`, not in
`include_router()`:

```python
from fastapi import APIRouter, Depends, FastAPI

router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/")
def list_items() -> list[Item]:
    return []


app = FastAPI()
app.include_router(router)
```

Not this:

```python
# DO NOT DO THIS
router = APIRouter()
app.include_router(router, prefix="/items", tags=["items"])
```

There can be exceptions, but follow this by default.

## One HTTP method per function

```python
@app.get("/items/")
def list_items() -> list[Item]:
    return []


@app.post("/items/")
def create_item(item: Item) -> Item:
    return item
```

Not this:

```python
# DO NOT DO THIS
@app.api_route("/items/", methods=["GET", "POST"])
async def handle_items(request: Request): ...
```
