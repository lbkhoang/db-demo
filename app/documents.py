"""Read-only document/job endpoints; ingestion is started by the batch CLI."""
from pathlib import Path
from uuid import UUID
import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, HTTPException

router = APIRouter()


def connect():
    return psycopg.connect(connect_timeout=5, row_factory=dict_row)


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
