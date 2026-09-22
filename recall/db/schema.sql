-- Schema for Recall Temporal Entity Memory Engine

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('person', 'organization', 'location', 'event', 'concept')),
    canonical_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_name);

CREATE TABLE IF NOT EXISTS facts (
    version_id TEXT PRIMARY KEY,
    logical_id TEXT NOT NULL,
    subject_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    predicate TEXT NOT NULL,
    object_value TEXT NOT NULL,
    object_entity_id TEXT REFERENCES entities(id) ON DELETE SET NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source_type TEXT NOT NULL CHECK (source_type IN ('direct_statement', 'inference', 'hearsay', 'user_edit')),
    source_ref TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    tx_from TEXT NOT NULL,
    tx_to TEXT,
    fact_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_logical ON facts(logical_id);
CREATE INDEX IF NOT EXISTS idx_facts_subject_pred ON facts(subject_id, predicate);
CREATE INDEX IF NOT EXISTS idx_facts_valid_interval ON facts(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_facts_tx_interval ON facts(tx_from, tx_to);
CREATE INDEX IF NOT EXISTS idx_facts_hash ON facts(fact_hash);

CREATE TABLE IF NOT EXISTS relations (
    version_id TEXT PRIMARY KEY,
    logical_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    target_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL,
    strength REAL NOT NULL CHECK (strength >= 0.0 AND strength <= 1.0),
    source_ref TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    tx_from TEXT NOT NULL,
    tx_to TEXT
);

CREATE INDEX IF NOT EXISTS idx_relations_logical ON relations(logical_id);
CREATE INDEX IF NOT EXISTS idx_relations_source_target ON relations(source_id, target_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_valid_interval ON relations(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_relations_tx_interval ON relations(tx_from, tx_to);

CREATE TABLE IF NOT EXISTS reinforcements (
    id TEXT PRIMARY KEY,
    logical_fact_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    reinforced_at TEXT NOT NULL,
    tx_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reinforcements_logical ON reinforcements(logical_fact_id);
CREATE INDEX IF NOT EXISTS idx_reinforcements_time ON reinforcements(reinforced_at, tx_time);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    speaker TEXT,
    raw_text TEXT,
    conv_id TEXT,
    event_time TEXT NOT NULL,
    tx_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_msg ON sources(message_id);

CREATE TABLE IF NOT EXISTS string_embeddings (
    text_hash TEXT PRIMARY KEY,
    embedding_json TEXT NOT NULL
);
