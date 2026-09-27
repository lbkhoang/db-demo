# Runbook terminal

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

Migrate chạy tự động bằng `migrations/schema.sql`. Upload file qua API rồi theo dõi job:

```powershell
curl.exe -F "file=@examples/software_list_v0.1.md" -F "title=software policy" http://localhost:8000/documents
curl.exe http://localhost:8000/jobs/<JOB_ID>
```

Chat terminal:

```powershell
python -m scripts.chat_cli "Phần mềm uTorrent là whitelist hay blacklist?"
python scripts/agent_loop_demo.py "Lấy toàn bộ blacklist trong danh sách phần mềm."
python scripts/agent_loop_demo.py "Lấy tất cả phần mềm và tổng hợp blacklist hay whitelist."
```

Bật chunk theo header trong `.env`:

```text
CHUNK_STRATEGY=header
```

Kiểm tra code:

```powershell
python -m compileall -q app scripts
python -m scripts.test_chunking
```
