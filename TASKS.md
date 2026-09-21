# Tiến độ build

Quy ước: `[x]` hoàn thành và kiểm tra, `[ ]` chưa hoàn thành.

## T01 — Nền tảng (hạ tầng hoàn thành, còn benchmark model)

- [x] Đọc README, chốt kiến trúc và cấu hình máy.
- [x] Xác nhận Docker Desktop Linux engine và GPU host 16 GB.
- [x] Compose PostgreSQL/pgvector, Ollama GPU, FastAPI, MCP.
- [x] Migration runner, health endpoints, MCP handshake/tool smoke test.
- [x] Build và chạy các service; kiểm tra GPU bên trong container.
- [x] Thêm script benchmark embedding và Qwen → MCP → câu trả lời.
- [ ] Benchmark Qwen3.6 và embedding; chốt tag/digest theo kết quả.

### Kết quả kiểm tra ngày 2026-09-21

- `docker compose config --quiet`: pass.
- Python compile và import FastAPI/MCP trong image Python 3.12: pass.
- `docker compose up -d --build`: pass.
- `docker compose exec ollama nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv`: RTX 5060 Ti, 16311 MiB, driver 616.56.
- `docker compose exec app python -m scripts.smoke`: pass; pgvector 0.8.6, MCP tool `system_status` gọi database thành công, Ollama API OK.
- `docker compose run --rm migrate` lần hai: pass, không chạy lại migration đã áp dụng.
- Ollama chưa có model (`models: []`); chưa xác nhận inference, embedding dimension hoặc chất lượng/tốc độ Qwen. Chạy model checkpoint trong [RUNBOOK.md](RUNBOOK.md) là bước tiếp theo.
- Thư viện đã build: FastAPI 0.141.1, Uvicorn 0.53.0, HTTPX 0.28.1, Psycopg 3.3.6, MCP 1.30.0. Hiện chưa có lockfile đầy đủ.

## T02 — Upload và ingestion (hoàn thành)

- [x] Schema tài liệu/version/page/chunk/job và unique constraints.
- [x] Upload bất biến, cấp version có khóa, trạng thái và retry.
- [x] Worker Word → PDF → pages → chunks → embedding.
- [x] Kiểm tra dimension embedding; ingest idempotent và bản ready mặc định.

### Kết quả kiểm tra T02 ngày 2026-09-21

- Git local nhánh `main`, commit khởi tạo `c01f62e`; không cấu hình remote, không push. Thay đổi T02 ở working tree sau commit init.
- Tải `qwen3-embedding:0.6b` thành công; worker đã tạo vector thực tế 1024 chiều. Qwen3.6 chat benchmark vẫn chưa chạy.
- `scripts.seed_demo`: cả 4 file `.docx` render và ingest đúng 10 trang, xác minh nội dung tiếng Việt từng trang.
- `scripts.test_ingestion`: pass với PDF, file rỗng/đuôi không hỗ trợ, upload đồng thời v0.2/v0.3, file hỏng retry tối đa 3 lần, latest-ready không bị bản lỗi thay thế và retry không nhân đôi chunk.
- Worker chạy đơn bằng session advisory lock, lưu PDF render bên cạnh Word gốc. API upload/status/pages sử dụng được qua Swagger.
- Sau restart worker và chạy lại seed: vẫn đúng 2 tài liệu, 4 version, 40 trang, 40 chunk; smoke test API/MCP/Ollama pass. Bản sao file mẫu nằm ở `data/demo` (Git ignore).

## T03 — Search

- [ ] Vector, keyword tiếng Việt, hybrid RRF và bộ lọc trước top-k.
- [ ] MCP tools tìm kiếm, liệt kê version, đọc trang.
- [ ] Bộ câu hỏi và expected sources để đánh giá retrieval.

## T04 — Chat và so sánh

- [ ] Ollama/MCP tool loop, giới hạn vòng/timeout/context.
- [ ] Streaming, lịch sử chat, xác minh citations.
- [ ] So sánh version riêng biệt; xử lý thiếu bằng chứng.

## T05 — Frontend và demo

- [ ] Chat, upload/status, chọn version/search mode và xem nguồn.
- [x] Sinh 4 file Word × 10 trang và seed qua ingestion.
- [ ] Kiểm thử end-to-end, restart persistence, concurrent version, job retry.
- [ ] Hướng dẫn demo, kết quả benchmark và pin dependencies/images.
