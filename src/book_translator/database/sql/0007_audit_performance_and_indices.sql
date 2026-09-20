-- Migration 0007: Índices de Auditoria, Performance e Integridade Relacional
-- Versão 7

-- 1. Índices compostos para busca rápida de termos no Glossário e Translation Memory
CREATE INDEX IF NOT EXISTS idx_glossary_proj_term ON glossary (project_id, source_term);
CREATE INDEX IF NOT EXISTS idx_tm_proj_term ON translation_memory (project_id, source_term);

-- 2. Índices compostos para entidades e personagens por nome canônico
CREATE INDEX IF NOT EXISTS idx_entities_proj_name ON entities (project_id, name);
CREATE INDEX IF NOT EXISTS idx_characters_proj_name ON characters (project_id, name);

-- 3. Índices de ordenação e paginação para unidades de leitura
CREATE INDEX IF NOT EXISTS idx_segments_chap_order ON segments (chapter_id, order_index);
CREATE INDEX IF NOT EXISTS idx_paragraphs_chap_order ON paragraphs (chapter_id, order_index);
CREATE INDEX IF NOT EXISTS idx_sections_chap_order ON sections (chapter_id, order_index);

-- 4. Índice de contexto por chave primária de segmento
CREATE INDEX IF NOT EXISTS idx_contexts_segment_id ON contexts (segment_id);
