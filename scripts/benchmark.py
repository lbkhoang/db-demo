"""Explicit model checkpoint: requires models to be pulled beforehand."""
import asyncio
import json
import os
from time import perf_counter

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    base = os.getenv("OLLAMA_URL", "http://ollama:11434")
    chat_model = os.getenv("CHAT_MODEL", "qwen3:4b")
    embed_model = os.getenv("EMBED_MODEL", "qwen3-embedding:0.6b")
    context = int(os.getenv("CHAT_CONTEXT", "4096"))
    async with httpx.AsyncClient(base_url=base, timeout=600) as client:
        started = perf_counter()
        embedded = await client.post("/api/embed", json={
            "model": embed_model,
            "input": ["Chính sách thưởng của công ty", "Nhân viên được thưởng theo kết quả công việc"],
            "keep_alive": 0,
        })
        embedded.raise_for_status()
        vectors = embedded.json()["embeddings"]
        if len(vectors) != 2 or not vectors[0] or len(vectors[0]) != len(vectors[1]):
            raise RuntimeError("Invalid embedding shape")
        report = {"embedding_model": embed_model, "embedding_dimension": len(vectors[0]),
                  "embedding_seconds": round(perf_counter() - started, 2),
                  "chat_model": chat_model, "context": context}
        async with streamablehttp_client(os.getenv("MCP_URL", "http://mcp-server:8001/mcp")) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available = await session.list_tools()
                schemas = [{"type": "function", "function": {
                    "name": t.name, "description": t.description or "", "parameters": t.inputSchema,
                }} for t in available.tools if t.name == "system_status"]
                if not schemas:
                    raise RuntimeError("Missing system_status tool")
                messages = [{"role": "user", "content":
                    "Call the system_status tool to check the actual database, then report its status and pgvector version. Do not guess."}]
                tool_calls = 0
                started = perf_counter()
                for _ in range(6):
                    response = await client.post("/api/chat", json={
                        "model": chat_model, "messages": messages, "tools": schemas,
                        "stream": False, "options": {"num_ctx": context, "num_predict": 1024},
                    })
                    response.raise_for_status()
                    payload = response.json()
                    message = payload["message"]
                    messages.append(message)
                    calls = message.get("tool_calls", [])
                    if not calls:
                        if tool_calls == 0 or not message.get("content", "").strip():
                            raise RuntimeError("Model did not complete tool call followed by a final answer")
                        report.update(chat_seconds=round(perf_counter() - started, 2),
                                      tool_calls=tool_calls, answer=message["content"],
                                      eval_count=payload.get("eval_count"),
                                      eval_duration_ns=payload.get("eval_duration"))
                        break
                    for call in calls:
                        function = call["function"]
                        if function["name"] != "system_status" or function.get("arguments", {}) != {}:
                            raise RuntimeError("Unexpected tool or arguments")
                        result = await asyncio.wait_for(session.call_tool("system_status", {}), 15)
                        if result.isError:
                            raise RuntimeError("MCP tool failed")
                        tool_calls += 1
                        messages.append({"role": "tool", "tool_name": "system_status",
                                         "content": result.model_dump_json()})
                else:
                    raise RuntimeError("Tool loop limit exceeded")
        running = await client.get("/api/ps")
        running.raise_for_status()
        report["running_models"] = running.json()
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
