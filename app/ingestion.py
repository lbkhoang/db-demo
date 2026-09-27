from pathlib import Path
import json
import math
import os
import subprocess
import shutil
import tempfile

import httpx
import pymupdf

from app.chunking import chunk_text

MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding:0.6b")
DIMENSION = int(os.getenv("EMBED_DIM", "1024"))


def parse_pages(source: Path) -> list[str]:
    if source.suffix.lower() in {".md", ".txt"}:
        text = source.read_text(encoding="utf-8").replace("\x00", "").strip()
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
                raise ValueError("Không chuyển được Word sang PDF")
        with pymupdf.open(pdf) as document:
            if document.needs_pass:
                raise ValueError("Không hỗ trợ tài liệu có mật khẩu")
            if len(document) > 200:
                raise ValueError("Giới hạn 200 trang cho demo")
            pages = [page.get_text(sort=True).strip().replace("\x00", "") for page in document]
        if not any(pages):
            raise ValueError("Không tìm thấy văn bản; chưa hỗ trợ OCR")
        if sum(map(len, pages)) > 1_000_000:
            raise ValueError("Vượt giới hạn văn bản cho demo")
        if source.suffix.lower() != ".pdf":
            canonical = source.with_suffix(".rendered.pdf")
            temporary = canonical.with_suffix(".tmp")
            shutil.copyfile(pdf, temporary)
            temporary.replace(canonical)
        return pages


def embed(client: httpx.Client, text: str) -> str:
    response = client.post("/api/embed", json={"model": MODEL, "input": text, "truncate": False})
    response.raise_for_status()
    vectors = response.json()["embeddings"]
    if len(vectors) != 1 or len(vectors[0]) != DIMENSION:
        raise ValueError(f"Embedding dimension không khớp schema {DIMENSION}")
    if not all(math.isfinite(value) for value in vectors[0]) or not any(vectors[0]):
        raise ValueError("Embedding không hợp lệ")
    return json.dumps(vectors[0])
