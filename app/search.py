import os
from typing import Literal

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel, Field

from app.documents import connect
from app.ingestion import MODEL, embed

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=6, ge=1, le=50)


BASE = """SELECT c.id AS chunk_id,c.text,c.section_path,p.page_number,d.id AS document_id,
    d.filename FROM chunks c JOIN pages p ON p.id=c.page_id
    JOIN documents d ON d.id=p.document_id
    WHERE d.status='ready' AND c.embedding_model=%s"""


def search_documents(query: str, mode: str = "hybrid", top_k: int = 6) -> dict:
    request = SearchRequest(query=query, mode=mode, top_k=top_k)
    with connect() as conn:
        vector_rows, keyword_rows = [], []
        if mode != "keyword":
            with httpx.Client(base_url=os.getenv("OLLAMA_URL", "http://ollama:11434"), timeout=180) as client:
                vector = embed(client, query)
            vector_rows = conn.execute(BASE + " ORDER BY c.embedding <=> %s::vector,c.id LIMIT 40", (MODEL, vector)).fetchall()
        if mode != "vector":
            keyword_rows = conn.execute(BASE + """ AND c.search_vector @@ websearch_to_tsquery('simple',unaccent(%s))
                ORDER BY ts_rank_cd(c.search_vector,websearch_to_tsquery('simple',unaccent(%s))) DESC,c.id LIMIT 40""",
                (MODEL, query, query)).fetchall()
    merged = {}
    for kind, rows in (("vector", vector_rows), ("keyword", keyword_rows)):
        for rank, row in enumerate(rows, 1):
            source = merged.setdefault(row["chunk_id"], {**row, "score": 0.0})
            source["score"] += 1 / (60 + rank)
            source[f"{kind}_rank"] = rank
    return {"sources": sorted(merged.values(), key=lambda row: (-row["score"], row["chunk_id"]))[:request.top_k], "mode": mode}


@router.post("/search")
def search_api(request: SearchRequest):
    try:
        return search_documents(request.query, request.mode, request.top_k)
    except httpx.HTTPError as error:
        raise HTTPException(503, "Embedding service unavailable") from error
