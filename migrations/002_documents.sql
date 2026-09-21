CREATE TABLE documents (
    id uuid PRIMARY KEY,
    title text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE document_versions (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id),
    major integer NOT NULL DEFAULT 0 CHECK (major >= 0),
    minor integer NOT NULL CHECK (minor > 0),
    original_name text NOT NULL,
    filename text NOT NULL,
    storage_path text NOT NULL,
    checksum text NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    effective_at date,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
    error text,
    page_count integer,
    UNIQUE(document_id, major, minor)
);
CREATE TABLE pages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number integer NOT NULL CHECK (page_number > 0),
    text text NOT NULL,
    UNIQUE(version_id, page_number)
);
CREATE TABLE chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id bigint NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    embedding vector(1024) NOT NULL,
    embedding_model text NOT NULL,
    UNIQUE(page_id, chunk_index)
);
CREATE TABLE ingestion_jobs (
    id uuid PRIMARY KEY,
    version_id uuid NOT NULL UNIQUE REFERENCES document_versions(id),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
    attempts integer NOT NULL DEFAULT 0,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ingestion_jobs_queue_idx ON ingestion_jobs(status, created_at);
CREATE INDEX document_versions_document_idx ON document_versions(document_id, major DESC, minor DESC);
