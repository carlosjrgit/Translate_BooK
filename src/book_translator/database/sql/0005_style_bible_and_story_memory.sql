-- Migration 0005: Suporte à Style Bible enriquecida e Story/Context Memory
-- Versão 5

-- 1. Enriquecimento da tabela style_bible com novas dimensões e regras estruturadas
ALTER TABLE style_bible ADD COLUMN narrative_person TEXT DEFAULT '';
ALTER TABLE style_bible ADD COLUMN predominant_tense TEXT DEFAULT '';
ALTER TABLE style_bible ADD COLUMN formality_level TEXT DEFAULT '';
ALTER TABLE style_bible ADD COLUMN title_treatment TEXT DEFAULT '';
ALTER TABLE style_bible ADD COLUMN internal_conventions_json TEXT DEFAULT '[]';
ALTER TABLE style_bible ADD COLUMN rules_json TEXT DEFAULT '{}';

-- 2. Tabela de resumos de capítulos e seções
CREATE TABLE IF NOT EXISTS story_summaries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL DEFAULT 'chapter', -- 'chapter' ou 'section'
    unit_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    summary_text TEXT NOT NULL,
    key_events_json TEXT DEFAULT '[]',
    characters_present_json TEXT DEFAULT '[]',
    order_index INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabela de estados de personagens ao longo do enredo
CREATE TABLE IF NOT EXISTS character_states (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    character_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    alive_status TEXT DEFAULT 'alive',
    location TEXT DEFAULT '',
    emotional_state TEXT DEFAULT '',
    role_or_title TEXT DEFAULT '',
    known_facts_json TEXT DEFAULT '[]',
    order_index INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabela de eventos da história e linha do tempo
CREATE TABLE IF NOT EXISTS story_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id TEXT NOT NULL,
    unit_id TEXT DEFAULT '',
    description TEXT NOT NULL,
    characters_involved_json TEXT DEFAULT '[]',
    significance TEXT DEFAULT 'major',
    narrative_order INTEGER DEFAULT 0,
    chronological_order INTEGER DEFAULT 0,
    evidence TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabela de fatos persistentes (lore, regras do mundo, características fixas)
CREATE TABLE IF NOT EXISTS story_facts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'world_rule', -- 'lore', 'world_rule', 'character_attribute', 'setting', 'plot_fact'
    statement TEXT NOT NULL,
    subject_entity_ids_json TEXT DEFAULT '[]',
    evidence TEXT DEFAULT '',
    confidence REAL DEFAULT 1.0,
    locked INTEGER DEFAULT 0,
    occurrences_json TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabela de referências cruzadas entre trechos da obra
CREATE TABLE IF NOT EXISTS story_cross_references (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_unit_id TEXT NOT NULL,
    target_unit_id TEXT NOT NULL,
    ref_type TEXT NOT NULL DEFAULT 'callback', -- 'foreshadowing', 'callback', 'parallel', 'revelation', 'citation'
    description TEXT NOT NULL,
    evidence TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Índices para performance e consultas seletivas de contexto
CREATE INDEX IF NOT EXISTS idx_story_summaries_proj_unit ON story_summaries (project_id, unit_id);
CREATE INDEX IF NOT EXISTS idx_character_states_proj_char ON character_states (project_id, character_id);
CREATE INDEX IF NOT EXISTS idx_character_states_proj_chap ON character_states (project_id, chapter_id);
CREATE INDEX IF NOT EXISTS idx_story_events_proj_chap ON story_events (project_id, chapter_id);
CREATE INDEX IF NOT EXISTS idx_story_events_proj_chrono ON story_events (project_id, chronological_order);
CREATE INDEX IF NOT EXISTS idx_story_facts_proj_cat ON story_facts (project_id, category);
CREATE INDEX IF NOT EXISTS idx_story_cross_refs_source ON story_cross_references (project_id, source_unit_id);
