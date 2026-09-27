# Terminal RAG Demo

A small Docker-based RAG demo for a customer walkthrough. The demo has no frontend and no upload API: all ingestion starts from a local batch folder.

The stack uses Python, FastAPI, PostgreSQL with pgvector, Ollama, MCP, and one PostgreSQL-backed ingestion worker. Put documents in `app/data`, run the batch command, and then ask questions from the terminal.

## Software policy demo

The sample file is [`examples/software_list_v0.1.md`](examples/software_list_v0.1.md).

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force app/data | Out-Null
Copy-Item examples/software_list_v0.1.md app/data/
docker compose up -d --build
docker compose exec app python -m scripts.batch_ingest
```

Ask questions:

```powershell
docker compose exec app python -m scripts.chat_cli "Is uTorrent whitelist or blacklist?"
docker compose exec app python scripts/agent_loop_demo.py "List every blacklist item."
docker compose exec app python scripts/agent_loop_demo.py "List every software item and classify it as whitelist or blacklist."
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for design and [RUNBOOK.md](RUNBOOK.md) for operations.\n

The ingestion and retrieval diagrams are in [docs/RAG_FLOWS.md](docs/RAG_FLOWS.md).\n