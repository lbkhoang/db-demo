import argparse
import json
import os
import re
import sys
import uuid

import httpx

from common import EMBED_MODEL, OLLAMA_URL, db, embed


def latest_or_selected(conn, version_ids):
    if version_ids:
        rows = conn.execute("SELECT id,document_id,filename,major,minor FROM document_versions WHERE id=ANY(%s) AND status='ready'", (version_ids,)).fetchall()
        if len(rows) != len(version_ids):
            raise ValueError("Version không tồn tại hoặc chưa ready")
        return rows
    return conn.execute("""SELECT DISTINCT ON (document_id) id,document_id,filename,major,minor
        FROM document_versions WHERE status='ready'
        ORDER BY document_id,major DESC,minor DESC,uploaded_at DESC""").fetchall()


def search(query, mode, version_ids, top_k=6):
    vectors, keywords = [], []
    with db() as conn:
        selected = latest_or_selected(conn, version_ids)
        ids = [row["id"] for row in selected]
        if mode in ("vector", "hybrid"):
            vector = json.dumps(embed([query])[0])
            vectors = conn.execute("""SELECT c.id AS chunk_id,c.text,p.page_number,v.id AS version_id,v.filename,
                1-(c.embedding <=> %s::vector) AS score FROM chunks c JOIN pages p ON p.id=c.page_id
                JOIN document_versions v ON v.id=p.version_id WHERE v.id=ANY(%s)
                ORDER BY c.embedding <=> %s::vector LIMIT 40""", (vector,ids,vector)).fetchall()
        if mode in ("keyword", "hybrid"):
            keywords = conn.execute("""SELECT c.id AS chunk_id,c.text,p.page_number,v.id AS version_id,v.filename,
                ts_rank_cd(c.search_vector,websearch_to_tsquery('simple',unaccent(%s))) AS score
                FROM chunks c JOIN pages p ON p.id=c.page_id JOIN document_versions v ON v.id=p.version_id
                WHERE v.id=ANY(%s) AND c.search_vector @@ websearch_to_tsquery('simple',unaccent(%s))
                ORDER BY score DESC,c.id LIMIT 40""", (query,ids,query)).fetchall()
    merged = {}
    for rows in (vectors, keywords):
        for rank, row in enumerate(rows, 1):
            item = merged.setdefault(row["chunk_id"], dict(row, score=0.0))
            item["score"] += 1 / (60 + rank)
    return sorted(merged.values(), key=lambda row: (-row["score"], row["chunk_id"]))[:top_k]


def compare(old_id):
    with db() as conn:
        old = conn.execute("SELECT id,document_id FROM document_versions WHERE id=%s AND status='ready'", (old_id,)).fetchone()
        if not old:
            raise ValueError("Không tìm thấy version cũ")
        latest = conn.execute("""SELECT id FROM document_versions WHERE document_id=%s AND status='ready'
            ORDER BY major DESC,minor DESC,uploaded_at DESC LIMIT 1""", (old["document_id"],)).fetchone()
    if not latest or latest["id"] == old["id"]:
        raise ValueError("Chưa có version mới hơn")
    return search("", "keyword", [old["id"], latest["id"]], 40) if False else read_all([old["id"], latest["id"]])


def read_all(ids):
    with db() as conn:
        return conn.execute("""SELECT c.id AS chunk_id,c.text,p.page_number,v.id AS version_id,v.filename
            FROM chunks c JOIN pages p ON p.id=c.page_id JOIN document_versions v ON v.id=p.version_id
            WHERE v.id=ANY(%s) ORDER BY v.minor,p.page_number,c.chunk_index""", (ids,)).fetchall()


def ask(prompt, mode, version_ids, compare_id=None):
    sources = compare(compare_id) if compare_id else search(prompt, mode, version_ids)
    if not sources:
        print("Chưa tìm thấy evidence.")
        return
    evidence = "\n".join(f"[C{s['chunk_id']}] {s['filename']} page {s['page_number']}: {s['text']}" for s in sources)
    instruction = "So sánh bản cũ và bản mới, nêu thay đổi và dẫn nguồn." if compare_id else "Trả lời ngắn gọn bằng evidence và dẫn nguồn [C<id>]. Nếu không đủ dữ liệu, nói rõ."
    with httpx.Client(base_url=OLLAMA_URL, timeout=360) as client:
        response = client.post("/api/chat", json={"model": os.getenv("CHAT_MODEL", "qwen3:4b"), "stream": False,
            "messages": [{"role": "system", "content": "Bạn trả lời tiếng Việt, chỉ dùng evidence được cung cấp. " + instruction},
                         {"role": "user", "content": f"Câu hỏi: {prompt}\n\nEvidence:\n{evidence}"}],
            "options": {"num_ctx": 4096, "temperature": 0}})
        response.raise_for_status()
        answer = response.json()["message"]["content"]
    print(answer)
    print("\nSources:")
    for source in sources:
        print(f"  [C{source['chunk_id']}] {source['filename']} · page {source['page_number']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
    parser.add_argument("--version-id", action="append", default=[])
    parser.add_argument("--compare-version")
    args = parser.parse_args()
    with db() as conn:
        if not args.version_id and not args.compare_version:
            print("Ready versions:")
            for row in latest_or_selected(conn, []):
                print(f"  {row['id']}  {row['filename']}")
    if args.prompt:
        ask(args.prompt, args.mode, args.version_id, args.compare_version)
        return
    print("Portable RAG chat. /quit để thoát.")
    while True:
        try:
            prompt = input("\nBạn> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); return
        if prompt in {"/quit", "/exit"}:
            return
        if prompt:
            try: ask(prompt, args.mode, args.version_id, args.compare_version)
            except Exception as error: print(f"ERROR: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
