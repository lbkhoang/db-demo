CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY,
    title text NOT NULL,
    original_name text NOT NULL,
    filename text NOT NULL,
    storage_path text NOT NULL,
    checksum text NOT NULL UNIQUE,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
    error text,
    page_count integer
);
CREATE TABLE IF NOT EXISTS pages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number integer NOT NULL CHECK (page_number > 0),
    text text NOT NULL,
    UNIQUE(document_id, page_number)
);
CREATE TABLE IF NOT EXISTS chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id bigint NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    section_path text NOT NULL DEFAULT '',
    text text NOT NULL,
    embedding vector(1024) NOT NULL,
    embedding_model text NOT NULL,
    search_vector tsvector,
    UNIQUE(page_id, chunk_index)
);
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
    attempts integer NOT NULL DEFAULT 0,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingestion_jobs_queue_idx ON ingestion_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS documents_uploaded_idx ON documents(uploaded_at DESC);

CREATE OR REPLACE FUNCTION update_chunk_search() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple', unaccent(NEW.text));
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS chunk_search ON chunks;
CREATE TRIGGER chunk_search BEFORE INSERT OR UPDATE OF text ON chunks
FOR EACH ROW EXECUTE FUNCTION update_chunk_search();
UPDATE chunks SET search_vector=to_tsvector('simple', unaccent(text));
CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING gin(search_vector);

CREATE TABLE IF NOT EXISTS conversations (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    role text NOT NULL CHECK (role IN ('user','assistant')),
    content text NOT NULL,
    citations jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages(conversation_id,id);
