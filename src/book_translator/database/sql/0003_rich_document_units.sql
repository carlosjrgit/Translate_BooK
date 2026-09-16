-- Representação Rica de Unidades Documentais
-- Versão 3

-- Atualização na tabela paragraphs para conter metadados ricos de formatação e ordem
ALTER TABLE paragraphs ADD COLUMN normalized_text TEXT DEFAULT '';
ALTER TABLE paragraphs ADD COLUMN reading_order INTEGER DEFAULT 0;
ALTER TABLE paragraphs ADD COLUMN spans_json TEXT DEFAULT '[]';
ALTER TABLE paragraphs ADD COLUMN source_location_json TEXT DEFAULT '{}';

CREATE TABLE IF NOT EXISTS headings (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    level INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    reading_order INTEGER NOT NULL,
    spans_json TEXT DEFAULT '[]',
    source_location_json TEXT DEFAULT '{}',
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS dialogues (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    dialogue_marker TEXT DEFAULT '—',
    speaker_hint TEXT,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    reading_order INTEGER NOT NULL,
    spans_json TEXT DEFAULT '[]',
    source_location_json TEXT DEFAULT '{}',
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS footnotes (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    marker TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    referencing_unit_id TEXT,
    reading_order INTEGER DEFAULT 0,
    source_location_json TEXT DEFAULT '{}',
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS references_bibliography (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    citation_key TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    url TEXT,
    reading_order INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    caption_raw TEXT DEFAULT '',
    caption_normalized TEXT DEFAULT '',
    alt_text TEXT DEFAULT '',
    relative_path TEXT DEFAULT '',
    original_src TEXT DEFAULT '',
    reading_order INTEGER NOT NULL,
    source_location_json TEXT DEFAULT '{}',
    metadata_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_headings_chapter_id ON headings(chapter_id);
CREATE INDEX IF NOT EXISTS idx_dialogues_chapter_id ON dialogues(chapter_id);
CREATE INDEX IF NOT EXISTS idx_footnotes_chapter_id ON footnotes(chapter_id);
CREATE INDEX IF NOT EXISTS idx_references_doc_id ON references_bibliography(document_id);
CREATE INDEX IF NOT EXISTS idx_images_chapter_id ON images(chapter_id);
