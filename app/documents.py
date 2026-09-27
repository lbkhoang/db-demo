"""Document upload and ingestion-job endpoints."""
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4
import os
import re

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter()
FILE_ROOT = Path(os.getenv("FILE_ROOT", "/data/files"))
MAX_BYTES = 20 * 1024 * 1024


def connect():
    return psycopg.connect(connect_timeout=5, row_factory=dict_row)


def store_upload(file: UploadFile, title: str | None = None):
    # Store the upload under a generated ID; never trust a client path.
    original = (file.filename or "").replace("\\", "/").split("/")[-1]
    suffix = Path(original).suffix.lower()
    if suffix not in {".doc", ".docx", ".pdf", ".md", ".txt"}:
        raise HTTPException(415, "Unsupported file type; use .doc, .docx, .pdf, .md or .txt")
    document_id, job_id = uuid4(), uuid4()
    FILE_ROOT.mkdir(parents=True, exist_ok=True)
    path = FILE_ROOT / f"{document_id}{suffix}"
    digest, size = sha256(), 0
    committed = False
    try:
        with path.open("xb") as target:
            while block := file.file.read(1024 * 1024):
                size += len(block)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File size limit is 20 MiB")
                digest.update(block)
                target.write(block)
        if size == 0:
            raise HTTPException(422, "File is empty")
        resolved_title = (title or re.sub(r"_v\d+\.\d+$", "", Path(original).stem)).strip()
        if not resolved_title or len(resolved_title) > 200:
            raise HTTPException(422, "Title must be between 1 and 200 characters")
        basename = re.sub(r"[^\w\-]+", "_", resolved_title, flags=re.UNICODE).strip("_") or "document"
        filename = f"{basename}{suffix}"
        # Metadata and the worker job are committed together.
        with connect() as conn:
            conn.execute("""INSERT INTO documents
                (id,title,original_name,filename,storage_path,checksum)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (document_id, resolved_title, original, filename, str(path), digest.hexdigest()))
            conn.execute("INSERT INTO ingestion_jobs(id,document_id) VALUES (%s,%s)", (job_id, document_id))
        committed = True
        return {"document_id": document_id, "job_id": job_id, "filename": filename, "status": "queued"}
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(409, "A document with this file checksum already exists") from error
    finally:
        file.file.close()
        if not committed:
            path.unlink(missing_ok=True)


@router.post("/documents", status_code=202)
def upload_document(file: UploadFile = File(...), title: str | None = Form(None)):
    return store_upload(file, title)


@router.get("/documents")
def list_documents():
    with connect() as conn:
        return conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()


@router.get("/documents/{document_id}/pages")
def get_document_pages(document_id: UUID):
    with connect() as conn:
        document = conn.execute("SELECT status FROM documents WHERE id=%s", (document_id,)).fetchone()
        if not document:
            raise HTTPException(404, "Document not found")
        if document["status"] != "ready":
            raise HTTPException(409, "Document is not ready")
        return conn.execute("SELECT page_number,text FROM pages WHERE document_id=%s ORDER BY page_number", (document_id,)).fetchall()


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID):
    with connect() as conn:
        row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=%s", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        return row


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: UUID):
    with connect() as conn:
        job = conn.execute("SELECT * FROM ingestion_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        if job["status"] != "failed":
            raise HTTPException(409, "Only failed jobs can be retried")
        conn.execute("UPDATE ingestion_jobs SET status='queued',attempts=0,error=NULL,updated_at=now() WHERE id=%s", (job_id,))
        conn.execute("UPDATE documents SET status='queued',error=NULL WHERE id=%s", (job["document_id"],))
        return {"job_id": job_id, "status": "queued"}
