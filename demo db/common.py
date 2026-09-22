import os
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding:0.6b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
FILES_DIR = Path(os.getenv("FILES_DIR", "./data/files")).resolve()


def db():
    return psycopg.connect(row_factory=psycopg.rows.dict_row, connect_timeout=5)


def embed(texts):
    with httpx.Client(base_url=OLLAMA_URL, timeout=180) as client:
        response = client.post("/api/embed", json={"model": EMBED_MODEL, "input": texts, "truncate": False})
        response.raise_for_status()
        vectors = response.json()["embeddings"]
    if not vectors or any(len(vector) != EMBED_DIM for vector in vectors):
        raise RuntimeError(f"Embedding dimension mismatch; expected {EMBED_DIM}")
    return vectors
