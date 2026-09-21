import logging
import os
from pathlib import Path
import time

import httpx
import psycopg
from psycopg.rows import dict_row

from app.ingestion import MODEL, chunk_text, embed, parse_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOCK_ID = 728402


def process(conn, job):
    pages = parse_pages(Path(job["storage_path"]))
    prepared = []
    with httpx.Client(base_url=os.getenv("OLLAMA_URL", "http://ollama:11434"), timeout=180) as client:
        for number, text in enumerate(pages, 1):
            chunks = [(index, content, embed(client, content)) for index, content in enumerate(chunk_text(text))]
            prepared.append((number, text, chunks))
    # Publish all pages/chunks and ready state atomically, only after embedding succeeds.
    with conn.transaction():
        conn.execute("DELETE FROM pages WHERE version_id=%s", (job["version_id"],))
        for number, text, chunks in prepared:
            page_id = conn.execute("INSERT INTO pages(version_id,page_number,text) VALUES (%s,%s,%s) RETURNING id", (job["version_id"],number,text)).fetchone()["id"]
            for index, content, vector in chunks:
                conn.execute("INSERT INTO chunks(page_id,chunk_index,text,embedding,embedding_model) VALUES (%s,%s,%s,%s::vector,%s)", (page_id,index,content,vector,MODEL))
        conn.execute("UPDATE document_versions SET status='ready',error=NULL,page_count=%s WHERE id=%s", (len(pages),job["version_id"]))
        conn.execute("UPDATE ingestion_jobs SET status='ready',error=NULL,updated_at=now() WHERE id=%s", (job["id"],))


def main():
    # A session lock guarantees one worker, including during restart/recovery.
    # A lost DB session aborts this process before it can publish any result.
    with psycopg.connect(connect_timeout=5, autocommit=True, row_factory=dict_row) as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s) AS locked", (LOCK_ID,)).fetchone()["locked"]:
            raise RuntimeError("Một worker khác đang chạy")
        with conn.transaction():
            recovered = conn.execute("""UPDATE ingestion_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'queued' END,
                error='Worker interrupted',updated_at=now() WHERE status='processing' RETURNING version_id,status""").fetchall()
            for job in recovered:
                conn.execute("UPDATE document_versions SET status=%s,error='Worker interrupted' WHERE id=%s", (job["status"],job["version_id"]))
        logging.info("Worker ready")
        while True:
            with conn.transaction():
                job = conn.execute("""SELECT j.*,v.storage_path FROM ingestion_jobs j JOIN document_versions v ON v.id=j.version_id
                    WHERE j.status='queued' ORDER BY j.created_at LIMIT 1 FOR UPDATE OF j SKIP LOCKED""").fetchone()
                if job:
                    conn.execute("UPDATE ingestion_jobs SET status='processing',attempts=attempts+1,updated_at=now() WHERE id=%s", (job["id"],))
                    conn.execute("UPDATE document_versions SET status='processing',error=NULL WHERE id=%s", (job["version_id"],))
            if not job:
                time.sleep(2)
                continue
            try:
                process(conn, job)
                logging.info("Ready version %s", job["version_id"])
            except Exception as error:
                logging.exception("Ingest failed for %s", job["version_id"])
                status = "failed" if job["attempts"] + 1 >= 3 else "queued"
                reason = f"{type(error).__name__}: {error}"[:1000]
                with conn.transaction():
                    conn.execute("UPDATE ingestion_jobs SET status=%s,error=%s,updated_at=now() WHERE id=%s", (status,reason,job["id"]))
                    conn.execute("UPDATE document_versions SET status=%s,error=%s WHERE id=%s", (status,reason,job["version_id"]))
                time.sleep(3)


if __name__ == "__main__":
    main()
