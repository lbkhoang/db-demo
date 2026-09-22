"""Interactive terminal client for the RAG chat SSE endpoint."""
import argparse
import json
import os
import sys
import uuid

import httpx


def api_url():
    return os.getenv("RAG_API_URL", "http://localhost:8000").rstrip("/")


def parse_event(block):
    kind = "message"
    payload = None
    for line in block.splitlines():
        if line.startswith("event: "):
            kind = line[7:]
        elif line.startswith("data: "):
            payload = json.loads(line[6:])
    return kind, payload


def ask(client, prompt, conversation_id, version_ids, mode, compare):
    body = {
        "message": prompt,
        "conversation_id": conversation_id,
        "version_ids": version_ids,
        "mode": mode,
        "compare": compare,
    }
    answer = ""
    done = None
    with client.stream("POST", "/chat", json=body, timeout=600) as response:
        response.raise_for_status()
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                kind, payload = parse_event(block)
                if not payload:
                    continue
                if kind == "status":
                    print(f"\n[{payload.get('message', 'working')}]")
                elif kind == "delta":
                    text = payload.get("text", "")
                    print(text, end="", flush=True)
                    answer += text
                elif kind == "done":
                    done = payload
                elif kind == "error":
                    raise RuntimeError(payload.get("message", "chat failed"))
    if not done:
        raise RuntimeError("Chat kết thúc trước event done")
    print("\n\nSources:")
    for source in done.get("citations", []):
        print(f"  [C{source['chunk_id']}] {source['filename']} · page {source['page_number']}")
    print(f"Elapsed: {done.get('elapsed_seconds', '?')}s")
    return done["conversation_id"]


def main():
    parser = argparse.ArgumentParser(description="Terminal chat client for the local RAG app")
    parser.add_argument("--version-id", action="append", default=[], help="Version UUID; repeat for explicit scope")
    parser.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
    parser.add_argument("--compare", action="store_true", help="One selected old version is compared with latest ready")
    parser.add_argument("prompt", nargs="?", help="One prompt; omit for interactive mode")
    args = parser.parse_args()
    if args.compare and len(args.version_id) not in (1, 2):
        parser.error("--compare cần một version cũ, hoặc hai version cụ thể")
    with httpx.Client(base_url=api_url(), timeout=600) as client:
        conversation = str(uuid.uuid4())
        if args.prompt:
            ask(client, args.prompt, conversation, args.version_id, args.mode, args.compare)
            return
        print("RAG terminal chat. Gõ /help để xem lệnh, /quit để thoát.")
        while True:
            try:
                prompt = input("\nBạn> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not prompt:
                continue
            if prompt in {"/quit", "/exit"}:
                return
            if prompt == "/help":
                print("Nhập câu hỏi tự nhiên. Scope hiện tại: " + (", ".join(args.version_id) if args.version_id else "latest ready của mỗi tài liệu"))
                print("Dùng --version-id UUID để giới hạn version; --compare để so sánh bản cũ với bản mới nhất.")
                continue
            try:
                conversation = ask(client, prompt, conversation, args.version_id, args.mode, args.compare)
            except (httpx.HTTPError, RuntimeError) as error:
                print(f"\nERROR: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
