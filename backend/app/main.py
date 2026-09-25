"""FastAPI app entrypoint (placeholder; replaced in Task 12)."""

from fastapi import FastAPI

app = FastAPI(title="Legal-RAG v3", version="0.1.0")


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"pong": "v3"}
