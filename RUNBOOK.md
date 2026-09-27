# Runbook

## Start the stack

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force app/data | Out-Null
docker compose up -d --build
```

The migrate service applies the single [`migrations/schema.sql`](migrations/schema.sql) file. There is no upload endpoint. Put source files in the local `app/data` folder, then run one batch command:

```powershell
Copy-Item examples/software_list_v0.1.md app/data/
docker compose exec app python -m scripts.batch_ingest
docker compose logs -f worker
```

The batch command scans `.doc`, `.docx`, `.pdf`, `.md`, and `.txt` files, skips duplicate checksums, copies accepted files into the application volume, and queues the worker jobs.

## Terminal questions

```powershell
docker compose exec app python -m scripts.chat_cli "Is uTorrent whitelist or blacklist?"
docker compose exec app python scripts/agent_loop_demo.py "List every blacklist item."
docker compose exec app python scripts/agent_loop_demo.py "List every software item and classify it as whitelist or blacklist."
```

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


## Stop the Docker demo

Stop all services while keeping PostgreSQL and Ollama data:

```powershell
docker compose down
```

Stop the services and remove this project's volumes as well:

```powershell
docker compose down -v
```\n