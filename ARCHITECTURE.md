# Kiến trúc RAG terminal

Demo chạy bằng Docker, chỉ dùng terminal. Người dùng upload một file, worker parse/chunk/embed, rồi terminal chat hỏi dữ liệu trong PostgreSQL + pgvector.

## Thành phần

- FastAPI: API upload, search và chat SSE cho terminal client.
- PostgreSQL + pgvector: lưu document, page, chunk, vector và lịch sử chat.
- Ollama: chat model và embedding model chạy local.
- MCP server: expose `search_documents` cho model.
- Worker: đọc job PostgreSQL, chuyển Word/PDF sang text, chunk và embed.

## Flow

1. `POST /documents` lưu một file và tạo một document/job duy nhất.
2. Worker đọc file, tách page, chunk theo page hoặc header (`CHUNK_STRATEGY=header`), rồi lưu vector.
3. `POST /search` hoặc terminal chat tìm hybrid/vector/keyword trên toàn bộ document ready.
4. Model trả lời từ evidence và citation `[C<chunk_id>]`.
5. `scripts/agent_loop_demo.py` minh họa agent gọi search thêm khi evidence chưa đủ.

Không có khái niệm document version hoặc compare trong schema và API. Muốn cập nhật tài liệu, xóa file cũ rồi ingest file mới.

## Schema

`migrations/schema.sql` là file SQL duy nhất, tạo:

- `documents`: metadata, storage path, checksum, trạng thái ingest.
- `pages`: text theo trang.
- `chunks`: text, `section_path`, embedding và full-text vector.
- `ingestion_jobs`: queue và retry.
- `conversations/messages`: lịch sử chat.

Nếu database đã tạo theo schema cũ có document version, reset volume PostgreSQL trước khi chạy schema mới:

```powershell
docker compose down -v
docker compose up -d --build
```

## Demo phần mềm

File mẫu: `examples/software_list_v0.1.md`.

```powershell
# ingest file mẫu qua API/worker hoặc upload file tương tự
python scripts/agent_loop_demo.py "Phần mềm uTorrent là whitelist hay blacklist?"
python scripts/agent_loop_demo.py "Lấy toàn bộ blacklist trong danh sách phần mềm."
python scripts/agent_loop_demo.py "Lấy tất cả phần mềm và tổng hợp blacklist hay whitelist."
```
