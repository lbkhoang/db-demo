"""Terminal demo for document upload and database ingestion.

Examples:
  python -m scripts.demo_ingest --file ./data/demo/hr_policy_v0.1.docx --title hr_policy
  python -m scripts.demo_ingest --seed
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row


def api_url():
    return os.getenv("RAG_API_URL", "http://localhost:8000").rstrip("/")


def wait_job(client, job_id, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        print(f"  job={job_id} status={job['status']} attempts={job['attempts']}", flush=True)
        if job["status"] == "ready":
            return job
        if job["status"] == "failed":
            raise RuntimeError(job.get("error") or "ingestion failed")
        time.sleep(2)
    raise TimeoutError(f"Job chưa hoàn thành sau {timeout}s: {job_id}")


def upload(client, path, title, document_id, effective_at):
    suffix = path.suffix.lower()
    if suffix not in {".doc", ".docx", ".pdf"}:
        raise ValueError("Chỉ hỗ trợ .doc, .docx và .pdf")
    endpoint = f"/documents/{document_id}/versions" if document_id else "/documents"
    with path.open("rb") as source:
        data = {}
        if title:
            data["title"] = title
        if effective_at:
            data["effective_at"] = effective_at
        response = client.post(endpoint, files={"file": (path.name, source)}, data=data)
    response.raise_for_status()
    return response.json()


def print_database_view(client, document_id):
    docs = client.get("/documents").json()
    document = next((item for item in docs if str(item["id"]) == str(document_id)), None)
    if not document:
        raise RuntimeError("Không tìm thấy document sau khi ingest")
    versions = client.get(f"/documents/{document_id}/versions").json()
    print("\nDB view")
    print(f"  document: {document['title']} ({document['id']})")
    print(f"  versions: {len(versions)}")
    for version in versions:
        pages = client.get(f"/versions/{version['id']}/pages") if version["status"] == "ready" else None
        page_count = len(pages.json()) if pages else 0
        print(f"    {version['filename']} status={version['status']} pages={page_count} uploaded_at={version['uploaded_at']}")
    try:
        with psycopg.connect(connect_timeout=3, row_factory=dict_row) as conn:
            counts = conn.execute("""SELECT count(DISTINCT p.id) AS pages,count(c.id) AS chunks,
                coalesce(min(vector_dims(c.embedding)),0) AS vector_dim
                FROM document_versions v LEFT JOIN pages p ON p.version_id=v.id
                LEFT JOIN chunks c ON c.page_id=p.id WHERE v.document_id=%s""", (document_id,)).fetchone()
            print(f"  postgres: pages={counts['pages']} chunks={counts['chunks']} vector_dim={counts['vector_dim']}")
    except psycopg.Error:
        print("  postgres: direct connection unavailable (use docker compose exec app for DB counters)")


def seed(client):
    # Keep the existing deterministic four-file fixture as the DB ingest demo.
    import scripts.seed_demo as fixture

    fixture.main()
    documents = client.get("/documents").json()
    print(f"\nSeed complete: {len(documents)} document(s)")
    for document in documents:
        print_database_view(client, document["id"])


def main():
    parser = argparse.ArgumentParser(description="Demo upload -> worker -> PostgreSQL pages/chunks")
    parser.add_argument("--file", type=Path, help=".doc/.docx/.pdf to upload")
    parser.add_argument("--title", help="Title for a new document")
    parser.add_argument("--document-id", help="Existing document UUID; upload as next version")
    parser.add_argument("--effective-at", help="Effective date YYYY-MM-DD")
    parser.add_argument("--seed", action="store_true", help="Ingest the four 10-page demo fixtures")
    parser.add_argument("--wait", type=int, default=600, help="Ingestion timeout in seconds")
    args = parser.parse_args()
    if bool(args.file) == bool(args.seed):
        parser.error("Chọn đúng một trong --file hoặc --seed")
    with httpx.Client(base_url=api_url(), timeout=30) as client:
        if args.seed:
            seed(client)
            return
        path = args.file.resolve()
        if not path.is_file():
            parser.error(f"Không tìm thấy file: {path}")
        item = upload(client, path, args.title, args.document_id, args.effective_at)
        print(json.dumps(item, ensure_ascii=False, indent=2))
        wait_job(client, item["job_id"], args.wait)
        print_database_view(client, item["document_id"])
        print("\nIngest complete: file -> version -> pages -> chunks/vector")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
