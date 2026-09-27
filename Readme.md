# Terminal RAG Demo

A small Docker-based RAG demo for a customer walkthrough. The demo has no frontend: all user interaction happens from the terminal.

The stack uses Python, FastAPI, PostgreSQL with pgvector, Ollama, MCP, and one PostgreSQL-backed ingestion worker. A document is uploaded once, split into page or header-aware chunks, embedded, and searched when a user asks a question.

## Software policy demo

The sample file is [`examples/software_list_v0.1.md`](examples/software_list_v0.1.md). It contains a whitelist and a blacklist.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
python scripts/agent_loop_demo.py "Is uTorrent whitelist or blacklist?"
python scripts/agent_loop_demo.py "List every blacklist item."
python scripts/agent_loop_demo.py "List every software item and classify it as whitelist or blacklist."
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and [RUNBOOK.md](RUNBOOK.md) for operational commands.
