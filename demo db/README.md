# Portable DB demo

Folder này chạy trực tiếp bằng Python `venv`, không khởi động Docker. Máy khách chỉ cần chuẩn bị PostgreSQL + pgvector và Ollama ở local. Mặc định kết nối `localhost`; sửa `.env` nếu cần.

## Chuẩn bị

```powershell
cd ".\demo db"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python db_init.py
python healthcheck.py
```

Ollama cần có `qwen3-embedding:0.6b` và model chat được khai báo trong `.env`.

## Ingest

Chỉ cần bỏ Word/PDF vào thư mục `docs/`, rồi chạy:

```powershell
python ingest.py
```

Để xóa dữ liệu demo hiện tại và import lại toàn bộ thư mục:

```powershell
python ingest.py reset
```

Version tự đọc từ suffix:

```text
docs/hr_policy_v0.1.docx
docs/hr_policy_v0.2.docx
docs/bonus_policy_v0.1.docx
docs/bonus_policy_v0.2.docx
```

File không có suffix sẽ nhận minor tiếp theo. File trùng checksum được bỏ qua; hai file trùng version sẽ làm lệnh dừng để tránh ghi đè.

Flow ingest là: quét `docs/` → lưu file gốc → Word render sang PDF → đọc text theo page → gọi Ollama embedding → insert document/version/page/chunk/vector vào PostgreSQL. Cuối lệnh in số lượng document, version, page và chunk. LibreOffice cần có trong PATH cho Word; PDF có text không cần LibreOffice. OCR chưa hỗ trợ.

## Chat terminal

```powershell
python chat.py
python chat.py "Theo HR-01, nhân viên được nghỉ phép bao nhiêu ngày?"
python chat.py --version-id <VERSION_UUID> "Chính sách của version này là gì?"
python chat.py --compare-version <OLD_VERSION_UUID>
```

Chat thường dùng version `ready` mới nhất. Compare nhận một version cũ rồi tự lấy version mới nhất cùng tài liệu. Kết quả in câu trả lời và citation `[C<chunk_id>] file · page`.

## Files

- `ingest.py`: lệnh duy nhất cho ingest (`reset` là tham số duy nhất).
- `chat.py`: chat/search trực tiếp với PostgreSQL và Ollama.
- `db_init.py`, `schema.sql`: khởi tạo database demo.
- `healthcheck.py`: kiểm tra DB, pgvector, Ollama và embedding dimension.
- `docs/`: nơi khách bỏ file cần demo.
- `.env.example`: cấu hình local.

## Demo chunk theo header

Mặc định ingest dùng chunk theo page để giữ hành vi cũ. Để tách theo Markdown heading và lưu đường dẫn mục vào `chunks.section_path`, đặt trong `.env`:

```text
CHUNK_STRATEGY=header
```

Sau đó chạy lại `python ingest.py reset`. Ví dụ `# Leave` rồi `## Request` sẽ được lưu với section path `Leave > Request`; citation của `chat.py` cũng in section này.

## Demo agent loop

Agent loop minh họa cách model gọi search lần đầu, tự nhận evidence, rồi gọi search thêm khi evidence chưa đủ. Chạy từ root project khi API, PostgreSQL và Ollama đang sẵn sàng:

```powershell
python scripts/agent_loop_demo.py "Tóm tắt HR-01 và HR-02, gồm ngày phép và remote work."
```

Mỗi lần gọi search được in ra terminal; loop tối đa ba lần và cuối cùng trả lời từ toàn bộ evidence đã gom.

## Demo software whitelist/blacklist

File mẫu nằm ở `docs/software_list_v0.1.md`. File có hai section `Whitelist` và `Blacklist`, vì vậy phù hợp để demo chunk theo header.

```powershell
# trong thư mục demo db
$env:CHUNK_STRATEGY="header"
python ingest.py reset

# terminal chat: câu 1
python chat.py "Phần mềm uTorrent là whitelist hay blacklist?"

# câu 2: agent loop lấy một nhóm
cd ..
python scripts/agent_loop_demo.py "Lấy toàn bộ blacklist trong danh sách phần mềm."

# câu 3: tổng hợp cả danh sách
python scripts/agent_loop_demo.py "Lấy tất cả phần mềm trong danh sách và tổng hợp phần nào blacklist, phần nào whitelist."
```

Agent loop in từng lần gọi search. Nếu evidence chưa đủ, model gọi lại tool với query bổ sung trước khi tổng hợp câu trả lời.
