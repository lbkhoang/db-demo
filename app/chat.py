import asyncio
import json
import os
import re
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.documents import connect

router = APIRouter()
CHAT_LOCK = asyncio.Lock()
SYSTEM = """Bạn trả lời tiếng Việt về danh sách phần mềm. Phải dùng search_documents trước khi trả lời.
Chỉ dùng evidence được cung cấp, không tự tạo thông tin. Mỗi kết luận phải dẫn [C<chunk_id>].
Nếu hỏi whitelist/blacklist, liệt kê đúng nhóm. Nếu hỏi toàn bộ, tổng hợp đủ hai nhóm.
Nếu evidence chưa đủ, nói rõ thiếu thông tin."""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: UUID | None = None
    mode: str = "hybrid"


def save_turn(conversation_id, question, answer, citations):
    with connect() as conn:
        conn.execute("INSERT INTO conversations(id) VALUES (%s) ON CONFLICT DO NOTHING", (conversation_id,))
        conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES (%s,'user',%s)", (conversation_id, question))
        conn.execute("INSERT INTO messages(conversation_id,role,content,citations) VALUES (%s,'assistant',%s,%s)", (conversation_id, answer, Jsonb(citations)))


def event(kind, payload):
    return f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def validate_answer(answer, sources):
    cited = list(dict.fromkeys(int(value) for value in re.findall(r"\[C(\d+)\]", answer)))
    allowed = {item["chunk_id"]: item for item in sources}
    if not cited or any(value not in allowed for value in cited):
        return "Chưa đủ bằng chứng có citation hợp lệ để trả lời.", []
    return answer, [allowed[value] for value in cited]


async def generate(request: ChatRequest):
    started = perf_counter()
    conversation_id = request.conversation_id or uuid4()
    yield event("status", {"message": "Đang tìm evidence…"})
    async with CHAT_LOCK:
        try:
            url = os.getenv("MCP_URL", "http://mcp-server:8001/mcp")
            async with streamablehttp_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    available = await session.list_tools()
                    if "search_documents" not in {tool.name for tool in available.tools}:
                        raise RuntimeError("MCP thiếu search_documents")
                    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request.message}]
                    model = os.getenv("CHAT_MODEL", "qwen3:4b")
                    options = {"num_ctx": int(os.getenv("CHAT_CONTEXT", "4096")), "num_predict": 1024, "temperature": 0}
                    async with httpx.AsyncClient(base_url=os.getenv("OLLAMA_URL", "http://ollama:11434"), timeout=360) as client:
                        routed = await client.post("/api/chat", json={"model": model, "messages": messages,
                            "tools": [{"type": "function", "function": {"name": "search_documents", "description": "Tìm evidence.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}], "stream": False, "options": options})
                        routed.raise_for_status()
                        proposal = routed.json()["message"]
                        call = (proposal.get("tool_calls") or [{"function": {"arguments": {"query": request.message}}}])[0]["function"]
                        query = call.get("arguments", {}).get("query", request.message)
                        result = await asyncio.wait_for(session.call_tool("search_documents", {"query": query, "mode": request.mode, "top_k": 12}), 180)
                        payload = result.structuredContent or json.loads(next(item.text for item in result.content if item.type == "text"))
                        sources = payload.get("sources", [])
                        compact = [{"citation": f"C{s['chunk_id']}", "file": s["filename"], "page": s["page_number"], "section": s.get("section_path", ""), "text": s["text"]} for s in sources]
                        messages += [proposal, {"role": "tool", "tool_name": "search_documents", "content": json.dumps(compact, ensure_ascii=False)}, {"role": "system", "content": "Trả lời từ evidence và dùng citation [C<id>]."}]
                        yield event("status", {"message": "Đang soạn câu trả lời…", "tool": "search_documents"})
                        answer = ""
                        async with client.stream("POST", "/api/chat", json={"model": model, "messages": messages, "stream": True, "options": options}) as response:
                            response.raise_for_status()
                            async for line in response.aiter_lines():
                                if line:
                                    delta = json.loads(line).get("message", {}).get("content", "")
                                    answer += delta
                                    if delta:
                                        yield event("delta", {"text": delta})
                        answer, citations = validate_answer(answer, sources)
            await asyncio.to_thread(save_turn, conversation_id, request.message, answer, citations)
            yield event("done", {"conversation_id": str(conversation_id), "answer": answer, "citations": citations, "elapsed_seconds": round(perf_counter() - started, 2)})
        except Exception:
            yield event("error", {"message": "Chat chưa hoàn tất; kiểm tra model, MCP và database."})


@router.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(generate(request), media_type="text/event-stream")
