-- =============================================================================
-- DocuMind — PostgreSQL Initialization Script
-- Sets up pgvector extension + full database schema
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ─── Document Status Enum ───────────────────────────────────────────────────
CREATE TYPE document_status AS ENUM ('uploading', 'processing', 'chunking', 'embedding', 'ready', 'error');
CREATE TYPE chunk_type AS ENUM ('parent', 'child');

-- ─── Documents Table ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         VARCHAR(255) NOT NULL,          -- Clerk user ID
    filename        VARCHAR(500) NOT NULL,          -- stored filename (hashed)
    original_name   VARCHAR(500) NOT NULL,          -- original upload name
    file_size       INTEGER NOT NULL,               -- bytes
    file_hash       VARCHAR(64),                    -- SHA-256 for dedup
    page_count      INTEGER DEFAULT 0,
    total_chunks    INTEGER DEFAULT 0,
    status          document_status DEFAULT 'uploading',
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Chunks Table ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,               -- order within document
    page_number     INTEGER,                        -- source page in PDF
    page_numbers    INTEGER[],                      -- may span multiple pages
    chunk_kind      chunk_type DEFAULT 'child',
    parent_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
    start_char      INTEGER,                        -- char offset in full text
    end_char        INTEGER,
    bbox            JSONB,                          -- bounding box for highlights
    embedding       vector(3072),                   -- Gemini embedding-2
    token_count     INTEGER DEFAULT 0,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Conversations Table ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         VARCHAR(255) NOT NULL,          -- Clerk user ID
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title           VARCHAR(500) NOT NULL DEFAULT 'New Chat',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Query History Table ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         VARCHAR(255) NOT NULL,          -- Clerk user ID
    document_id     UUID REFERENCES documents(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    query_text      TEXT NOT NULL,
    answer_text     TEXT,
    citations       JSONB DEFAULT '[]',             -- [{chunk_id, page, text_snippet}]
    agent_steps     JSONB DEFAULT '[]',             -- LangGraph execution log
    sub_queries     JSONB DEFAULT '[]',             -- decomposed sub-queries
    latency_ms      INTEGER,
    token_usage     JSONB DEFAULT '{}',             -- {prompt_tokens, completion_tokens}
    cached          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Evaluations Table (Ragas Metrics) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS evaluations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id            UUID NOT NULL REFERENCES query_history(id) ON DELETE CASCADE,
    document_id         UUID REFERENCES documents(id) ON DELETE SET NULL,
    faithfulness        FLOAT,
    answer_relevancy    FLOAT,
    context_precision   FLOAT,
    context_recall      FLOAT,
    overall_score       FLOAT,                      -- weighted composite
    eval_metadata       JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Cache Entries Table (for tracking semantic cache stats) ────────────────
CREATE TABLE IF NOT EXISTS cache_entries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_hash      VARCHAR(64) NOT NULL,
    query_text      TEXT NOT NULL,
    query_embedding vector(1536),
    response_text   TEXT NOT NULL,
    citations       JSONB DEFAULT '[]',
    hit_count       INTEGER DEFAULT 0,
    document_id     UUID REFERENCES documents(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Vector similarity index (IVFFlat for fast ANN search)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Document lookups
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_parent_id ON chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_kind ON chunks(chunk_kind);

-- Full-text search index for BM25
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
    ON chunks USING gin(to_tsvector('english', content));

-- Query history lookups
CREATE INDEX IF NOT EXISTS idx_query_history_document ON query_history(document_id);
CREATE INDEX IF NOT EXISTS idx_query_history_conversation ON query_history(conversation_id);
CREATE INDEX IF NOT EXISTS idx_query_history_created ON query_history(created_at DESC);

-- Conversation lookups
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_document ON conversations(document_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

-- Evaluation lookups
CREATE INDEX IF NOT EXISTS idx_evaluations_query ON evaluations(query_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_document ON evaluations(document_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_created ON evaluations(created_at DESC);

-- Cache lookups
CREATE INDEX IF NOT EXISTS idx_cache_document ON cache_entries(document_id);
CREATE INDEX IF NOT EXISTS idx_cache_embedding
    ON cache_entries USING ivfflat (query_embedding vector_cosine_ops)
    WITH (lists = 50);

-- ─── Updated At Trigger ─────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Seed: Log successful initialization
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE '✅ DocuMind database initialized successfully!';
    RAISE NOTICE '   → pgvector extension enabled';
    RAISE NOTICE '   → Tables: documents, chunks, conversations, query_history, evaluations, cache_entries';
    RAISE NOTICE '   → Indexes: vector similarity, full-text search, foreign keys';
END $$;
