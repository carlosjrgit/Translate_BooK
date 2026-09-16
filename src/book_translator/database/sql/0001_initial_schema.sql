-- Schema Inicial do BookTranslator
-- Versão 1

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_file_path TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    source_lang TEXT DEFAULT 'en',
    target_lang TEXT DEFAULT 'pt-BR',
    status TEXT DEFAULT 'active',
    config_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    author TEXT DEFAULT 'Desconhecido',
    source_format TEXT DEFAULT 'unknown',
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    parent_section_id TEXT REFERENCES sections(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    order_index INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    section_id TEXT REFERENCES sections(id) ON DELETE SET NULL,
    order_index INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    paragraph_id TEXT REFERENCES paragraphs(id) ON DELETE SET NULL,
    section_id TEXT REFERENCES sections(id) ON DELETE SET NULL,
    order_index INTEGER NOT NULL,
    original_text TEXT NOT NULL,
    translated_text TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    original_hash TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    occurrences INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    gender TEXT DEFAULT 'neutral',
    speech_style TEXT DEFAULT '',
    linguistic_traits TEXT DEFAULT '',
    first_appearance TEXT DEFAULT '',
    occurrences INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    aliases_json TEXT DEFAULT '[]',
    relations_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS glossary (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    entry_type TEXT DEFAULT 'concept',
    description TEXT DEFAULT '',
    aliases_json TEXT DEFAULT '[]',
    case_sensitive INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 1,
    gender TEXT DEFAULT '',
    plural TEXT DEFAULT '',
    context TEXT DEFAULT '',
    first_occurrence TEXT DEFAULT '',
    occurrences INTEGER DEFAULT 0,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS translation_memory (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    entry_type TEXT DEFAULT 'phrase',
    locked INTEGER DEFAULT 1,
    first_chapter TEXT DEFAULT '',
    occurrences INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS style_bible (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    narrator TEXT DEFAULT 'terceira pessoa',
    register TEXT DEFAULT 'literário contemporâneo',
    dialogue_style TEXT DEFAULT 'natural em PT-BR',
    profanity_handling TEXT DEFAULT 'preservar intensidade do original',
    predominant_treatment TEXT DEFAULT 'você',
    punctuation_standard TEXT DEFAULT 'editorial brasileiro',
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS contexts (
    segment_id TEXT PRIMARY KEY REFERENCES segments(id) ON DELETE CASCADE,
    preceding_text_json TEXT DEFAULT '[]',
    succeeding_text_json TEXT DEFAULT '[]',
    chapter_summary TEXT DEFAULT '',
    active_characters_json TEXT DEFAULT '[]',
    relevant_glossary_json TEXT DEFAULT '[]',
    established_translations_json TEXT DEFAULT '[]',
    extra_metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS translations (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    translated_text TEXT NOT NULL,
    engine_name TEXT NOT NULL,
    candidate_rank INTEGER DEFAULT 1,
    score REAL DEFAULT 0.0,
    is_selected INTEGER DEFAULT 1,
    execution_time_ms REAL DEFAULT 0.0,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    old_text TEXT NOT NULL,
    new_text TEXT NOT NULL,
    revised_by TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS qa_issues (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    check_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    original_snippet TEXT DEFAULT '',
    translated_snippet TEXT DEFAULT '',
    suggested_fix TEXT,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    phase TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    last_chapter_id TEXT DEFAULT '',
    last_segment_id TEXT DEFAULT '',
    completed_segments INTEGER DEFAULT 0,
    total_segments INTEGER DEFAULT 0,
    status TEXT DEFAULT 'in_progress',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
