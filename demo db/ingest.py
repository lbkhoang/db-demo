"""Import ./docs into PostgreSQL.

python ingest.py          # import new files
python ingest.py reset    # clear demo tables, then import everything

Names use <document>_v<major>.<minor>.docx, for example hr_policy_v0.1.docx.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pymupdf

from common import EMBED_MODEL, FILES_DIR, db, embed
from header_chunking import chunks_for_page

ROOT = Path(__file__).parent
DOCS_DIR = ROOT / "docs"
VERSION_RE = re.compile(r"^(?P<title>.+?)_v(?P<major>\d+)\.(?P<minor>\d+)$", re.I)


def split_name(path):
    match = VERSION_RE.match(path.stem)
    if match:
        return match.group("title"), int(match.group("major")), int(match.group("minor"))
    return path.stem, 0, None


def chunks(text, size=1000, overlap=100):
    output, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        value = text[start:end].strip()
        if value:
            output.append(value)
        if end == len(text):
            break
        start = end - overlap
    return output


def read_pages(path):
    with tempfile.TemporaryDirectory(prefix="demo-db-") as folder:
        folder = Path(folder)
        source = path
        if path.suffix.lower() != ".pdf":
            subprocess.run([
                "soffice", "--headless", f"-env:UserInstallation={(folder / 'profile').as_uri()}",
                "--convert-to", "pdf", "--outdir", str(folder), str(path),
            ], check=True, timeout=120, capture_output=True)
            source = folder / f"{path.stem}.pdf"
        with pymupdf.open(source) as document:
            pages = [page.get_text(sort=True).strip() for page in document]
    if not any(pages):
        raise RuntimeError(f"Không có text: {path.name}")
    return pages


def import_file(conn, path, title, major, minor):
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if conn.execute("SELECT id FROM document_versions WHERE checksum=%s", (checksum,)).fetchone():
        print(f"SKIP {path.name}: checksum đã tồn tại")
        return
    document = conn.execute("SELECT id FROM documents WHERE title=%s ORDER BY created_at LIMIT 1", (title,)).fetchone()
    document_id = document["id"] if document else uuid4()
    if not document:
        conn.execute("INSERT INTO documents(id,title) VALUES (%s,%s)", (document_id, title))
    if minor is None:
        minor = conn.execute("SELECT coalesce(max(minor),0)+1 AS minor FROM document_versions WHERE document_id=%s AND major=%s", (document_id, major)).fetchone()["minor"]
    if conn.execute("SELECT 1 FROM document_versions WHERE document_id=%s AND major=%s AND minor=%s", (document_id, major, minor)).fetchone():
        raise RuntimeError(f"Trùng version {title}_v{major}.{minor}: {path.name}")
    version_id, stored = uuid4(), FILES_DIR / f"{uuid4()}{path.suffix.lower()}"
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, stored)
    try:
        pages = read_pages(stored)
        strategy = os.getenv("CHUNK_STRATEGY", "page")
        page_chunks = [chunks_for_page(page, strategy) for page in pages]
        values = [item["text"] for items in page_chunks for item in items]
        vectors = embed(values)
        filename = f"{title}_v{major}.{minor}{path.suffix.lower()}"
        conn.execute("""INSERT INTO document_versions
            (id,document_id,major,minor,original_name,filename,storage_path,checksum,status,page_count)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ready',%s)""",
            (version_id,document_id,major,minor,path.name,filename,str(stored),checksum,len(pages)))
        offset = 0
        for page_number, text in enumerate(pages, 1):
            page_id = conn.execute("INSERT INTO pages(version_id,page_number,text) VALUES (%s,%s,%s) RETURNING id", (version_id,page_number,text)).fetchone()["id"]
            for item in page_chunks[page_number - 1]:
                conn.execute("""INSERT INTO chunks(page_id,chunk_index,section_path,text,embedding,embedding_model,search_vector)
                    VALUES (%s,%s,%s,%s,%s::vector,%s,to_tsvector('simple',unaccent(%s)))""",
                    (page_id,item["chunk_index"],item["header"],item["text"],json.dumps(vectors[offset]),EMBED_MODEL,item["text"]))
                offset += 1
        print(f"READY {filename}: {len(pages)} pages, {len(values)} chunks, vector={len(vectors[0])}")
    except Exception:
        stored.unlink(missing_ok=True)
        raise


def main():
    reset = len(sys.argv) == 2 and sys.argv[1].lower() == "reset"
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and not reset):
        raise SystemExit("Usage: python ingest.py [reset]")
    files = sorted(path for path in DOCS_DIR.rglob("*") if path.suffix.lower() in {".doc", ".docx", ".pdf"})
    if not files:
        raise SystemExit(f"Chưa có file Word/PDF trong {DOCS_DIR}")
    with db() as conn:
        if reset:
            conn.execute("TRUNCATE chunks,pages,document_versions,documents RESTART IDENTITY CASCADE")
            shutil.rmtree(FILES_DIR, ignore_errors=True)
            print("RESET demo tables")
        for path in files:
            title, major, minor = split_name(path)
            import_file(conn, path, title, major, minor)
        counts = conn.execute("""SELECT (SELECT count(*) FROM documents) documents,
            (SELECT count(*) FROM document_versions) versions,(SELECT count(*) FROM pages) pages,
            (SELECT count(*) FROM chunks) chunks""").fetchone()
    print(f"DONE documents={counts['documents']} versions={counts['versions']} pages={counts['pages']} chunks={counts['chunks']}")


if __name__ == "__main__":
    main()
