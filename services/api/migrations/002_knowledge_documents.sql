CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id UUID PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    source VARCHAR(128) NOT NULL DEFAULT 'filesystem',
    domain VARCHAR(64) NOT NULL DEFAULT 'shared',
    checksum VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'discovered',
    summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    summarized_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_domain ON knowledge_documents (domain);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status ON knowledge_documents (status);
