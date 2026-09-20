-- Migration 0006: Suporte a Story Relationships e Diferenciação de Inferências
-- Versão 6

-- 1. Tabela de relações interpessoais ativas da obra
CREATE TABLE IF NOT EXISTS story_relationships (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_character_id TEXT NOT NULL,
    target_character_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    chapter_id TEXT DEFAULT '',
    evidence TEXT DEFAULT '',
    confidence REAL DEFAULT 1.0,
    is_inferred INTEGER DEFAULT 0,
    source_type TEXT DEFAULT 'explicit',
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_story_rel_proj ON story_relationships (project_id);
CREATE INDEX IF NOT EXISTS idx_story_rel_source ON story_relationships (project_id, source_character_id);
CREATE INDEX IF NOT EXISTS idx_story_rel_target ON story_relationships (project_id, target_character_id);
CREATE INDEX IF NOT EXISTS idx_story_rel_chap ON story_relationships (project_id, chapter_id);

-- 2. Adição de rastreabilidade de evidência e inferência nas tabelas existentes
ALTER TABLE character_states ADD COLUMN evidence TEXT DEFAULT '';
ALTER TABLE character_states ADD COLUMN confidence REAL DEFAULT 1.0;
ALTER TABLE character_states ADD COLUMN is_inferred INTEGER DEFAULT 0;
ALTER TABLE character_states ADD COLUMN source_type TEXT DEFAULT 'explicit';

ALTER TABLE story_events ADD COLUMN confidence REAL DEFAULT 1.0;
ALTER TABLE story_events ADD COLUMN is_inferred INTEGER DEFAULT 0;
ALTER TABLE story_events ADD COLUMN source_type TEXT DEFAULT 'explicit';

ALTER TABLE story_facts ADD COLUMN is_inferred INTEGER DEFAULT 0;
ALTER TABLE story_facts ADD COLUMN source_type TEXT DEFAULT 'explicit';

ALTER TABLE story_cross_references ADD COLUMN confidence REAL DEFAULT 1.0;
ALTER TABLE story_cross_references ADD COLUMN is_inferred INTEGER DEFAULT 0;
ALTER TABLE story_cross_references ADD COLUMN source_type TEXT DEFAULT 'explicit';
