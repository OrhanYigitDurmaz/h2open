from fastapi import FastAPI

app = FastAPI(title="h2open")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
