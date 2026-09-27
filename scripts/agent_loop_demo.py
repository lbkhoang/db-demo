"""Observable agent loop: the model may call search up to three times."""
import argparse
import json
import os
import sys

import httpx

SYSTEM = """Bạn là agent hỏi đáp chính sách. Hãy dùng search_documents để lấy evidence.
Nếu evidence chưa đủ để trả lời toàn bộ câu hỏi, hãy gọi tool lần nữa với query hẹp hơn.
Tối đa ba lần gọi. Khi đủ dữ liệu, trả lời tiếng Việt và dẫn [C<chunk_id>]. Không bịa."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", default="Tóm tắt HR-01 và HR-02, gồm ngày phép và remote work.")
    parser.add_argument("--api", default=os.getenv("RAG_API_URL", "http://localhost:8000"))
    parser.add_argument("--model", default=os.getenv("CHAT_MODEL", "qwen3:4b"))
    args = parser.parse_args()
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": args.prompt}]
    tools = [{"type": "function", "function": {"name": "search_documents", "description": "Tìm evidence trong tài liệu.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]
    calls, seen = 0, set()
    ollama = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    with httpx.Client(base_url=args.api.rstrip("/"), timeout=360) as client:
        while calls < 3:
            response = client.post(ollama + "/api/chat", json={"model": args.model, "messages": messages, "tools": tools, "stream": False, "options": {"num_ctx": int(os.getenv("CHAT_CONTEXT", "4096")), "temperature": 0}})
            response.raise_for_status()
            message = response.json()["message"]
            requested = message.get("tool_calls", [])
            if not requested:
                print("\nAnswer:\n" + message.get("content", ""))
                print(f"Agent loop calls: {calls}")
                return
            messages.append(message)
            function = requested[0]["function"]
            query = function.get("arguments", {}).get("query", args.prompt)
            if not isinstance(query, str) or query in seen:
                print("Agent stopped: duplicate/invalid follow-up query")
                return
            seen.add(query)
            print(f"\n[agent call {calls + 1}] search_documents(query={query!r})")
            result = client.post("/search", json={"query": query, "mode": "hybrid", "top_k": 6})
            result.raise_for_status()
            sources = result.json().get("sources", [])
            print(f"  -> {len(sources)} source(s)")
            messages.append({"role": "tool", "tool_name": "search_documents", "content": json.dumps(sources, ensure_ascii=False)})
            calls += 1
        messages.append({"role": "system", "content": "Đã đạt giới hạn retrieval. Trả lời từ evidence đã có; nếu thiếu, nói rõ."})
        response = client.post(ollama + "/api/chat", json={"model": args.model, "messages": messages, "stream": False, "options": {"num_ctx": 4096, "temperature": 0}})
        response.raise_for_status()
        print("\nAnswer:\n" + response.json()["message"].get("content", ""))
        print(f"Agent loop calls: {calls} (limit reached)")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
