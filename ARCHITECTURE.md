# Architecture

## Purpose

This is a terminal-only RAG demo. A user uploads a document, a worker indexes it, and a terminal client asks questions against PostgreSQL and pgvector.

## Components

- **FastAPI** exposes upload, search, and streaming chat endpoints.
- **PostgreSQL + pgvector** stores document metadata, pages, chunks, embeddings, and chat history.
- **Ollama** runs the chat and embedding models locally.
- **MCP server** exposes the bounded `search_documents` tool to the model.
- **Worker** converts Word/PDF files, extracts text, chunks it, embeds it, and publishes the result.

## Data flow

1. `POST /documents` stores one file and creates one ingestion job.
2. The worker extracts pages and chunks each page. `CHUNK_STRATEGY=header` keeps Markdown heading paths in `chunks.section_path`.
3. `POST /search` and terminal chat search all ready documents with vector, keyword, or hybrid retrieval.
4. The model answers only from returned evidence and cites `[C<chunk_id>]`.
5. `scripts/agent_loop_demo.py` shows an agent calling search again when the first evidence set is incomplete.

There is no document-version or compare layer. To replace a document, remove the old record/file and ingest the new file.

## Database schema

The complete schema is in [`migrations/schema.sql`](migrations/schema.sql):

- `documents`: file metadata, checksum, storage path, and processing status.
- `pages`: extracted text grouped by page.
- `chunks`: text, `section_path`, embedding, and PostgreSQL full-text vector.
- `ingestion_jobs`: queue state, retry count, and errors.
- `conversations` and `messages`: completed chat history and citations.

If a PostgreSQL volume was created with the previous versioned schema, reset it once before starting the new schema:

```powershell
docker compose down -v
docker compose up -d --build
```

## Chunking

`page` is the default strategy and keeps the existing page-based behavior. `header` detects Markdown headings such as `# Whitelist` and `# Blacklist`, then stores the active heading path with each chunk.

## Agent loop

The agent demo gives the model one tool, `search_documents`. The host executes each requested search, appends the returned evidence to the conversation, and allows up to three calls. This makes follow-up retrieval visible in the terminal without exposing SQL to the model.
