-- Migration 0009: Tabela de auditoria de correções automáticas de QA
CREATE TABLE IF NOT EXISTS qa_fix_audits (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    check_type TEXT NOT NULL,
    old_text TEXT NOT NULL,
    new_text TEXT NOT NULL,
    rule_applied TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_qa_fix_audits_segment_id ON qa_fix_audits(segment_id);
