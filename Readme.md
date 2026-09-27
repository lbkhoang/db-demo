# RAG terminal demo

Project Python + Docker dùng PostgreSQL/pgvector, Ollama, MCP và FastAPI. Demo không có frontend.

Dữ liệu mẫu nằm ở `examples/software_list_v0.1.md`, gồm whitelist và blacklist phần mềm. Hệ thống lưu một document duy nhất, chunk theo page hoặc header, embed vào PostgreSQL và trả lời qua terminal.

Các câu hỏi demo:

```powershell
python scripts/agent_loop_demo.py "Phần mềm uTorrent là whitelist hay blacklist?"
python scripts/agent_loop_demo.py "Lấy toàn bộ blacklist trong danh sách phần mềm."
python scripts/agent_loop_demo.py "Lấy tất cả phần mềm và tổng hợp blacklist hay whitelist."
```

Chi tiết kiến trúc và vận hành: [ARCHITECTURE.md](ARCHITECTURE.md), [RUNBOOK.md](RUNBOOK.md).
