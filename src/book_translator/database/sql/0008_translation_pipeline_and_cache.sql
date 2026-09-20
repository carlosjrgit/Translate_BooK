-- 0008_translation_pipeline_and_cache.sql
-- Tabela de cache de traduções indexada e índices para o pipeline incremental

CREATE TABLE IF NOT EXISTS translation_cache (
    cache_key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    model_name TEXT NOT NULL,
    runtime TEXT NOT NULL,
    parameters_json TEXT DEFAULT '{}',
    context_hash TEXT NOT NULL,
    glossary_terms_json TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cache_project_segment ON translation_cache(project_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_cache_key ON translation_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_translations_segment_rank ON translations(segment_id, candidate_rank);
CREATE INDEX IF NOT EXISTS idx_translations_selected ON translations(segment_id, is_selected);
