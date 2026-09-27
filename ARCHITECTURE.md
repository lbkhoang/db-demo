# Architecture

## Purpose

This is a terminal-only RAG demo. There is no upload endpoint. A user places files in a local folder, runs a batch command, and asks questions against PostgreSQL and pgvector.

## Components

- **FastAPI** exposes read-only document/job status, search, and streaming chat endpoints.
- **Batch CLI** scans the mounted local folder, deduplicates by checksum, copies files to the data volume, and creates ingestion jobs.
- **PostgreSQL + pgvector** stores document metadata, pages, chunks, embeddings, and chat history.
- **Ollama** runs the chat and embedding models locally.
- **MCP server** exposes the bounded `search_documents` tool to the model.
- **Worker** converts Word/PDF files, extracts text, chunks it, embeds it, and publishes the result.

## Data flow

1. Copy source files into local `app/data`.
2. Run `docker compose exec app python -m scripts.batch_ingest`.
3. The batch CLI validates extensions/size, skips duplicate checksums, copies each file to `/data/files`, and creates one job.
4. The worker extracts pages and chunks them. `CHUNK_STRATEGY=header` keeps Markdown heading paths in `chunks.section_path`.
5. Terminal chat searches all ready documents and answers with `[C<chunk_id>]` citations.

## Database schema

The complete schema is in [`migrations/schema.sql`](migrations/schema.sql). It contains `documents`, `pages`, `chunks`, `ingestion_jobs`, `conversations`, and `messages`.

If an old PostgreSQL volume contains the previous upload/version schema, reset it once:

```powershell
docker compose down -v
docker compose up -d --build
```

## Batch behavior

The batch command accepts `.doc`, `.docx`, `.pdf`, `.md`, and `.txt`. It is safe to run repeatedly: an identical checksum is skipped. A changed file becomes a new document record. Failed jobs can be retried through `POST /jobs/{job_id}/retry`.

## Agent loop

The agent demo gives the model one tool, `search_documents`. The host executes each requested search, appends the returned evidence, and allows up to three calls so follow-up retrieval is visible in the terminal.\n

See [docs/RAG_FLOWS.md](docs/RAG_FLOWS.md) for the common RAG, direct chunking, and Markdown conversion flows.\n