# Streaming

## JSON Lines

Declare the return type and `yield` items:

```python
from collections.abc import AsyncIterable


@app.get("/items/stream")
async def stream_items() -> AsyncIterable[Item]:
    for item in items:
        yield item
```

## Server-Sent Events (SSE)

Use `response_class=EventSourceResponse` and `yield`. Plain objects are
JSON-serialized into `data:` fields; declare the return type so Pydantic does
the serialization:

```python
from collections.abc import AsyncIterable

from fastapi.sse import EventSourceResponse


@app.get("/items/stream", response_class=EventSourceResponse)
async def stream_items() -> AsyncIterable[Item]:
    yield Item(name="Plumbus", price=32.99)
```

For full control over SSE fields (`event`, `id`, `retry`, `comment`), yield
`ServerSentEvent`:

```python
from fastapi.sse import EventSourceResponse, ServerSentEvent


@app.get("/events", response_class=EventSourceResponse)
async def stream_events() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(data={"status": "started"}, event="status", id="1")
    yield ServerSentEvent(data={"progress": 50}, event="progress", id="2")
```

Use `raw_data=` instead of `data=` to send a pre-formatted string without
JSON encoding: `ServerSentEvent(raw_data="plain text line", event="log")`.

## Bytes

Set `response_class=` to `StreamingResponse` or a subclass and `yield` the data:

```python
from collections.abc import Iterator

from fastapi.responses import StreamingResponse


class PNGStreamingResponse(StreamingResponse):
    media_type = "image/png"


@app.get("/image", response_class=PNGStreamingResponse)
def stream_image() -> Iterator[bytes]:
    with read_image() as image_file:
        yield from image_file
```

Prefer this over constructing and returning a `StreamingResponse` yourself.
