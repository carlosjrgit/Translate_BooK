-- Enriquecimento de Memórias e Tabela de Auditoria
-- Versão 4

ALTER TABLE characters ADD COLUMN treatment TEXT DEFAULT '';
ALTER TABLE characters ADD COLUMN evidences_json TEXT DEFAULT '[]';
ALTER TABLE characters ADD COLUMN confidence REAL DEFAULT 1.0;
ALTER TABLE characters ADD COLUMN history_json TEXT DEFAULT '[]';

ALTER TABLE glossary ADD COLUMN history_json TEXT DEFAULT '[]';

ALTER TABLE translation_memory ADD COLUMN context TEXT DEFAULT '';
ALTER TABLE translation_memory ADD COLUMN origin TEXT DEFAULT 'user';
ALTER TABLE translation_memory ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE translation_memory ADD COLUMN confidence REAL DEFAULT 1.0;
ALTER TABLE translation_memory ADD COLUMN history_json TEXT DEFAULT '[]';

CREATE TABLE IF NOT EXISTS memory_audit_log (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    term_or_name TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT DEFAULT '',
    new_value TEXT DEFAULT '',
    changed_by TEXT DEFAULT 'user',
    reason TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_audit_project_id ON memory_audit_log(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_audit_entry_id ON memory_audit_log(entry_id);
CREATE INDEX IF NOT EXISTS idx_memory_audit_memory_type ON memory_audit_log(memory_type);
