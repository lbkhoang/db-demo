# MCP + LangChain agent loop demo

Demo này không dùng database. Nó có một file Markdown và một MCP server cung cấp đúng hai quyền đọc có kiểm soát:

- `list_chunks`: xem danh sách chunk và heading, chưa đọc toàn bộ nội dung.
- `read_chunk(index)`: đọc một chunk cụ thể.
- `run_terminal(command)`: terminal read-only bị giới hạn vào `cat/type/Get-Content data/software_policy.md`.

Agent dùng LangChain + Ollama. Model phải gọi `list_chunks` trước, chọn chunk phù hợp, rồi gọi `read_chunk` một hoặc nhiều lần nếu evidence chưa đủ. Mọi lần gọi tool được ghi ra terminal và `agent.log`.

## Flow

```mermaid
flowchart LR
    Q[Prompt] --> L[LangChain + Ollama]
    L -->|list_chunks| M[MCP server]
    M --> F[(software_policy.md)]
    L -->|read_chunk(index)| M
    M --> E[Tool result]
    E --> L
    L --> A[Answer + chunk citations]
```

Model không được cấp quyền đọc filesystem trực tiếp. MCP server expose các thao tác đọc đã giới hạn. `run_terminal` chỉ để minh họa quyền terminal và không cho chạy shell command tùy ý.

## Run on Windows PowerShell

```powershell
cd agent_loop_demo
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Ollama phải đang chạy và có model chat:

```powershell
ollama pull qwen3:4b
```

Chạy agent:

```powershell
python agent.py "Is uTorrent whitelist or blacklist?"
python agent.py "List every blacklist item and explain why."
python agent.py "Classify every software item as whitelist or blacklist."
```

Output kỳ vọng:

```text
INFO MCP tool call: list_chunks({})
INFO MCP result: ... characters
INFO MCP tool call: read_chunk({'index': 2})
INFO MCP result: ... characters

Answer:
...
Agent tool calls: 2
```

Model có thể gọi `read_chunk` thêm lần nữa nếu câu hỏi cần cả Whitelist và Blacklist. Giới hạn mặc định là bốn tool calls; đổi qua `MAX_TOOL_CALLS` trong `.env`.

## Files

- `agent.py`: LangChain loop và logging.
- `mcp_server.py`: MCP server đọc file Markdown.
- `data/software_policy.md`: dữ liệu demo.
- `agent.log`: log được tạo sau lần chạy đầu tiên.

## Hiển thị tiến trình của agent

Mỗi lần model chọn một tool, chương trình in action trace ra terminal:

```text
[step 1] model selected list_chunks({})
[step 1] tool returned 184 characters; sending result back to model
[step 2] model selected read_chunk({'index': 1})
[step 2] tool returned 620 characters; sending result back to model
```

Trace này cho thấy model đã chọn tool nào, truyền tham số gì và nhận được bao nhiêu dữ liệu. Đây là các hành động quan sát được để demo agent loop; chương trình không in private chain-of-thought hoặc suy luận nội bộ chi tiết của model.

## Windows troubleshooting

Nếu chương trình đứng sau dòng `MCP tool call: run_terminal(...)`, hãy cập nhật `mcp_server.py` bản mới nhất. Tool terminal đã được cấu hình `stdin=subprocess.DEVNULL` và timeout 5 giây để không giữ nhầm stdin của MCP stdio trên Windows.

Kiểm tra Ollama trước khi chạy agent:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
python agent.py "Is uTorrent whitelist or blacklist?"
```

Lần gọi model đầu tiên cũng có thể mất vài giây vì Ollama phải load model vào VRAM. Nếu cần xem log chi tiết, mở `agent.log` trong thư mục này.
