# Runbook

## Start the stack

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

The migrate service applies the single [`migrations/schema.sql`](migrations/schema.sql) file. Upload a document and keep the returned job ID:

```powershell
curl.exe -F "file=@examples/software_list_v0.1.md" -F "title=Software policy" http://localhost:8000/documents
curl.exe http://localhost:8000/jobs/<JOB_ID>
```

## Terminal questions

```powershell
python -m scripts.chat_cli "Is uTorrent whitelist or blacklist?"
python scripts/agent_loop_demo.py "List every blacklist item."
python scripts/agent_loop_demo.py "List every software item and classify it as whitelist or blacklist."
```

The agent loop prints every retrieval call and then prints the final answer. It stops after three retrieval calls and tells the model to disclose missing evidence.

## Header-aware chunks

Set this in `.env` before starting the worker:

```text
CHUNK_STRATEGY=header
```

The worker stores heading paths such as `Whitelist` or `Blacklist` in `chunks.section_path`.

## Checks

```powershell
python -m compileall -q app scripts
python -m scripts.test_chunking
git diff --check
```
