-- Adição de Índices de Performance e Integridade
-- Versão 2

CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_chapters_document_id ON chapters(document_id);
CREATE INDEX IF NOT EXISTS idx_sections_chapter_id ON sections(chapter_id);
CREATE INDEX IF NOT EXISTS idx_paragraphs_chapter_id ON paragraphs(chapter_id);
CREATE INDEX IF NOT EXISTS idx_segments_chapter_id ON segments(chapter_id);
CREATE INDEX IF NOT EXISTS idx_segments_status ON segments(status);
CREATE INDEX IF NOT EXISTS idx_entities_project_id ON entities(project_id);
CREATE INDEX IF NOT EXISTS idx_characters_project_id ON characters(project_id);
CREATE INDEX IF NOT EXISTS idx_glossary_project_id ON glossary(project_id);
CREATE INDEX IF NOT EXISTS idx_tm_project_id ON translation_memory(project_id);
CREATE INDEX IF NOT EXISTS idx_translations_segment_id ON translations(segment_id);
CREATE INDEX IF NOT EXISTS idx_revisions_segment_id ON revisions(segment_id);
CREATE INDEX IF NOT EXISTS idx_qa_issues_segment_id ON qa_issues(segment_id);
CREATE INDEX IF NOT EXISTS idx_project_events_project_id ON project_events(project_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_project_id ON checkpoints(project_id);
