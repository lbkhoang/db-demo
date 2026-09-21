from datetime import date
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


def store_upload(file: UploadFile, document_id: UUID | None, title: str | None, effective_at: date | None):
    original = (file.filename or "").replace("\\", "/").split("/")[-1]
    suffix = Path(original).suffix.lower()
    if suffix not in {".doc", ".docx", ".pdf"}:
        raise HTTPException(415, "Chỉ hỗ trợ .doc, .docx và .pdf")
    version_id, job_id = uuid4(), uuid4()
    FILE_ROOT.mkdir(parents=True, exist_ok=True)
    path = FILE_ROOT / f"{version_id}{suffix}"
    digest, size = sha256(), 0
    committed = False
    try:
        with path.open("xb") as target:
            while block := file.file.read(1024 * 1024):
                size += len(block)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Giới hạn file là 20 MiB")
                digest.update(block)
                target.write(block)
        if size == 0:
            raise HTTPException(422, "File rỗng")
        with connect() as conn:
            if document_id is None:
                document_id = uuid4()
                resolved_title = (title or re.sub(r"_v\d+\.\d+$", "", Path(original).stem)).strip()
                if not resolved_title or len(resolved_title) > 200:
                    raise HTTPException(422, "Tên tài liệu phải dài từ 1 đến 200 ký tự")
                conn.execute("INSERT INTO documents(id,title) VALUES (%s,%s)", (document_id, resolved_title))
            doc = conn.execute("SELECT * FROM documents WHERE id=%s FOR UPDATE", (document_id,)).fetchone()
            if not doc:
                raise HTTPException(404, "Không tìm thấy tài liệu")
            minor = conn.execute("SELECT coalesce(max(minor),0)+1 AS minor FROM document_versions WHERE document_id=%s AND major=0", (document_id,)).fetchone()["minor"]
            basename = re.sub(r"[^\w\-]+", "_", doc["title"], flags=re.UNICODE).strip("_") or "document"
            filename = f"{basename}_v0.{minor}{suffix}"
            conn.execute("""INSERT INTO document_versions
                (id,document_id,minor,original_name,filename,storage_path,checksum,effective_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (version_id,document_id,minor,original,filename,str(path),digest.hexdigest(),effective_at))
            conn.execute("INSERT INTO ingestion_jobs(id,version_id) VALUES (%s,%s)", (job_id,version_id))
        committed = True
        return {"document_id": document_id, "version_id": version_id, "job_id": job_id,
                "version": f"v0.{minor}", "filename": filename, "status": "queued"}
    finally:
        file.file.close()
        if not committed:
            path.unlink(missing_ok=True)


@router.post("/documents", status_code=202)
def upload_document(file: UploadFile = File(...), title: str | None = Form(None), effective_at: date | None = Form(None)):
    return store_upload(file, None, title, effective_at)


@router.post("/documents/{document_id}/versions", status_code=202)
def upload_version(document_id: UUID, file: UploadFile = File(...), effective_at: date | None = Form(None)):
    return store_upload(file, document_id, None, effective_at)


@router.get("/documents")
def list_documents():
    with connect() as conn:
        return conn.execute("""SELECT d.*, v.id AS latest_ready_version_id, v.filename AS latest_ready_filename
            FROM documents d LEFT JOIN LATERAL (
                SELECT id,filename FROM document_versions WHERE document_id=d.id AND status='ready'
                ORDER BY major DESC,minor DESC LIMIT 1
            ) v ON true ORDER BY d.created_at DESC""").fetchall()


@router.get("/documents/{document_id}/versions")
def list_versions(document_id: UUID):
    with connect() as conn:
        if not conn.execute("SELECT id FROM documents WHERE id=%s", (document_id,)).fetchone():
            raise HTTPException(404, "Không tìm thấy tài liệu")
        return conn.execute("""SELECT id,document_id,major,minor,original_name,filename,checksum,
            uploaded_at,effective_at,status,error,page_count FROM document_versions
            WHERE document_id=%s ORDER BY major DESC,minor DESC""", (document_id,)).fetchall()


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID):
    with connect() as conn:
        row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=%s", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy job")
        return row


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: UUID):
    with connect() as conn:
        job = conn.execute("SELECT * FROM ingestion_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Không tìm thấy job")
        if job["status"] != "failed":
            raise HTTPException(409, "Chỉ retry job đã failed")
        conn.execute("UPDATE ingestion_jobs SET status='queued',attempts=0,error=NULL,updated_at=now() WHERE id=%s", (job_id,))
        conn.execute("UPDATE document_versions SET status='queued',error=NULL WHERE id=%s", (job["version_id"],))
        return {"job_id": job_id, "status": "queued"}


@router.get("/versions/{version_id}/pages")
def get_pages(version_id: UUID):
    with connect() as conn:
        version = conn.execute("SELECT status FROM document_versions WHERE id=%s", (version_id,)).fetchone()
        if not version:
            raise HTTPException(404, "Không tìm thấy version")
        if version["status"] != "ready":
            raise HTTPException(409, "Version chưa sẵn sàng")
        return conn.execute("SELECT page_number,text FROM pages WHERE version_id=%s ORDER BY page_number", (version_id,)).fetchall()
