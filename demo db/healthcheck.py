import os
import httpx
from common import EMBED_DIM, EMBED_MODEL, OLLAMA_URL, db


def main():
    with db() as conn:
        extension = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        if not extension:
            raise RuntimeError("pgvector extension is missing")
        print(f"PostgreSQL OK, pgvector {extension['extversion']}")
    with httpx.Client(base_url=OLLAMA_URL, timeout=10) as client:
        tags = client.get("/api/tags"); tags.raise_for_status()
        names = [item["name"] for item in tags.json().get("models", [])]
        print(f"Ollama OK: {', '.join(names) or '(no models)'}")
        vector = client.post("/api/embed", json={"model": EMBED_MODEL, "input": "healthcheck"})
        vector.raise_for_status()
        dimension = len(vector.json()["embeddings"][0])
        if dimension != EMBED_DIM:
            raise RuntimeError(f"Embedding dimension is {dimension}, expected {EMBED_DIM}")
        print(f"Embedding OK: {EMBED_MODEL}, dimension {dimension}")


if __name__ == "__main__":
    main()
