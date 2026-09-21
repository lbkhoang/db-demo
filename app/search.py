import json
import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel, Field

from app.documents import connect
from app.ingestion import MODEL, embed

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    version_ids: list[UUID] = Field(default_factory=list, max_length=2)
    top_k: int = Field(default=6, ge=1, le=20)


def resolve_versions(conn, version_ids):
    if version_ids:
        ids = list(dict.fromkeys(UUID(str(value)) for value in version_ids))
        rows = conn.execute("SELECT id FROM document_versions WHERE id=ANY(%s) AND status='ready'", (ids,)).fetchall()
        if len(rows) != len(ids):
            raise ValueError("Version không tồn tại hoặc chưa ready")
        return ids
    return [row["id"] for row in conn.execute("""SELECT DISTINCT ON (document_id) id
        FROM document_versions WHERE status='ready' ORDER BY document_id,major DESC,minor DESC""").fetchall()]


BASE = """SELECT c.id AS chunk_id,c.text,p.page_number,v.id AS version_id,v.document_id,
    v.filename,v.major,v.minor FROM chunks c JOIN pages p ON p.id=c.page_id
    JOIN document_versions v ON v.id=p.version_id
    WHERE v.id=ANY(%s) AND v.status='ready' AND c.embedding_model=%s"""


def public(row):
    return {key: str(value) if isinstance(value, UUID) else value for key, value in row.items()}


def search_documents(query: str, mode: str = "hybrid", version_ids: list[str] | None = None, top_k: int = 6) -> dict:
    request = SearchRequest(query=query, mode=mode, version_ids=version_ids or [], top_k=top_k)
    if not request.query.strip():
        raise ValueError("Query rỗng")
    with connect() as conn:
        ids = resolve_versions(conn, request.version_ids)
        if not ids:
            return {"sources": [], "mode": mode}
        vector_rows, keyword_rows = [], []
        if mode != "keyword":
            with httpx.Client(base_url=os.getenv("OLLAMA_URL", "http://ollama:11434"), timeout=180) as client:
                vector = embed(client, query)
            vector_rows = conn.execute(BASE + " ORDER BY c.embedding <=> %s::vector,c.id LIMIT 40", (ids,MODEL,vector)).fetchall()
        if mode != "vector":
            keyword_rows = conn.execute(BASE + """ AND c.search_vector @@ websearch_to_tsquery('simple',unaccent(%s))
                ORDER BY ts_rank_cd(c.search_vector,websearch_to_tsquery('simple',unaccent(%s))) DESC,c.id LIMIT 40""",
                (ids,MODEL,query,query)).fetchall()
    merged = {}
    for kind, rows in (("vector", vector_rows), ("keyword", keyword_rows)):
        for rank, row in enumerate(rows, 1):
            source = merged.setdefault(row["chunk_id"], {**public(row), "score": 0.0})
            source["score"] += 1 / (60 + rank)
            source[f"{kind}_rank"] = rank
    sources = sorted(merged.values(), key=lambda row: (-row["score"], row["chunk_id"]))[:top_k]
    return {"sources": sources, "mode": mode}


def read_version_evidence(version_ids: list[str]) -> dict:
    if len(set(version_ids)) != 2:
        raise ValueError("Chọn đúng hai version khác nhau để so sánh")
    with connect() as conn:
        ids = resolve_versions(conn, version_ids)
        rows = conn.execute(BASE + " ORDER BY v.major,v.minor,p.page_number,c.chunk_index", (ids,MODEL)).fetchall()
    if len({row["document_id"] for row in rows}) != 1:
        raise ValueError("Hai version phải thuộc cùng tài liệu")
    if {row["version_id"] for row in rows} != set(ids):
        raise ValueError("Một version không có evidence với embedding model hiện tại")
    if len(rows) > 40 or sum(len(row["text"]) for row in rows) > 6500:
        raise ValueError("Hai bản quá dài để so sánh đầy đủ trong context demo; hãy hỏi chủ đề cụ thể")
    return {"sources": [public(row) for row in rows], "complete": True}


@router.post("/search")
def search_api(request: SearchRequest):
    try:
        return search_documents(request.query, request.mode, [str(x) for x in request.version_ids], request.top_k)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(503, "Embedding service chưa sẵn sàng") from error
