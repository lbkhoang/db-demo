"""Integration checks against the local demo stack; creates isolated test data."""
from concurrent.futures import ThreadPoolExecutor
import uuid

import httpx
import psycopg
import pymupdf

from app.ingestion import chunk_text
from scripts.seed_demo import wait_job


def pdf_bytes():
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), "POLICY-TEST: Annual leave is 12 days.")
        return doc.tobytes()


def main():
    content = pdf_bytes()
    with httpx.Client(base_url="http://app:8000", timeout=30) as client:
        assert client.post("/documents", files={"file": ("test.exe", b"invalid")}).status_code == 415
        assert client.post("/documents", files={"file": ("empty.pdf", b"")}).status_code == 422
        response = client.post("/documents", data={"title": f"integration-{uuid.uuid4()}"}, files={"file": ("test.pdf", content)})
        response.raise_for_status()
        first = response.json()
        wait_job(client, first["job_id"])
        endpoint = f"/documents/{first['document_id']}/versions"

        def upload(_):
            result = client.post(endpoint, files={"file": ("test.pdf", content)})
            result.raise_for_status()
            return result.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent = list(executor.map(upload, range(2)))
        assert {item["version"] for item in concurrent} == {"v0.2", "v0.3"}
        for item in concurrent:
            wait_job(client, item["job_id"])
        result = client.post(endpoint, files={"file": ("corrupt.pdf", b"not a pdf")})
        result.raise_for_status()
        failed = result.json()
        try:
            wait_job(client, failed["job_id"], 60)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Corrupt file should fail")
        job = client.get(f"/jobs/{failed['job_id']}").json()
        assert job["attempts"] == 3
        current = next(doc for doc in client.get("/documents").json() if doc["id"] == first["document_id"])
        third = next(item for item in concurrent if item["version"] == "v0.3")
        assert current["latest_ready_version_id"] == third["version_id"]
        assert client.post(f"/jobs/{first['job_id']}/retry").status_code == 409
        # Simulate recovery/reprocessing of an already-published version.
        with psycopg.connect() as conn:
            conn.execute("UPDATE ingestion_jobs SET status='failed' WHERE id=%s", (first["job_id"],))
            conn.execute("UPDATE document_versions SET status='failed' WHERE id=%s", (first["version_id"],))
        retried = client.post(f"/jobs/{first['job_id']}/retry")
        retried.raise_for_status()
        wait_job(client, first["job_id"])
        with psycopg.connect() as conn:
            count = conn.execute("SELECT count(*),min(vector_dims(c.embedding)) FROM chunks c JOIN pages p ON p.id=c.page_id WHERE p.version_id=%s", (first["version_id"],)).fetchone()
            assert count == (1, 1024), count
        assert len(chunk_text("a" * 2000)) == 3
        print("PASS: PDF ingest, real 1024-d embedding, concurrent versions, bounded retry, latest-ready, idempotent reprocessing")
        # Remove only the documents created by this test, leaving demo/user data intact.
        with psycopg.connect() as conn:
            paths = conn.execute("SELECT storage_path FROM document_versions WHERE document_id=%s", (first["document_id"],)).fetchall()
            conn.execute("DELETE FROM ingestion_jobs WHERE version_id IN (SELECT id FROM document_versions WHERE document_id=%s)", (first["document_id"],))
            conn.execute("DELETE FROM pages WHERE version_id IN (SELECT id FROM document_versions WHERE document_id=%s)", (first["document_id"],))
            conn.execute("DELETE FROM document_versions WHERE document_id=%s", (first["document_id"],))
            conn.execute("DELETE FROM documents WHERE id=%s", (first["document_id"],))
        from pathlib import Path
        root = Path("/data/files").resolve()
        for (stored,) in paths:
            path = Path(stored).resolve()
            if path.parent != root:
                raise RuntimeError("Unexpected test file path")
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
