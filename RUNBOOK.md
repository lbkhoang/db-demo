# Chạy task nền tảng

Kiến trúc: [ARCHITECTURE.md](ARCHITECTURE.md). Tiến độ: [TASKS.md](TASKS.md).

Yêu cầu Docker Desktop đang chạy Linux containers/WSL2 và driver NVIDIA hỗ trợ GPU trong Docker.

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec ollama nvidia-smi
docker compose exec app python -m scripts.smoke
```

Mở http://localhost:8000/docs. Có thể upload trực tiếp qua Swagger ở `POST /documents`, thêm version qua `POST /documents/{document_id}/versions`, xem trạng thái qua `GET /jobs/{job_id}` và nội dung qua `GET /versions/{version_id}/pages`.

`/health/ready` kiểm tra database, MCP tool và Ollama API; HTTP 200 ở đây chưa có nghĩa model đã tải. Frontend chat ở http://localhost:8000.

## Chat và search

```powershell
docker compose exec ollama ollama pull qwen3:4b
docker compose exec app python -m scripts.test_search_chat
docker compose exec app python -m scripts.test_search_chat --chat
```

Ở giao diện, chọn tài liệu hoặc để tất cả bản ready mới nhất. Hỏi “Theo HR-01, nhân viên được nghỉ phép bao nhiêu ngày mỗi năm?”. Muốn so sánh: chọn tài liệu HR, giữ Ctrl chọn hai version, bật “So sánh hai phiên bản”, rồi hỏi “HR-01 và HR-02 thay đổi thế nào?”. Mở từng nguồn bên dưới câu trả lời để xem file, version, trang và đoạn văn.

API `POST /search` nhận query/mode/version_ids/top_k. `POST /chat` nhận message/conversation_id/mode/version_ids/compare và trả SSE status/delta/done/error. Chỉ sự kiện done chứa câu trả lời cuối đã kiểm tra citation; nếu có error hoặc mất kết nối, lượt chat chưa hoàn tất. `GET /conversations/{id}/messages` đọc lịch sử đã lưu. UI giữ conversation ID trong phiên trang hiện tại; reload bắt đầu phiên mới, lịch sử cũ vẫn trong DB.

Mặc định `CHAT_THINK=false`, context 4096 và một lượt chat đồng thời để phù hợp demo. Có thể bật thinking trong `.env` rồi recreate app; thời gian và context phải đo lại. Vector phù hợp câu hỏi ngữ nghĩa; mã ngắn như HR-01 nên dùng keyword/hybrid. Benchmark chat dùng model thật, không mock; test tạo các hội thoại kiểm thử trong DB.

## Upload và dữ liệu demo

```powershell
docker compose exec ollama ollama pull qwen3-embedding:0.6b
docker compose exec app python -m scripts.seed_demo
docker compose exec app python -m scripts.test_ingestion
```

Seed tạo 4 file Word × 10 trang với dữ liệu giả lập HR/thưởng, upload qua API và xác minh nội dung từng trang. File mẫu cùng manifest lưu trong volume ở `/data/files/demo`; chạy lại seed dùng manifest, không upload thêm bản nếu đã có. Muốn lấy file mẫu về workspace:

```powershell
New-Item -ItemType Directory -Force data
docker compose cp app:/data/files/demo data/demo
```

Integration test tạo tài liệu riêng, kiểm tra version đồng thời, PDF, embedding 1024 chiều, retry hữu hạn, latest-ready và reprocess không trùng chunks; khi thành công xóa riêng dữ liệu test. Word/PDF gốc lưu bất biến theo UUID trong volume; Word có thêm bản `.rendered.pdf`. Worker tự retry tối đa 3 lần; sau khi sửa nguyên nhân có thể gọi `POST /jobs/{id}/retry`.

## Model checkpoint

Các lệnh sau tải model vào volume riêng của project; lần đầu có thể mất nhiều thời gian/dung lượng. Chat model là ứng viên benchmark, chưa chốt cấu hình tối ưu cho 16 GB VRAM.

```powershell
docker compose exec ollama ollama pull qwen3-embedding:0.6b
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama list
docker compose exec app python -m scripts.benchmark
docker compose exec ollama ollama ps
```

Khi đổi tag cần sửa `.env`. Benchmark tiếp theo phải kiểm tra embedding dimension, tool call thật qua MCP, câu trả lời sau tool, context 4096, độ trễ và RAM/VRAM. Không dùng kết quả healthcheck thay benchmark.

## Vận hành

```powershell
docker compose logs --tail 100 app mcp-server migrate ollama
docker compose run --rm migrate
docker compose stop
docker compose start
```

Migration chạy lại an toàn, từ chối SQL đã áp dụng bị thay đổi. `docker compose down` giữ named volumes; không thêm `-v` nếu muốn giữ database/model. Không chia sẻ `.env`. Dependency ranges và image tags hiện phục vụ bootstrap, cần pin bản đã kiểm chứng trước khi đóng gói demo.
