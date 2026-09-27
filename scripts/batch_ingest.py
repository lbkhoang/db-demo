"""Scan the local input folder and queue every new document for the worker.

The demo source files live in ``app/data``. No upload HTTP request is
required; this command creates the database rows and the worker does the heavy work.
"""
import hashlib
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

import psycopg

from app.documents import connect

INPUT_DIR = Path(os.getenv("BATCH_INPUT_DIR", "/app/app/data"))
FILE_ROOT = Path(os.getenv("FILE_ROOT", "/data/files"))
ALLOWED = {".doc", ".docx", ".pdf", ".md", ".txt"}
MAX_BYTES = 20 * 1024 * 1024


def queue_file(conn, source: Path) -> bool:
    data = source.read_bytes()
    if not data:
        print(f"SKIP {source.name}: empty file")
        return False
    if len(data) > MAX_BYTES:
        print(f"SKIP {source.name}: larger than 20 MiB")
        return False
    checksum = hashlib.sha256(data).hexdigest()
    if conn.execute("SELECT 1 FROM documents WHERE checksum=%s", (checksum,)).fetchone():
        print(f"SKIP {source.name}: checksum already indexed")
        return False

    document_id, job_id = uuid4(), uuid4()
    suffix = source.suffix.lower()
    stored = FILE_ROOT / f"{document_id}{suffix}"
    FILE_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, stored)
    title = re.sub(r"[_\-]+", " ", source.stem).strip()[:200] or "document"
    try:
        conn.execute("""INSERT INTO documents
            (id,title,original_name,filename,storage_path,checksum)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (document_id, title, source.name, source.name, str(stored), checksum))
        conn.execute("INSERT INTO ingestion_jobs(id,document_id) VALUES (%s,%s)", (job_id, document_id))
    except Exception:
        stored.unlink(missing_ok=True)
        raise
    print(f"QUEUED {source.name} job={job_id}")
    return True


def main():
    files = sorted(path for path in INPUT_DIR.rglob("*") if path.is_file() and path.suffix.lower() in ALLOWED)
    if not files:
        raise SystemExit(f"No supported files found in {INPUT_DIR}")
    with connect() as conn:
        queued = sum(queue_file(conn, path) for path in files)
    print(f"DONE scanned={len(files)} queued={queued}")


if __name__ == "__main__":
    main()


