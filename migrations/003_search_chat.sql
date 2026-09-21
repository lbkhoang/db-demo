CREATE EXTENSION IF NOT EXISTS unaccent;
ALTER TABLE chunks ADD COLUMN search_vector tsvector;
CREATE FUNCTION update_chunk_search() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple', unaccent(NEW.text));
    RETURN NEW;
END;
$$;
CREATE TRIGGER chunk_search BEFORE INSERT OR UPDATE OF text ON chunks
FOR EACH ROW EXECUTE FUNCTION update_chunk_search();
UPDATE chunks SET search_vector=to_tsvector('simple', unaccent(text));
CREATE INDEX chunks_fts_idx ON chunks USING gin(search_vector);
CREATE TABLE conversations (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    role text NOT NULL CHECK (role IN ('user','assistant')),
    content text NOT NULL,
    citations jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_conversation_idx ON messages(conversation_id,id);
