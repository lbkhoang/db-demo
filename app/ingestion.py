"""File parsing and Ollama embedding helpers used by the worker."""
from pathlib import Path
import json
import math
import os
import shutil
import subprocess
import tempfile

import httpx
import pymupdf

MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding:0.6b")
DIMENSION = int(os.getenv("EMBED_DIM", "1024"))


def parse_pages(source: Path) -> list[str]:
    """Return extracted text pages; Markdown/text files are one logical page."""
    if source.suffix.lower() in {".md", ".txt"}:
        text = source.read_text(encoding="utf-8-sig").replace("\x00", "").strip()
        if not text:
            raise ValueError("Empty text file")
        return [text]

    with tempfile.TemporaryDirectory(prefix="rag-convert-") as directory:
        root = Path(directory)
        pdf = source
        if source.suffix.lower() != ".pdf":
            subprocess.run([
                "libreoffice", f"-env:UserInstallation={(root / 'profile').as_uri()}",
                "--headless", "--convert-to", "pdf", "--outdir", str(root), str(source),
            ], check=True, timeout=120, capture_output=True)
            pdf = root / (source.stem + ".pdf")
            if not pdf.exists():
                raise ValueError("Could not convert Word file to PDF")
        with pymupdf.open(pdf) as document:
            if document.needs_pass:
                raise ValueError("Password-protected files are not supported")
            if len(document) > 200:
                raise ValueError("Demo limit is 200 pages")
            pages = [page.get_text(sort=True).strip().replace("\x00", "") for page in document]
        if not any(pages):
            raise ValueError("No text found; OCR is not enabled")
        if sum(map(len, pages)) > 1_000_000:
            raise ValueError("Demo text limit exceeded")
        if source.suffix.lower() != ".pdf":
            # Keep a canonical PDF beside the original for repeatable pagination.
            canonical = source.with_suffix(".rendered.pdf")
            temporary = canonical.with_suffix(".tmp")
            shutil.copyfile(pdf, temporary)
            temporary.replace(canonical)
        return pages


def embed(client: httpx.Client, text: str) -> str:
    """Embed one chunk and validate its dimension before writing it to pgvector."""
    response = client.post("/api/embed", json={"model": MODEL, "input": text, "truncate": False})
    response.raise_for_status()
    vectors = response.json()["embeddings"]
    if len(vectors) != 1 or len(vectors[0]) != DIMENSION:
        raise ValueError(f"Embedding dimension does not match schema {DIMENSION}")
    if not all(math.isfinite(value) for value in vectors[0]) or not any(vectors[0]):
        raise ValueError("Invalid embedding returned by Ollama")
    return json.dumps(vectors[0])
