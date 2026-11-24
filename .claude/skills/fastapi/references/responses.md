# Responses

## Declare a return type

The return type is used to validate, filter, document and serialize the
response, with serialization done on the Rust side by Pydantic. It doesn't
have to be a model: `list[int]`, `dict[str, str]` and so on work too.

```python
class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me")
def get_item() -> Item:
    return Item(name="Plumbus", description="All-purpose home device")
```

## When to use `response_model`

Use `response_model=` when what you return isn't the public schema, for
example to strip internal or secret fields. The response is filtered through
`response_model`, so declare the real internal type as the return annotation.

The upstream guide annotates these functions `-> Any`; this project bans
`Any`, so use the actual type instead:

```python
class InternalItem(BaseModel):
    name: str
    description: str | None = None
    secret_key: str


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me", response_model=Item)
def get_item() -> InternalItem:
    return InternalItem(name="Foo", description="A very nice Item", secret_key="...")
```

The client only receives `name` and `description`.

Don't use `ORJSONResponse` or `UJSONResponse`; they're deprecated.
