mình cần 1 project docker, nền python, demo được rag,
stack:
ollama
qwen3.6
postgress
pgvector
mcp
fastapi

nội dung cần làm
user chat ở fe, có thể up file
qwen reasoning và call mcp
lấy data từ db vecto và trả lời

về phần file, parse theo chunk và insert theo page, hãy demo 2 file doc có 10 page về hr policy và khoản thưởng, mỗi page 1 câu để search là được

db postgress thì lưu thông tin file, ngày up và version

file mặc định sẽ có _v0.1 và tăng dần ở cuối tên
demo được có thể lưu file nhiều version và reasoning giữa các version
có thể demo được hybrid search nữa
Current demo scope: terminal only, no frontend. The sample software policy is `examples/software_list_v0.1.md` and supports whitelist/blacklist lookup, category listing through the agent loop, and full inventory summarization.\n