import asyncio
import os

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.db import database_status
from app.mcp_client import check_mcp
from app.documents import router as documents_router

app = FastAPI(title="RAG PostgreSQL", version="0.1.0")
app.include_router(documents_router)


@app.get("/")
async def index():
    return {"app": "rag-pg", "stage": "upload-and-ingestion", "docs": "/docs"}


@app.get("/health/live")
async def live():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    async def ollama_status():
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/tags")
            response.raise_for_status()
            models = [item["name"] for item in response.json().get("models", [])]
            return {"status": "ok", "models": models}

    names = ["postgres", "mcp", "ollama"]
    results = await asyncio.gather(
        asyncio.wait_for(database_status(), 5),
        asyncio.wait_for(check_mcp(), 5),
        asyncio.wait_for(ollama_status(), 5),
        return_exceptions=True,
    )
    checks = {
        name: {"status": "error", "type": type(result).__name__}
        if isinstance(result, BaseException) else result
        for name, result in zip(names, results)
    }
    healthy = not any(isinstance(result, BaseException) for result in results)
    # Infrastructure readiness is separate from model availability.
    return JSONResponse(
        {"status": "ok" if healthy else "error", "scope": "infrastructure", "checks": checks},
        status_code=200 if healthy else 503,
    )
