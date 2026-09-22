CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY, title text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS document_versions (
    id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id),
    major integer NOT NULL DEFAULT 0 CHECK (major >= 0), minor integer NOT NULL CHECK (minor > 0),
    original_name text NOT NULL, filename text NOT NULL, storage_path text NOT NULL,
    checksum text NOT NULL, uploaded_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','failed')),
    page_count integer, UNIQUE(document_id,major,minor)
);
CREATE TABLE IF NOT EXISTS pages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number integer NOT NULL CHECK (page_number > 0), text text NOT NULL,
    UNIQUE(version_id,page_number)
);
CREATE TABLE IF NOT EXISTS chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id bigint NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL, text text NOT NULL,
    embedding vector(1024) NOT NULL, embedding_model text NOT NULL,
    search_vector tsvector, UNIQUE(page_id,chunk_index)
);
CREATE INDEX IF NOT EXISTS chunks_vector_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING gin(search_vector);
CREATE OR REPLACE FUNCTION demo_update_search() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.search_vector := to_tsvector('simple', unaccent(NEW.text)); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS demo_chunk_search ON chunks;
CREATE TRIGGER demo_chunk_search BEFORE INSERT OR UPDATE OF text ON chunks
FOR EACH ROW EXECUTE FUNCTION demo_update_search();
