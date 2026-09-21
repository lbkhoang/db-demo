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

Mở http://localhost:8000/docs. `/health/ready` kiểm tra database, MCP tool và Ollama API; HTTP 200 ở đây chưa có nghĩa model đã tải hoặc chat RAG đã sẵn sàng. Task nền tảng chưa có upload/chat UI.

## Model checkpoint

Các lệnh sau tải model vào volume riêng của project; lần đầu có thể mất nhiều thời gian/dung lượng. Chat model là ứng viên benchmark, chưa chốt cấu hình tối ưu cho 16 GB VRAM.

```powershell
docker compose exec ollama ollama pull qwen3-embedding:0.6b
docker compose exec ollama ollama pull qwen3.6:27b
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
