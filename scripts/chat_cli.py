"""Terminal client for the single-document RAG chat API."""
import argparse
import json
import os
import sys
import uuid
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
    args = parser.parse_args()
    prompt = args.prompt or input("Prompt> ").strip()
    body = {"message": prompt, "conversation_id": str(uuid.uuid4()), "mode": args.mode}
    with httpx.Client(base_url=os.getenv("RAG_API_URL", "http://localhost:8000"), timeout=600) as client:
        with client.stream("POST", "/chat", json=body) as response:
            response.raise_for_status()
            for block in response.iter_text():
                for line in block.splitlines():
                    if line.startswith("data: "):
                        payload = json.loads(line[6:])
                        if "text" in payload:
                            print(payload["text"], end="", flush=True)
                        elif "answer" in payload:
                            print("\n\nSources:")
                            for source in payload.get("citations", []):
                                print(f"  [C{source['chunk_id']}] {source['filename']} · page {source['page_number']}")
    print()


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
