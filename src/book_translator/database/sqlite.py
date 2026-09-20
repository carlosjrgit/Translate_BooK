"""Implementação concreta de DatabaseInterface em SQLite com suporte transacional completo."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from book_translator.context.base import TranslationContext
from book_translator.context.models import ContextItemScore, ContextMetrics, SemanticSnippet
from book_translator.core.models import (
    Chapter,
    Checkpoint,
    DialogueBlock,
    Document,
    DocumentMetadata,
    Entity,
    EventLog,
    Footnote,
    FormattingSpan,
    Heading,
    ImagePlaceholder,
    Paragraph,
    Project,
    ProjectMetadata,
    Reference,
    Section,
    Segment,
    SegmentStatus,
    SourceLocation,
)
from book_translator.database.base import DatabaseInterface
from book_translator.database.connection import get_sqlite_connection, transaction, wal_checkpoint
from book_translator.database.migrations import apply_migrations
from book_translator.errors import DatabaseError
from book_translator.memory.base import (
    ChapterSummary,
    CharacterEntry,
    CharacterState,
    GlossaryEntry,
    MemoryRevision,
    PersistentFact,
    StoryCrossReference,
    StoryEvent,
    StoryMemory,
    StoryRelationship,
    StyleBible,
    StyleRule,
    TranslationMemoryEntry,
)
from book_translator.qa.base import (
    IssueSeverity,
    QAFixAuditRecord,
    QAIssue,
    QAReport,
)
from book_translator.translation.base import TranslationDraft


class SQLiteDatabase(DatabaseInterface):
    """Implementação transacional do banco de dados do projeto sobre SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.conn = get_sqlite_connection(self.db_path)

    def initialize(self) -> None:
        """Aplica todas as migrations necessárias no banco de dados."""
        apply_migrations(self.conn)

    # -------------------------------------------------------------------------
    # Projetos e Documentos
    # -------------------------------------------------------------------------
    def save_project(self, project: Project) -> None:
        meta = project.metadata
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO projects (
                    id, title, source_file_path, source_file_sha256,
                    source_lang, target_lang, status, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    source_file_path=excluded.source_file_path,
                    source_file_sha256=excluded.source_file_sha256,
                    source_lang=excluded.source_lang,
                    target_lang=excluded.target_lang,
                    status=excluded.status,
                    config_json=excluded.config_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    meta.project_id,
                    meta.book_title,
                    meta.source_file_path,
                    meta.source_file_sha256,
                    meta.source_language,
                    meta.target_language,
                    meta.status,
                    json.dumps(project.config),
                ),
            )

    def load_project(self, project_id: str) -> Project | None:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM projects WHERE id = ?;", (project_id,))
            row = cur.fetchone()
            if not row:
                return None

            meta = ProjectMetadata(
                project_id=row["id"],
                book_title=row["title"],
                source_file_path=row["source_file_path"],
                source_language=row["source_lang"],
                target_language=row["target_lang"],
                source_file_sha256=row["source_file_sha256"],
                status=row["status"],
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            config = json.loads(row["config_json"] or "{}")
            return Project(
                metadata=meta,
                project_dir=self.db_path.parent,
                db_path=self.db_path,
                config=config,
            )
        finally:
            cur.close()

    def save_document(self, document: Document, project_id: str) -> None:
        meta_dict = (
            asdict(document.metadata)
            if hasattr(document, "metadata") and isinstance(document.metadata, DocumentMetadata)
            else (document.metadata if isinstance(document.metadata, dict) else {})
        )
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO documents (
                    id, project_id, title, author, source_format, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    source_format=excluded.source_format,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    document.id,
                    project_id,
                    document.title,
                    document.author,
                    document.source_format,
                    json.dumps(meta_dict),
                ),
            )

            # Salva cada capítulo e suas unidades ordenadas
            for chapter in document.chapters:
                self._save_chapter_internal(cur, chapter, document.id)

            # Salva referências bibliográficas
            for ref in document.references:
                cur.execute(
                    """
                    INSERT INTO references_bibliography (
                        id, document_id, citation_key, raw_text, normalized_text,
                        url, reading_order, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        citation_key=excluded.citation_key,
                        raw_text=excluded.raw_text,
                        normalized_text=excluded.normalized_text,
                        url=excluded.url,
                        reading_order=excluded.reading_order,
                        metadata_json=excluded.metadata_json;
                    """,
                    (
                        ref.id,
                        document.id,
                        ref.citation_key,
                        ref.raw_text,
                        ref.normalized_text,
                        ref.url,
                        ref.reading_order,
                        json.dumps(ref.metadata),
                    ),
                )

    def _save_chapter_internal(
        self,
        cur: Any,
        chapter: Chapter,
        document_id: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO chapters (id, document_id, title, order_index, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                order_index=excluded.order_index,
                metadata_json=excluded.metadata_json;
            """,
            (
                chapter.id,
                document_id,
                chapter.title,
                chapter.order,
                json.dumps(chapter.metadata),
            ),
        )

        for sec in chapter.sections:
            cur.execute(
                """
                INSERT INTO sections (
                    id, chapter_id, parent_section_id, title, order_index, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    order_index=excluded.order_index,
                    parent_section_id=excluded.parent_section_id,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    sec.id,
                    sec.chapter_id,
                    sec.parent_section_id,
                    sec.title,
                    getattr(sec, "order_index", getattr(sec, "reading_order", 0)),
                    json.dumps(sec.metadata),
                ),
            )

        for p in chapter.paragraphs:
            spans_json = json.dumps([asdict(s) for s in getattr(p, "spans", [])])
            loc = getattr(p, "source_location", None)
            loc_json = json.dumps(asdict(loc)) if loc else "{}"
            cur.execute(
                """
                INSERT INTO paragraphs (
                    id, chapter_id, section_id, order_index, raw_text,
                    normalized_text, reading_order, spans_json, source_location_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    section_id=excluded.section_id,
                    order_index=excluded.order_index,
                    raw_text=excluded.raw_text,
                    normalized_text=excluded.normalized_text,
                    reading_order=excluded.reading_order,
                    spans_json=excluded.spans_json,
                    source_location_json=excluded.source_location_json,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    p.id,
                    p.chapter_id,
                    p.section_id,
                    getattr(p, "order_index", getattr(p, "reading_order", 0)),
                    p.raw_text,
                    getattr(p, "normalized_text", p.raw_text),
                    getattr(p, "reading_order", 0),
                    spans_json,
                    loc_json,
                    json.dumps(p.metadata),
                ),
            )

        for h in chapter.headings:
            spans_json = json.dumps([asdict(s) for s in h.spans])
            loc_json = json.dumps(asdict(h.source_location)) if h.source_location else "{}"
            cur.execute(
                """
                INSERT INTO headings (
                    id, chapter_id, level, raw_text, normalized_text,
                    reading_order, spans_json, source_location_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    level=excluded.level,
                    raw_text=excluded.raw_text,
                    normalized_text=excluded.normalized_text,
                    reading_order=excluded.reading_order,
                    spans_json=excluded.spans_json,
                    source_location_json=excluded.source_location_json,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    h.id,
                    h.chapter_id,
                    h.level,
                    h.raw_text,
                    h.normalized_text,
                    h.reading_order,
                    spans_json,
                    loc_json,
                    json.dumps(h.metadata),
                ),
            )

        for d in chapter.dialogue_blocks:
            spans_json = json.dumps([asdict(s) for s in d.spans])
            loc_json = json.dumps(asdict(d.source_location)) if d.source_location else "{}"
            cur.execute(
                """
                INSERT INTO dialogues (
                    id, chapter_id, dialogue_marker, speaker_hint, raw_text,
                    normalized_text, reading_order, spans_json, source_location_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    dialogue_marker=excluded.dialogue_marker,
                    speaker_hint=excluded.speaker_hint,
                    raw_text=excluded.raw_text,
                    normalized_text=excluded.normalized_text,
                    reading_order=excluded.reading_order,
                    spans_json=excluded.spans_json,
                    source_location_json=excluded.source_location_json,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    d.id,
                    d.chapter_id,
                    d.dialogue_marker,
                    d.speaker_hint,
                    d.raw_text,
                    d.normalized_text,
                    d.reading_order,
                    spans_json,
                    loc_json,
                    json.dumps(d.metadata),
                ),
            )

        for fn in chapter.footnotes:
            loc_json = json.dumps(asdict(fn.source_location)) if fn.source_location else "{}"
            cur.execute(
                """
                INSERT INTO footnotes (
                    id, chapter_id, marker, raw_text, normalized_text,
                    referencing_unit_id, reading_order, source_location_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    marker=excluded.marker,
                    raw_text=excluded.raw_text,
                    normalized_text=excluded.normalized_text,
                    referencing_unit_id=excluded.referencing_unit_id,
                    reading_order=excluded.reading_order,
                    source_location_json=excluded.source_location_json,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    fn.id,
                    fn.chapter_id,
                    fn.marker,
                    fn.raw_text,
                    fn.normalized_text,
                    fn.referencing_unit_id,
                    fn.reading_order,
                    loc_json,
                    json.dumps(fn.metadata),
                ),
            )

        for img in chapter.image_placeholders:
            loc_json = json.dumps(asdict(img.source_location)) if img.source_location else "{}"
            cur.execute(
                """
                INSERT INTO images (
                    id, chapter_id, caption_raw, caption_normalized, alt_text,
                    relative_path, original_src, reading_order, source_location_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    caption_raw=excluded.caption_raw,
                    caption_normalized=excluded.caption_normalized,
                    alt_text=excluded.alt_text,
                    relative_path=excluded.relative_path,
                    original_src=excluded.original_src,
                    reading_order=excluded.reading_order,
                    source_location_json=excluded.source_location_json,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    img.id,
                    img.chapter_id,
                    img.caption_raw,
                    img.caption_normalized,
                    img.alt_text,
                    img.relative_path,
                    img.original_src,
                    img.reading_order,
                    loc_json,
                    json.dumps(img.metadata),
                ),
            )

        for seg in chapter.segments:
            cur.execute(
                """
                INSERT INTO segments (
                    id, chapter_id, paragraph_id, section_id, order_index,
                    original_text, translated_text, status, original_hash, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    translated_text=excluded.translated_text,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    seg.id,
                    seg.chapter_id,
                    seg.paragraph_id,
                    seg.section_id,
                    seg.sequence_order,
                    seg.original_text,
                    seg.translated_text,
                    seg.status.value,
                    seg.original_hash,
                    json.dumps(seg.metadata),
                ),
            )

    def load_document(self, project_id: str) -> Document | None:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM documents WHERE project_id = ? LIMIT 1;", (project_id,))
            row = cur.fetchone()
            if not row:
                return None

            doc_id = row["id"]
            meta_raw = json.loads(row["metadata_json"] or "{}")
            metadata = DocumentMetadata(
                title=meta_raw.get("title", row["title"]),
                author=meta_raw.get("author", row["author"]),
                language=meta_raw.get("language", "en"),
                publisher=meta_raw.get("publisher", ""),
                publication_date=meta_raw.get("publication_date", ""),
                isbn=meta_raw.get("isbn", ""),
                source_format=meta_raw.get("source_format", row["source_format"]),
                source_file_path=meta_raw.get("source_file_path", ""),
                source_file_sha256=meta_raw.get("source_file_sha256", ""),
                extra=meta_raw.get("extra", {}),
            )

            def parse_spans(raw_json: str | None) -> list[FormattingSpan]:
                return [FormattingSpan(**s) for s in json.loads(raw_json or "[]")]

            def parse_loc(raw_json: str | None) -> SourceLocation | None:
                d = json.loads(raw_json or "{}")
                return SourceLocation(**d) if d else None

            # Carrega capítulos
            cur.execute(
                "SELECT * FROM chapters WHERE document_id = ? ORDER BY order_index ASC;",
                (doc_id,),
            )
            chapters: list[Chapter] = []
            for ch_row in cur.fetchall():
                ch_id = ch_row["id"]
                ch_order = ch_row["order_index"]
                ch_meta = json.loads(ch_row["metadata_json"] or "{}")

                # Seções
                cur.execute(
                    "SELECT * FROM sections WHERE chapter_id = ? ORDER BY order_index ASC;",
                    (ch_id,),
                )
                sections = [
                    Section(
                        id=s["id"],
                        chapter_id=s["chapter_id"],
                        title=s["title"],
                        order_index=s["order_index"],
                        reading_order=s["order_index"],
                        parent_section_id=s["parent_section_id"],
                        metadata=json.loads(s["metadata_json"] or "{}"),
                    )
                    for s in cur.fetchall()
                ]

                # Parágrafos
                cur.execute(
                    "SELECT * FROM paragraphs WHERE chapter_id = ? ORDER BY order_index ASC;",
                    (ch_id,),
                )
                paragraphs = [
                    Paragraph(
                        id=p["id"],
                        chapter_id=p["chapter_id"],
                        reading_order=p["reading_order"] or p["order_index"],
                        raw_text=p["raw_text"],
                        normalized_text=p["normalized_text"] or p["raw_text"],
                        section_id=p["section_id"],
                        spans=parse_spans(p["spans_json"]),
                        source_location=parse_loc(p["source_location_json"]),
                        metadata=json.loads(p["metadata_json"] or "{}"),
                    )
                    for p in cur.fetchall()
                ]

                # Headings
                cur.execute(
                    "SELECT * FROM headings WHERE chapter_id = ? ORDER BY reading_order ASC;",
                    (ch_id,),
                )
                headings = [
                    Heading(
                        id=h["id"],
                        chapter_id=h["chapter_id"],
                        level=h["level"],
                        raw_text=h["raw_text"],
                        normalized_text=h["normalized_text"],
                        reading_order=h["reading_order"],
                        spans=parse_spans(h["spans_json"]),
                        source_location=parse_loc(h["source_location_json"]),
                        metadata=json.loads(h["metadata_json"] or "{}"),
                    )
                    for h in cur.fetchall()
                ]

                # Diálogos
                cur.execute(
                    "SELECT * FROM dialogues WHERE chapter_id = ? ORDER BY reading_order ASC;",
                    (ch_id,),
                )
                dialogues = [
                    DialogueBlock(
                        id=d["id"],
                        chapter_id=d["chapter_id"],
                        dialogue_marker=d["dialogue_marker"],
                        speaker_hint=d["speaker_hint"],
                        raw_text=d["raw_text"],
                        normalized_text=d["normalized_text"],
                        reading_order=d["reading_order"],
                        spans=parse_spans(d["spans_json"]),
                        source_location=parse_loc(d["source_location_json"]),
                        metadata=json.loads(d["metadata_json"] or "{}"),
                    )
                    for d in cur.fetchall()
                ]

                # Footnotes
                cur.execute(
                    "SELECT * FROM footnotes WHERE chapter_id = ? ORDER BY reading_order ASC;",
                    (ch_id,),
                )
                footnotes = [
                    Footnote(
                        id=fn["id"],
                        chapter_id=fn["chapter_id"],
                        marker=fn["marker"],
                        raw_text=fn["raw_text"],
                        normalized_text=fn["normalized_text"],
                        referencing_unit_id=fn["referencing_unit_id"],
                        reading_order=fn["reading_order"],
                        source_location=parse_loc(fn["source_location_json"]),
                        metadata=json.loads(fn["metadata_json"] or "{}"),
                    )
                    for fn in cur.fetchall()
                ]

                # Images
                cur.execute(
                    "SELECT * FROM images WHERE chapter_id = ? ORDER BY reading_order ASC;",
                    (ch_id,),
                )
                images = [
                    ImagePlaceholder(
                        id=img["id"],
                        chapter_id=img["chapter_id"],
                        caption_raw=img["caption_raw"],
                        caption_normalized=img["caption_normalized"],
                        alt_text=img["alt_text"],
                        relative_path=img["relative_path"],
                        original_src=img["original_src"],
                        reading_order=img["reading_order"],
                        source_location=parse_loc(img["source_location_json"]),
                        metadata=json.loads(img["metadata_json"] or "{}"),
                    )
                    for img in cur.fetchall()
                ]

                chapter = Chapter(
                    id=ch_id,
                    title=ch_row["title"],
                    order=ch_order,
                    reading_order=ch_order,
                    headings=headings,
                    paragraphs=paragraphs,
                    dialogue_blocks=dialogues,
                    image_placeholders=images,
                    footnotes=footnotes,
                    sections=sections,
                    segments=self.get_segments_by_chapter(ch_id),
                    metadata=ch_meta,
                )
                chapters.append(chapter)

            # Referências
            cur.execute(
                """
                SELECT * FROM references_bibliography
                WHERE document_id = ? ORDER BY reading_order ASC;
                """,
                (doc_id,),
            )
            references = [
                Reference(
                    id=ref_row["id"],
                    citation_key=ref_row["citation_key"],
                    raw_text=ref_row["raw_text"],
                    normalized_text=ref_row["normalized_text"],
                    url=ref_row["url"],
                    reading_order=ref_row["reading_order"],
                    metadata=json.loads(ref_row["metadata_json"] or "{}"),
                )
                for ref_row in cur.fetchall()
            ]

            return Document(
                id=doc_id,
                metadata=metadata,
                chapters=chapters,
                references=references,
            )
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Estrutura: Capítulos, Seções, Parágrafos e Segmentos
    # -------------------------------------------------------------------------
    def save_chapter(self, chapter: Chapter, document_id: str) -> None:
        with transaction(self.conn) as cur:
            self._save_chapter_internal(cur, chapter, document_id)

    def save_section(self, section: Section) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO sections (
                    id, chapter_id, parent_section_id, title, order_index, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    order_index=excluded.order_index,
                    parent_section_id=excluded.parent_section_id,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    section.id,
                    section.chapter_id,
                    section.parent_section_id,
                    section.title,
                    section.order_index,
                    json.dumps(section.metadata),
                ),
            )

    def save_paragraph(self, paragraph: Paragraph) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO paragraphs (
                    id, chapter_id, section_id, order_index, raw_text, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    section_id=excluded.section_id,
                    order_index=excluded.order_index,
                    raw_text=excluded.raw_text,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    paragraph.id,
                    paragraph.chapter_id,
                    paragraph.section_id,
                    paragraph.order_index,
                    paragraph.raw_text,
                    json.dumps(paragraph.metadata),
                ),
            )

    def save_segment(self, segment: Segment) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO segments (
                    id, chapter_id, paragraph_id, section_id, order_index,
                    original_text, translated_text, status, original_hash, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    translated_text=excluded.translated_text,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    segment.id,
                    segment.chapter_id,
                    segment.paragraph_id,
                    segment.section_id,
                    segment.sequence_order,
                    segment.original_text,
                    segment.translated_text,
                    segment.status.value,
                    segment.original_hash,
                    json.dumps(segment.metadata),
                ),
            )

    def get_segment(self, segment_id: str) -> Segment | None:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM segments WHERE id = ?;", (segment_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_segment(row)
        finally:
            cur.close()

    def get_segments_by_chapter(self, chapter_id: str) -> list[Segment]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM segments WHERE chapter_id = ? ORDER BY order_index ASC;",
                (chapter_id,),
            )
            return [self._row_to_segment(r) for r in cur.fetchall()]
        finally:
            cur.close()

    def get_pending_segments(self, project_id: str) -> list[Segment]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT s.* FROM segments s
                JOIN chapters c ON s.chapter_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE d.project_id = ? AND s.status IN ('pending', 'error')
                ORDER BY c.order_index ASC, s.order_index ASC;
                """,
                (project_id,),
            )
            return [self._row_to_segment(r) for r in cur.fetchall()]
        finally:
            cur.close()

    def count_translated_segments(self, project_id: str) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT COUNT(*) FROM segments s
                JOIN chapters c ON s.chapter_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE d.project_id = ? AND s.status = 'translated';
                """,
                (project_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            cur.close()

    def count_total_segments(self, project_id: str) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT COUNT(*) FROM segments s
                JOIN chapters c ON s.chapter_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE d.project_id = ?;
                """,
                (project_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            cur.close()

    def _row_to_segment(self, row: Any) -> Segment:
        return Segment(
            id=row["id"],
            chapter_id=row["chapter_id"],
            paragraph_id=row["paragraph_id"],
            section_id=row["section_id"],
            sequence_order=row["order_index"],
            original_text=row["original_text"],
            translated_text=row["translated_text"] or "",
            status=SegmentStatus(row["status"]),
            original_hash=row["original_hash"] or "",
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Entidades e Memórias
    # -------------------------------------------------------------------------
    def save_entity(self, entity: Entity) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO entities (
                    id, project_id, name, entity_type, description, occurrences, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    description=excluded.description,
                    occurrences=excluded.occurrences,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    entity.id,
                    entity.project_id,
                    entity.name,
                    entity.entity_type,
                    entity.description,
                    entity.occurrences,
                    json.dumps(entity.metadata),
                ),
            )

    def get_entities(self, project_id: str) -> list[Entity]:
        cur = self.conn.cursor()
        try:
            sql = "SELECT * FROM entities WHERE project_id = ? ORDER BY occurrences DESC;"
            cur.execute(sql, (project_id,))
            return [
                Entity(
                    id=r["id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    entity_type=r["entity_type"],
                    description=r["description"],
                    occurrences=r["occurrences"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                )
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def save_character(self, project_id: str, character: CharacterEntry) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO characters (
                    id, project_id, name, gender, speech_style, linguistic_traits,
                    first_appearance, occurrences, notes, aliases_json, relations_json,
                    treatment, evidences_json, confidence, history_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    gender=excluded.gender,
                    speech_style=excluded.speech_style,
                    linguistic_traits=excluded.linguistic_traits,
                    first_appearance=excluded.first_appearance,
                    occurrences=excluded.occurrences,
                    notes=excluded.notes,
                    aliases_json=excluded.aliases_json,
                    relations_json=excluded.relations_json,
                    treatment=excluded.treatment,
                    evidences_json=excluded.evidences_json,
                    confidence=excluded.confidence,
                    history_json=excluded.history_json;
                """,
                (
                    str(character.id),
                    str(project_id),
                    character.name,
                    character.gender,
                    character.speech_style,
                    ",".join(character.linguistic_traits),
                    character.first_appearance,
                    character.occurrences,
                    character.notes,
                    json.dumps(character.aliases),
                    json.dumps(character.relations),
                    getattr(character, "treatment", ""),
                    json.dumps(getattr(character, "evidences", [])),
                    getattr(character, "confidence", 1.0),
                    json.dumps([h.to_dict() for h in getattr(character, "history", [])]),
                ),
            )

    def get_characters(self, project_id: str) -> list[CharacterEntry]:
        cur = self.conn.cursor()
        try:
            sql = "SELECT * FROM characters WHERE project_id = ? ORDER BY occurrences DESC;"
            cur.execute(sql, (str(project_id),))
            entries = []
            for r in cur.fetchall():
                keys = r.keys()
                hist_raw = json.loads(r["history_json"] or "[]") if "history_json" in keys else []
                evid_raw = (
                    json.loads(r["evidences_json"] or "[]") if "evidences_json" in keys else []
                )
                entries.append(
                    CharacterEntry(
                        id=r["id"],
                        name=r["name"],
                        gender=r["gender"],
                        speech_style=r["speech_style"],
                        linguistic_traits=[t for t in r["linguistic_traits"].split(",") if t],
                        first_appearance=r["first_appearance"],
                        occurrences=r["occurrences"],
                        notes=r["notes"],
                        aliases=json.loads(r["aliases_json"] or "[]"),
                        relations=json.loads(r["relations_json"] or "[]"),
                        treatment=r["treatment"] if "treatment" in keys else "",
                        evidences=evid_raw,
                        confidence=(
                            float(r["confidence"])
                            if "confidence" in keys and r["confidence"] is not None
                            else 1.0
                        ),
                        history=[MemoryRevision.from_dict(h) for h in hist_raw],
                    )
                )
            return entries
        finally:
            cur.close()

    def save_glossary_entry(self, project_id: str, entry: GlossaryEntry) -> None:
        entry_id = f"{project_id}_{entry.source_term.lower()}"
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO glossary (
                    id, project_id, source_term, target_term, entry_type, description,
                    aliases_json, case_sensitive, locked, gender, plural, context,
                    first_occurrence, occurrences, notes, history_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    target_term=excluded.target_term,
                    entry_type=excluded.entry_type,
                    description=excluded.description,
                    aliases_json=excluded.aliases_json,
                    case_sensitive=excluded.case_sensitive,
                    locked=excluded.locked,
                    gender=excluded.gender,
                    plural=excluded.plural,
                    context=excluded.context,
                    occurrences=excluded.occurrences,
                    notes=excluded.notes,
                    history_json=excluded.history_json;
                """,
                (
                    str(entry_id),
                    str(project_id),
                    entry.source_term,
                    entry.target_term,
                    entry.entry_type,
                    entry.description,
                    json.dumps(entry.aliases),
                    1 if entry.case_sensitive else 0,
                    1 if entry.locked else 0,
                    entry.gender,
                    entry.plural,
                    entry.context,
                    entry.first_occurrence,
                    entry.occurrences,
                    entry.notes,
                    json.dumps([h.to_dict() for h in getattr(entry, "history", [])]),
                ),
            )

    def get_glossary(self, project_id: str) -> list[GlossaryEntry]:
        cur = self.conn.cursor()
        try:
            sql = "SELECT * FROM glossary WHERE project_id = ? ORDER BY source_term ASC;"
            cur.execute(sql, (str(project_id),))
            entries = []
            for r in cur.fetchall():
                keys = r.keys()
                hist_raw = json.loads(r["history_json"] or "[]") if "history_json" in keys else []
                entries.append(
                    GlossaryEntry(
                        source_term=r["source_term"],
                        target_term=r["target_term"],
                        entry_type=r["entry_type"],
                        description=r["description"],
                        aliases=json.loads(r["aliases_json"] or "[]"),
                        case_sensitive=bool(r["case_sensitive"]),
                        locked=bool(r["locked"]),
                        gender=r["gender"],
                        plural=r["plural"],
                        context=r["context"],
                        first_occurrence=r["first_occurrence"],
                        occurrences=r["occurrences"],
                        notes=r["notes"],
                        history=[MemoryRevision.from_dict(h) for h in hist_raw],
                    )
                )
            return entries
        finally:
            cur.close()

    def save_tm_entry(self, project_id: str, entry: TranslationMemoryEntry) -> None:
        entry_id = f"tm_{project_id}_{entry.source_term.lower()}"
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO translation_memory (
                    id, project_id, source_term, target_term,
                    entry_type, locked, first_chapter, occurrences,
                    context, origin, status, confidence, history_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    target_term=excluded.target_term,
                    locked=excluded.locked,
                    occurrences=excluded.occurrences,
                    context=excluded.context,
                    origin=excluded.origin,
                    status=excluded.status,
                    confidence=excluded.confidence,
                    history_json=excluded.history_json;
                """,
                (
                    str(entry_id),
                    str(project_id),
                    entry.source_term,
                    entry.target_term,
                    entry.entry_type,
                    1 if entry.locked else 0,
                    entry.first_chapter,
                    entry.occurrences,
                    getattr(entry, "context", ""),
                    getattr(entry, "origin", "user"),
                    getattr(entry, "status", "active"),
                    getattr(entry, "confidence", 1.0),
                    json.dumps([h.to_dict() for h in getattr(entry, "history", [])]),
                ),
            )

    def get_tm(self, project_id: str) -> list[TranslationMemoryEntry]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM translation_memory WHERE project_id = ?;", (str(project_id),)
            )
            entries = []
            for r in cur.fetchall():
                keys = r.keys()
                hist_raw = json.loads(r["history_json"] or "[]") if "history_json" in keys else []
                entries.append(
                    TranslationMemoryEntry(
                        source_term=r["source_term"],
                        target_term=r["target_term"],
                        entry_type=r["entry_type"],
                        locked=bool(r["locked"]),
                        first_chapter=r["first_chapter"],
                        occurrences=r["occurrences"],
                        context=r["context"] if "context" in keys else "",
                        origin=r["origin"] if "origin" in keys else "user",
                        status=r["status"] if "status" in keys else "active",
                        confidence=(
                            float(r["confidence"])
                            if "confidence" in keys and r["confidence"] is not None
                            else 1.0
                        ),
                        history=[MemoryRevision.from_dict(h) for h in hist_raw],
                    )
                )
            return entries
        finally:
            cur.close()

    def record_memory_audit(
        self,
        project_id: str,
        memory_type: str,
        entry_id: str,
        term_or_name: str,
        field_changed: str,
        old_value: Any = "",
        new_value: Any = "",
        changed_by: str = "user",
        reason: str = "",
    ) -> None:
        """Registra uma alteração no log de auditoria de memórias."""

        audit_id = f"audit_{uuid.uuid4().hex[:12]}"
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO memory_audit_log (
                    id, project_id, memory_type, entry_id, term_or_name,
                    field_changed, old_value, new_value, changed_by, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    audit_id,
                    str(project_id),
                    memory_type,
                    str(entry_id),
                    term_or_name,
                    field_changed,
                    str(old_value) if old_value is not None else "",
                    str(new_value) if new_value is not None else "",
                    changed_by,
                    reason,
                ),
            )

    def get_memory_audit_log(
        self,
        project_id: str,
        entry_id: str | None = None,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recupera registros do log relacional de auditoria de memórias."""
        cur = self.conn.cursor()
        try:
            query = "SELECT * FROM memory_audit_log WHERE project_id = ?"
            params: list[Any] = [str(project_id)]
            if entry_id:
                query += " AND entry_id = ?"
                params.append(str(entry_id))
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            query += " ORDER BY created_at DESC;"
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()

    def save_style_bible(self, project_id: str, style_bible: StyleBible) -> None:
        sb_id = f"style_{project_id}"
        rules_serialized = {k: v.to_dict() for k, v in getattr(style_bible, "rules", {}).items()}
        conventions_serialized = getattr(style_bible, "internal_conventions", [])
        narrative_person = getattr(style_bible, "narrative_person", "terceira pessoa")
        predominant_tense = getattr(style_bible, "predominant_tense", "passado")
        formality_level = getattr(style_bible, "formality_level", "formal")
        title_treatment = getattr(style_bible, "title_treatment", "traduzir")

        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO style_bible (
                    id, project_id, narrator, register, dialogue_style, profanity_handling,
                    predominant_treatment, punctuation_standard, metadata_json,
                    narrative_person, predominant_tense, formality_level, title_treatment,
                    internal_conventions_json, rules_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    narrator=excluded.narrator,
                    register=excluded.register,
                    dialogue_style=excluded.dialogue_style,
                    profanity_handling=excluded.profanity_handling,
                    predominant_treatment=excluded.predominant_treatment,
                    punctuation_standard=excluded.punctuation_standard,
                    metadata_json=excluded.metadata_json,
                    narrative_person=excluded.narrative_person,
                    predominant_tense=excluded.predominant_tense,
                    formality_level=excluded.formality_level,
                    title_treatment=excluded.title_treatment,
                    internal_conventions_json=excluded.internal_conventions_json,
                    rules_json=excluded.rules_json;
                """,
                (
                    sb_id,
                    str(project_id),
                    style_bible.narrator,
                    style_bible.register,
                    style_bible.dialogue_style,
                    style_bible.profanity_handling,
                    style_bible.predominant_treatment,
                    style_bible.punctuation_standard,
                    json.dumps(
                        {
                            **style_bible.metadata,
                            "tone": getattr(style_bible, "tone", "literário"),
                            "formality_level": formality_level,
                            "custom_rules": getattr(style_bible, "custom_rules", {}),
                        }
                    ),
                    narrative_person,
                    predominant_tense,
                    formality_level,
                    title_treatment,
                    json.dumps(conventions_serialized),
                    json.dumps(rules_serialized),
                ),
            )

    def get_style_bible(self, project_id: str) -> StyleBible | None:
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM style_bible WHERE project_id = ? LIMIT 1;", (str(project_id),)
            )
            row = cur.fetchone()
            if not row:
                return None
            meta = json.loads(row["metadata_json"] or "{}")

            keys = row.keys()
            rules_dict: dict[str, StyleRule] = {}
            if "rules_json" in keys and row["rules_json"]:
                raw_rules = json.loads(row["rules_json"])
                for rname, rdata in raw_rules.items():
                    if isinstance(rdata, dict):
                        rules_dict[rname] = StyleRule.from_dict(rdata)

            conventions = (
                json.loads(row["internal_conventions_json"])
                if ("internal_conventions_json" in keys and row["internal_conventions_json"])
                else []
            )
            narrative_person = (
                row["narrative_person"]
                if ("narrative_person" in keys and row["narrative_person"])
                else "terceira pessoa"
            )
            predominant_tense = (
                row["predominant_tense"]
                if ("predominant_tense" in keys and row["predominant_tense"])
                else "passado"
            )
            formality_level = (
                row["formality_level"]
                if ("formality_level" in keys and row["formality_level"])
                else meta.get("formality_level", "formal")
            )
            title_treatment = (
                row["title_treatment"]
                if ("title_treatment" in keys and row["title_treatment"])
                else "traduzir"
            )

            return StyleBible(
                narrator=row["narrator"],
                narrative_person=narrative_person,
                predominant_tense=predominant_tense,
                formality_level=formality_level,
                dialogue_style=row["dialogue_style"],
                profanity_handling=row["profanity_handling"],
                treatment_forms=row["predominant_treatment"],
                editorial_punctuation=row["punctuation_standard"],
                title_treatment=title_treatment,
                internal_conventions=conventions,
                register=row["register"],
                predominant_treatment=row["predominant_treatment"],
                punctuation_standard=row["punctuation_standard"],
                project_id=str(project_id),
                tone=meta.get("tone", "literário"),
                custom_rules=meta.get("custom_rules", {}),
                metadata=meta,
                rules=rules_dict,
            )
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Story / Context Memory
    # -------------------------------------------------------------------------

    def save_story_summary(self, project_id: str, summary: ChapterSummary) -> None:
        """Salva ou atualiza um resumo de capítulo ou seção."""
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO story_summaries (
                    id, project_id, unit_type, unit_id, title, summary_text,
                    key_events_json, characters_present_json, order_index, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    summary_text=excluded.summary_text,
                    key_events_json=excluded.key_events_json,
                    characters_present_json=excluded.characters_present_json,
                    order_index=excluded.order_index,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    summary.id,
                    str(project_id),
                    summary.unit_type,
                    summary.unit_id,
                    summary.title,
                    summary.summary_text,
                    json.dumps(summary.key_events),
                    json.dumps(summary.characters_present),
                    summary.order_index,
                    json.dumps(summary.metadata),
                ),
            )

    def get_story_summaries(
        self, project_id: str, unit_type: str | None = None
    ) -> list[ChapterSummary]:
        """Retorna todos os resumos de capítulos/seções do projeto."""
        cur = self.conn.cursor()
        try:
            if unit_type:
                cur.execute(
                    "SELECT * FROM story_summaries WHERE project_id = ? AND unit_type = ? ORDER BY order_index ASC;",
                    (str(project_id), unit_type),
                )
            else:
                cur.execute(
                    "SELECT * FROM story_summaries WHERE project_id = ? ORDER BY order_index ASC;",
                    (str(project_id),),
                )
            rows = cur.fetchall()
            return [
                ChapterSummary(
                    id=r["id"],
                    unit_id=r["unit_id"],
                    summary_text=r["summary_text"],
                    unit_type=r["unit_type"],
                    title=r["title"] or "",
                    key_events=json.loads(r["key_events_json"] or "[]"),
                    characters_present=json.loads(r["characters_present_json"] or "[]"),
                    order_index=r["order_index"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                )
                for r in rows
            ]
        finally:
            cur.close()

    def get_story_summary(self, project_id: str, unit_id: str) -> ChapterSummary | None:
        """Recupera o resumo de uma unidade específica."""
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM story_summaries WHERE project_id = ? AND unit_id = ? LIMIT 1;",
                (str(project_id), str(unit_id)),
            )
            r = cur.fetchone()
            if not r:
                return None
            return ChapterSummary(
                id=r["id"],
                unit_id=r["unit_id"],
                summary_text=r["summary_text"],
                unit_type=r["unit_type"],
                title=r["title"] or "",
                key_events=json.loads(r["key_events_json"] or "[]"),
                characters_present=json.loads(r["characters_present_json"] or "[]"),
                order_index=r["order_index"],
                metadata=json.loads(r["metadata_json"] or "{}"),
            )
        finally:
            cur.close()

    def save_character_state(self, project_id: str, state: CharacterState) -> None:
        """Salva o estado de um personagem em determinado capítulo."""
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO character_states (
                    id, project_id, character_id, chapter_id, alive_status,
                    location, emotional_state, role_or_title, known_facts_json,
                    order_index, metadata_json, evidence, confidence, is_inferred, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    alive_status=excluded.alive_status,
                    location=excluded.location,
                    emotional_state=excluded.emotional_state,
                    role_or_title=excluded.role_or_title,
                    known_facts_json=excluded.known_facts_json,
                    order_index=excluded.order_index,
                    metadata_json=excluded.metadata_json,
                    evidence=excluded.evidence,
                    confidence=excluded.confidence,
                    is_inferred=excluded.is_inferred,
                    source_type=excluded.source_type;
                """,
                (
                    state.id,
                    str(project_id),
                    state.character_id,
                    state.chapter_id,
                    state.alive_status,
                    state.location,
                    state.emotional_state,
                    state.role_or_title,
                    json.dumps(state.known_facts),
                    state.order_index,
                    json.dumps(state.metadata),
                    getattr(state, "evidence", "") or "",
                    float(getattr(state, "confidence", 1.0)),
                    1 if getattr(state, "is_inferred", False) else 0,
                    getattr(state, "source_type", "explicit") or "explicit",
                ),
            )

    def get_character_states(
        self, project_id: str, character_id: str | None = None
    ) -> list[CharacterState]:
        """Recupera a evolução dos estados de personagens."""
        cur = self.conn.cursor()
        try:
            if character_id:
                cur.execute(
                    "SELECT * FROM character_states WHERE project_id = ? AND character_id = ? ORDER BY order_index ASC;",
                    (str(project_id), str(character_id)),
                )
            else:
                cur.execute(
                    "SELECT * FROM character_states WHERE project_id = ? ORDER BY order_index ASC;",
                    (str(project_id),),
                )
            rows = cur.fetchall()
            states = []
            for r in rows:
                keys = r.keys()
                states.append(
                    CharacterState(
                        id=r["id"],
                        character_id=r["character_id"],
                        chapter_id=r["chapter_id"],
                        alive_status=r["alive_status"],
                        location=r["location"] or "",
                        emotional_state=r["emotional_state"] or "",
                        role_or_title=r["role_or_title"] or "",
                        known_facts=json.loads(r["known_facts_json"] or "[]"),
                        order_index=r["order_index"],
                        metadata=json.loads(r["metadata_json"] or "{}"),
                        evidence=r["evidence"] if "evidence" in keys and r["evidence"] else "",
                        confidence=float(r["confidence"])
                        if "confidence" in keys and r["confidence"] is not None
                        else 1.0,
                        is_inferred=bool(r["is_inferred"])
                        if "is_inferred" in keys and r["is_inferred"]
                        else False,
                        source_type=r["source_type"]
                        if "source_type" in keys and r["source_type"]
                        else "explicit",
                    )
                )
            return states
        finally:
            cur.close()

    def save_story_relationship(self, project_id: str, relationship: StoryRelationship) -> None:
        """Salva ou atualiza uma relação interpessoal ativa da história."""
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO story_relationships (
                    id, project_id, source_character_id, target_character_id,
                    relation_type, description, chapter_id, evidence, confidence,
                    is_inferred, source_type, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_character_id=excluded.source_character_id,
                    target_character_id=excluded.target_character_id,
                    relation_type=excluded.relation_type,
                    description=excluded.description,
                    chapter_id=excluded.chapter_id,
                    evidence=excluded.evidence,
                    confidence=excluded.confidence,
                    is_inferred=excluded.is_inferred,
                    source_type=excluded.source_type,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    relationship.id,
                    str(project_id),
                    relationship.source_character_id,
                    relationship.target_character_id,
                    relationship.relation_type,
                    relationship.description,
                    relationship.chapter_id,
                    relationship.evidence,
                    relationship.confidence,
                    1 if relationship.is_inferred else 0,
                    relationship.source_type,
                    json.dumps(relationship.metadata),
                ),
            )

    def get_story_relationships(
        self, project_id: str, character_id: str | None = None
    ) -> list[StoryRelationship]:
        """Recupera relações interpessoais cadastradas no projeto."""
        cur = self.conn.cursor()
        try:
            if character_id:
                cur.execute(
                    """
                    SELECT * FROM story_relationships
                    WHERE project_id = ? AND (source_character_id = ? OR target_character_id = ?)
                    ORDER BY created_at ASC;
                    """,
                    (str(project_id), str(character_id), str(character_id)),
                )
            else:
                cur.execute(
                    "SELECT * FROM story_relationships WHERE project_id = ? ORDER BY created_at ASC;",
                    (str(project_id),),
                )
            rows = cur.fetchall()
            rels = []
            for r in rows:
                keys = r.keys()
                rels.append(
                    StoryRelationship(
                        id=r["id"],
                        source_character_id=r["source_character_id"],
                        target_character_id=r["target_character_id"],
                        relation_type=r["relation_type"],
                        description=r["description"] or "",
                        chapter_id=r["chapter_id"] or "",
                        evidence=r["evidence"] or "",
                        confidence=float(r["confidence"])
                        if "confidence" in keys and r["confidence"] is not None
                        else 1.0,
                        is_inferred=bool(r["is_inferred"])
                        if "is_inferred" in keys and r["is_inferred"]
                        else False,
                        source_type=r["source_type"]
                        if "source_type" in keys and r["source_type"]
                        else "explicit",
                        metadata=json.loads(r["metadata_json"] or "{}"),
                    )
                )
            return rels
        finally:
            cur.close()

    def save_story_event(self, project_id: str, event: StoryEvent) -> None:
        """Salva um evento na linha do tempo da história."""
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO story_events (
                    id, project_id, chapter_id, unit_id, description,
                    characters_involved_json, significance, narrative_order,
                    chronological_order, evidence, metadata_json,
                    confidence, is_inferred, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    description=excluded.description,
                    characters_involved_json=excluded.characters_involved_json,
                    significance=excluded.significance,
                    narrative_order=excluded.narrative_order,
                    chronological_order=excluded.chronological_order,
                    evidence=excluded.evidence,
                    metadata_json=excluded.metadata_json,
                    confidence=excluded.confidence,
                    is_inferred=excluded.is_inferred,
                    source_type=excluded.source_type;
                """,
                (
                    event.id,
                    str(project_id),
                    event.chapter_id,
                    event.unit_id,
                    event.description,
                    json.dumps(event.characters_involved),
                    event.significance,
                    event.narrative_order,
                    event.chronological_order,
                    event.evidence,
                    json.dumps(event.metadata),
                    float(getattr(event, "confidence", 1.0)),
                    1 if getattr(event, "is_inferred", False) else 0,
                    getattr(event, "source_type", "explicit") or "explicit",
                ),
            )

    def get_story_events(
        self, project_id: str, chapter_id: str | None = None, chronological: bool = False
    ) -> list[StoryEvent]:
        """Recupera eventos do projeto com ordenação narrativa ou cronológica."""
        cur = self.conn.cursor()
        try:
            order_by = (
                "ORDER BY chronological_order ASC, narrative_order ASC"
                if chronological
                else "ORDER BY narrative_order ASC, chronological_order ASC"
            )
            if chapter_id:
                cur.execute(
                    f"SELECT * FROM story_events WHERE project_id = ? AND chapter_id = ? {order_by};",
                    (str(project_id), str(chapter_id)),
                )
            else:
                cur.execute(
                    f"SELECT * FROM story_events WHERE project_id = ? {order_by};",
                    (str(project_id),),
                )
            rows = cur.fetchall()
            events = []
            for r in rows:
                keys = r.keys()
                events.append(
                    StoryEvent(
                        id=r["id"],
                        chapter_id=r["chapter_id"],
                        description=r["description"],
                        unit_id=r["unit_id"] or "",
                        characters_involved=json.loads(r["characters_involved_json"] or "[]"),
                        significance=r["significance"],
                        narrative_order=r["narrative_order"],
                        chronological_order=r["chronological_order"],
                        evidence=r["evidence"] or "",
                        metadata=json.loads(r["metadata_json"] or "{}"),
                        confidence=float(r["confidence"])
                        if "confidence" in keys and r["confidence"] is not None
                        else 1.0,
                        is_inferred=bool(r["is_inferred"])
                        if "is_inferred" in keys and r["is_inferred"]
                        else False,
                        source_type=r["source_type"]
                        if "source_type" in keys and r["source_type"]
                        else "explicit",
                    )
                )
            return events
        finally:
            cur.close()

    def save_story_fact(self, project_id: str, fact: PersistentFact) -> None:
        """Salva um fato persistente (lore, regra) da obra."""
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO story_facts (
                    id, project_id, category, statement, subject_entity_ids_json,
                    evidence, confidence, locked, occurrences_json, metadata_json,
                    is_inferred, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    category=excluded.category,
                    statement=excluded.statement,
                    subject_entity_ids_json=excluded.subject_entity_ids_json,
                    evidence=excluded.evidence,
                    confidence=excluded.confidence,
                    locked=excluded.locked,
                    occurrences_json=excluded.occurrences_json,
                    metadata_json=excluded.metadata_json,
                    is_inferred=excluded.is_inferred,
                    source_type=excluded.source_type;
                """,
                (
                    fact.id,
                    str(project_id),
                    fact.category,
                    fact.statement,
                    json.dumps(fact.subject_entity_ids),
                    fact.evidence,
                    fact.confidence,
                    1 if fact.locked else 0,
                    json.dumps(fact.occurrences),
                    json.dumps(fact.metadata),
                    1 if getattr(fact, "is_inferred", False) else 0,
                    getattr(fact, "source_type", "explicit") or "explicit",
                ),
            )

    def get_story_facts(
        self,
        project_id: str,
        category: str | None = None,
        locked_only: bool = False,
    ) -> list[PersistentFact]:
        """Recupera fatos persistentes do projeto."""
        cur = self.conn.cursor()
        try:
            conditions = ["project_id = ?"]
            params: list[Any] = [str(project_id)]
            if category:
                conditions.append("category = ?")
                params.append(category)
            if locked_only:
                conditions.append("locked = 1")
            sql = f"SELECT * FROM story_facts WHERE {' AND '.join(conditions)} ORDER BY created_at ASC;"
            cur.execute(sql, params)
            rows = cur.fetchall()
            facts = []
            for r in rows:
                keys = r.keys()
                facts.append(
                    PersistentFact(
                        id=r["id"],
                        statement=r["statement"],
                        category=r["category"],
                        subject_entity_ids=json.loads(r["subject_entity_ids_json"] or "[]"),
                        evidence=r["evidence"] or "",
                        confidence=float(r["confidence"]),
                        locked=bool(r["locked"]),
                        occurrences=json.loads(r["occurrences_json"] or "[]"),
                        metadata=json.loads(r["metadata_json"] or "{}"),
                        is_inferred=bool(r["is_inferred"])
                        if "is_inferred" in keys and r["is_inferred"]
                        else False,
                        source_type=r["source_type"]
                        if "source_type" in keys and r["source_type"]
                        else "explicit",
                    )
                )
            return facts
        finally:
            cur.close()

    def save_story_cross_reference(self, project_id: str, cross_ref: StoryCrossReference) -> None:
        """Salva uma referência cruzada entre trechos da obra."""
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO story_cross_references (
                    id, project_id, source_unit_id, target_unit_id, ref_type,
                    description, evidence, metadata_json, confidence, is_inferred, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    ref_type=excluded.ref_type,
                    description=excluded.description,
                    evidence=excluded.evidence,
                    metadata_json=excluded.metadata_json,
                    confidence=excluded.confidence,
                    is_inferred=excluded.is_inferred,
                    source_type=excluded.source_type;
                """,
                (
                    cross_ref.id,
                    str(project_id),
                    cross_ref.source_unit_id,
                    cross_ref.target_unit_id,
                    cross_ref.ref_type,
                    cross_ref.description,
                    cross_ref.evidence,
                    json.dumps(cross_ref.metadata),
                    float(getattr(cross_ref, "confidence", 1.0)),
                    1 if getattr(cross_ref, "is_inferred", False) else 0,
                    getattr(cross_ref, "source_type", "explicit") or "explicit",
                ),
            )

    def get_story_cross_references(
        self, project_id: str, unit_id: str | None = None
    ) -> list[StoryCrossReference]:
        """Recupera referências cruzadas vinculadas a uma unidade."""
        cur = self.conn.cursor()
        try:
            if unit_id:
                cur.execute(
                    """
                    SELECT * FROM story_cross_references
                    WHERE project_id = ? AND (source_unit_id = ? OR target_unit_id = ?)
                    ORDER BY created_at ASC;
                    """,
                    (str(project_id), str(unit_id), str(unit_id)),
                )
            else:
                cur.execute(
                    "SELECT * FROM story_cross_references WHERE project_id = ? ORDER BY created_at ASC;",
                    (str(project_id),),
                )
            rows = cur.fetchall()
            refs = []
            for r in rows:
                keys = r.keys()
                refs.append(
                    StoryCrossReference(
                        id=r["id"],
                        source_unit_id=r["source_unit_id"],
                        target_unit_id=r["target_unit_id"],
                        description=r["description"],
                        ref_type=r["ref_type"],
                        evidence=r["evidence"] or "",
                        metadata=json.loads(r["metadata_json"] or "{}"),
                        confidence=float(r["confidence"])
                        if "confidence" in keys and r["confidence"] is not None
                        else 1.0,
                        is_inferred=bool(r["is_inferred"])
                        if "is_inferred" in keys and r["is_inferred"]
                        else False,
                        source_type=r["source_type"]
                        if "source_type" in keys and r["source_type"]
                        else "explicit",
                    )
                )
            return refs
        finally:
            cur.close()

    def save_story_memory(self, project_id: str, story_memory: StoryMemory) -> None:
        """Persiste todos os elementos contidos na StoryMemory no banco de dados, incluindo relacionamentos."""
        for summary in story_memory.get_all_summaries():
            self.save_story_summary(project_id, summary)

        for char_id in list(story_memory._character_states.keys()):
            for state in story_memory._character_states[char_id]:
                self.save_character_state(project_id, state)

        for rel in story_memory.get_relationships():
            self.save_story_relationship(project_id, rel)

        for event in story_memory.get_events():
            self.save_story_event(project_id, event)

        for fact in story_memory.get_facts():
            self.save_story_fact(project_id, fact)

        for cross_ref in list(story_memory._cross_references.values()):
            self.save_story_cross_reference(project_id, cross_ref)

    def get_story_memory(self, project_id: str) -> StoryMemory:
        """Carrega e reconstrói a StoryMemory completa do projeto a partir do banco de dados."""
        sm = StoryMemory(project_id=str(project_id))
        for summary in self.get_story_summaries(project_id):
            sm._summaries[summary.unit_id] = summary
            ch_id = summary.metadata.get("chapter_id")
            if ch_id and ch_id not in sm._summaries:
                sm._summaries[ch_id] = summary

        for state in self.get_character_states(project_id):
            if state.character_id not in sm._character_states:
                sm._character_states[state.character_id] = []
            sm._character_states[state.character_id].append(state)

        for rel in self.get_story_relationships(project_id):
            sm._relationships.append(rel)

        for event in self.get_story_events(project_id):
            sm._events[event.id] = event

        for fact in self.get_story_facts(project_id):
            sm._facts[fact.id] = fact

        for cross_ref in self.get_story_cross_references(project_id):
            sm._cross_references[cross_ref.id] = cross_ref

        return sm

    # -------------------------------------------------------------------------
    # Contexto e Traduções
    # -------------------------------------------------------------------------
    def save_context(self, context: TranslationContext) -> None:
        meta = dict(context.extra_metadata)
        meta["relevant_relationships"] = [
            r.to_dict() if hasattr(r, "to_dict") else r.__dict__
            for r in context.relevant_relationships
        ]
        meta["story_facts"] = [
            f.to_dict() if hasattr(f, "to_dict") else f.__dict__ for f in context.story_facts
        ]
        meta["semantic_snippets"] = [s.to_dict() for s in context.semantic_snippets]
        meta["scores"] = [s.to_dict() for s in context.scores]
        meta["strategy_used"] = context.strategy_used
        meta["reproducibility_hash"] = context.reproducibility_hash
        meta["future_leakage_prevented"] = context.future_leakage_prevented
        if context.metrics:
            meta["metrics"] = context.metrics.to_dict()

        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO contexts (
                    segment_id, preceding_text_json, succeeding_text_json,
                    chapter_summary, active_characters_json, relevant_glossary_json,
                    established_translations_json, extra_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(segment_id) DO UPDATE SET
                    preceding_text_json=excluded.preceding_text_json,
                    succeeding_text_json=excluded.succeeding_text_json,
                    chapter_summary=excluded.chapter_summary,
                    active_characters_json=excluded.active_characters_json,
                    relevant_glossary_json=excluded.relevant_glossary_json,
                    established_translations_json=excluded.established_translations_json,
                    extra_metadata_json=excluded.extra_metadata_json;
                """,
                (
                    context.segment_id,
                    json.dumps(context.preceding_text),
                    json.dumps(context.succeeding_text),
                    context.chapter_summary,
                    json.dumps([c.__dict__ for c in context.active_characters]),
                    json.dumps([g.__dict__ for g in context.relevant_glossary]),
                    json.dumps([t.__dict__ for t in context.established_translations]),
                    json.dumps(meta),
                ),
            )

    def get_context(self, segment_id: str) -> TranslationContext | None:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM contexts WHERE segment_id = ?;", (segment_id,))
            row = cur.fetchone()
            if not row:
                return None

            extra_meta = json.loads(row["extra_metadata_json"] or "{}")
            raw_chars = json.loads(row["active_characters_json"] or "[]")
            raw_gloss = json.loads(row["relevant_glossary_json"] or "[]")
            raw_tm = json.loads(row["established_translations_json"] or "[]")

            chars = [
                CharacterEntry(**c)
                if isinstance(c, dict) and not hasattr(CharacterEntry, "from_dict")
                else CharacterEntry.from_dict(c)
                if hasattr(CharacterEntry, "from_dict") and isinstance(c, dict)
                else c
                for c in raw_chars
            ]
            gloss = [
                GlossaryEntry.from_dict(g)
                if hasattr(GlossaryEntry, "from_dict") and isinstance(g, dict)
                else GlossaryEntry(**g)
                if isinstance(g, dict)
                else g
                for g in raw_gloss
            ]
            tm = [
                TranslationMemoryEntry.from_dict(t)
                if hasattr(TranslationMemoryEntry, "from_dict") and isinstance(t, dict)
                else TranslationMemoryEntry(**t)
                if isinstance(t, dict)
                else t
                for t in raw_tm
            ]

            raw_rels = extra_meta.pop("relevant_relationships", [])
            raw_facts = extra_meta.pop("story_facts", [])
            raw_snips = extra_meta.pop("semantic_snippets", [])
            raw_scores = extra_meta.pop("scores", [])
            strat = extra_meta.pop("strategy_used", "balanced")
            r_hash = extra_meta.pop("reproducibility_hash", "")
            f_prev = extra_meta.pop("future_leakage_prevented", True)
            metrics_d = extra_meta.pop("metrics", None)

            rels = [StoryRelationship.from_dict(r) if isinstance(r, dict) else r for r in raw_rels]
            facts = [PersistentFact.from_dict(f) if isinstance(f, dict) else f for f in raw_facts]
            snips = [SemanticSnippet.from_dict(s) if isinstance(s, dict) else s for s in raw_snips]
            scores = [
                ContextItemScore.from_dict(s) if isinstance(s, dict) else s for s in raw_scores
            ]
            metrics_obj = ContextMetrics(**metrics_d) if isinstance(metrics_d, dict) else None

            return TranslationContext(
                segment_id=row["segment_id"],
                preceding_text=json.loads(row["preceding_text_json"] or "[]"),
                succeeding_text=json.loads(row["succeeding_text_json"] or "[]"),
                chapter_summary=row["chapter_summary"],
                active_characters=chars,
                relevant_glossary=gloss,
                established_translations=tm,
                relevant_relationships=rels,
                story_facts=facts,
                semantic_snippets=snips,
                scores=scores,
                strategy_used=strat,
                reproducibility_hash=r_hash,
                future_leakage_prevented=f_prev,
                metrics=metrics_obj,
                extra_metadata=extra_meta,
            )
        finally:
            cur.close()

    def save_translation_draft(self, draft: TranslationDraft) -> None:
        with transaction(self.conn) as cur:
            for idx, cand in enumerate(draft.candidates, start=1):
                cand_id = f"trans_{draft.segment_id}_{idx}"
                is_selected = 1 if cand.text == draft.selected_text else 0
                merged_meta = {**draft.metadata, **cand.metadata}
                cur.execute(
                    """
                    INSERT INTO translations (
                        id, segment_id, translated_text, engine_name,
                        candidate_rank, score, is_selected, execution_time_ms, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        translated_text=excluded.translated_text,
                        score=excluded.score,
                        is_selected=excluded.is_selected,
                        metadata_json=excluded.metadata_json;
                    """,
                    (
                        cand_id,
                        draft.segment_id,
                        cand.text,
                        draft.engine_name,
                        cand.rank,
                        cand.score,
                        is_selected,
                        draft.execution_time_ms,
                        json.dumps(merged_meta),
                    ),
                )

    def get_translations(self, segment_id: str) -> list[dict[str, Any]]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT * FROM translations
                WHERE segment_id = ?
                ORDER BY candidate_rank ASC;
                """,
                (segment_id,),
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                meta = json.loads(r["metadata_json"] or "{}")
                results.append(
                    {
                        "id": r["id"],
                        "segment_id": r["segment_id"],
                        "translated_text": r["translated_text"],
                        "engine_name": r["engine_name"],
                        "candidate_rank": r["candidate_rank"],
                        "score": r["score"],
                        "is_selected": bool(r["is_selected"]),
                        "execution_time_ms": r["execution_time_ms"],
                        "metadata": meta,
                        "created_at": str(r["created_at"]),
                    }
                )
            return results
        finally:
            cur.close()

    def get_selected_translation(self, segment_id: str) -> dict[str, Any] | None:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT * FROM translations
                WHERE segment_id = ? AND is_selected = 1
                LIMIT 1;
                """,
                (segment_id,),
            )
            r = cur.fetchone()
            if not r:
                return None
            meta = json.loads(r["metadata_json"] or "{}")
            return {
                "id": r["id"],
                "segment_id": r["segment_id"],
                "translated_text": r["translated_text"],
                "engine_name": r["engine_name"],
                "candidate_rank": r["candidate_rank"],
                "score": r["score"],
                "is_selected": True,
                "execution_time_ms": r["execution_time_ms"],
                "metadata": meta,
                "created_at": str(r["created_at"]),
            }
        finally:
            cur.close()

    def save_translation_cache(
        self,
        cache_key: str,
        project_id: str,
        segment_id: str,
        source_text: str,
        target_text: str,
        model_name: str,
        runtime: str,
        parameters: dict[str, Any],
        context_hash: str,
        glossary_terms: list[str] | None = None,
    ) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO translation_cache (
                    cache_key, project_id, segment_id, source_text, target_text,
                    model_name, runtime, parameters_json, context_hash, glossary_terms_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    target_text=excluded.target_text,
                    parameters_json=excluded.parameters_json,
                    context_hash=excluded.context_hash,
                    glossary_terms_json=excluded.glossary_terms_json;
                """,
                (
                    cache_key,
                    project_id,
                    segment_id,
                    source_text,
                    target_text,
                    model_name,
                    runtime,
                    json.dumps(parameters),
                    context_hash,
                    json.dumps(glossary_terms or []),
                ),
            )

    def get_translation_cache(self, cache_key: str) -> dict[str, Any] | None:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT * FROM translation_cache
                WHERE cache_key = ?
                LIMIT 1;
                """,
                (cache_key,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return {
                "cache_key": r["cache_key"],
                "project_id": r["project_id"],
                "segment_id": r["segment_id"],
                "source_text": r["source_text"],
                "target_text": r["target_text"],
                "model_name": r["model_name"],
                "runtime": r["runtime"],
                "parameters": json.loads(r["parameters_json"] or "{}"),
                "context_hash": r["context_hash"],
                "glossary_terms": json.loads(r["glossary_terms_json"] or "[]"),
                "created_at": str(r["created_at"]),
            }
        finally:
            cur.close()

    def invalidate_cache_by_glossary_term(self, project_id: str, glossary_term: str) -> list[str]:
        """Invalida o cache e reverte para pending apenas os segmentos afetados pelo termo de glossário."""
        pattern = re.compile(rf"\b{re.escape(glossary_term)}\b", re.IGNORECASE)
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT s.id, s.original_text
                FROM segments s
                JOIN chapters c ON s.chapter_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE d.project_id = ?;
                """,
                (project_id,),
            )
            affected_ids = [
                row["id"] for row in cur.fetchall() if pattern.search(row["original_text"])
            ]
        finally:
            cur.close()

        if not affected_ids:
            return []

        with transaction(self.conn) as cur:
            placeholders = ",".join("?" for _ in affected_ids)
            cur.execute(
                f"DELETE FROM translation_cache WHERE segment_id IN ({placeholders});",
                affected_ids,
            )
            cur.execute(
                f"""
                UPDATE segments
                SET status = 'pending', translated_text = '', updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders});
                """,
                affected_ids,
            )
        return affected_ids

    def save_revision(
        self,
        segment_id: str,
        old_text: str,
        new_text: str,
        revised_by: str,
        reason: str = "",
    ) -> None:
        rev_id = f"rev_{segment_id}_{hash(old_text + new_text) & 0xFFFFFFFF:08x}"
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO revisions (id, segment_id, old_text, new_text, revised_by, reason)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (rev_id, segment_id, old_text, new_text, revised_by, reason),
            )

    # -------------------------------------------------------------------------
    # QA e Validação
    # -------------------------------------------------------------------------
    def save_qa_report(self, report: QAReport) -> None:
        with transaction(self.conn) as cur:
            cur.execute("DELETE FROM qa_issues WHERE segment_id = ?;", (report.segment_id,))
            for idx, issue in enumerate(report.issues, start=1):
                issue_id = f"qa_{report.segment_id}_{idx}"
                cur.execute(
                    """
                    INSERT INTO qa_issues (
                        id, segment_id, check_type, severity, description,
                        original_snippet, translated_snippet, suggested_fix
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        issue_id,
                        report.segment_id,
                        issue.check_type,
                        issue.severity.value,
                        issue.description,
                        issue.original_snippet,
                        issue.translated_snippet,
                        issue.suggested_fix,
                    ),
                )

    def get_qa_issues(self, segment_id: str) -> list[QAIssue]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT check_type, severity, description, original_snippet,
                       translated_snippet, suggested_fix
                FROM qa_issues
                WHERE segment_id = ?
                ORDER BY rowid ASC;
                """,
                (segment_id,),
            )
            rows = cur.fetchall()
            return [
                QAIssue(
                    check_type=row["check_type"],
                    severity=IssueSeverity(row["severity"]),
                    description=row["description"],
                    original_snippet=row["original_snippet"] or "",
                    translated_snippet=row["translated_snippet"] or "",
                    suggested_fix=row["suggested_fix"],
                )
                for row in rows
            ]
        finally:
            cur.close()

    def save_qa_fix_audit(self, audit: QAFixAuditRecord) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO qa_fix_audits (
                    id, segment_id, check_type, old_text, new_text,
                    rule_applied, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    audit.id,
                    audit.segment_id,
                    audit.check_type,
                    audit.old_text,
                    audit.new_text,
                    audit.rule_applied,
                    json.dumps(audit.metadata),
                ),
            )

    def get_qa_fix_audits(self, segment_id: str) -> list[QAFixAuditRecord]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, segment_id, check_type, old_text, new_text,
                       rule_applied, metadata_json, created_at
                FROM qa_fix_audits
                WHERE segment_id = ?
                ORDER BY created_at ASC, rowid ASC;
                """,
                (segment_id,),
            )
            rows = cur.fetchall()
            return [
                QAFixAuditRecord(
                    id=row["id"],
                    segment_id=row["segment_id"],
                    check_type=row["check_type"],
                    old_text=row["old_text"],
                    new_text=row["new_text"],
                    rule_applied=row["rule_applied"],
                    timestamp=str(row["created_at"]),
                    metadata=json.loads(row["metadata_json"] or "{}"),
                )
                for row in rows
            ]
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Checkpoints e Eventos
    # -------------------------------------------------------------------------
    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO checkpoints (
                    id, project_id, last_chapter_id, last_segment_id,
                    completed_segments, total_segments, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_chapter_id=excluded.last_chapter_id,
                    last_segment_id=excluded.last_segment_id,
                    completed_segments=excluded.completed_segments,
                    total_segments=excluded.total_segments,
                    status=excluded.status;
                """,
                (
                    checkpoint.id,
                    checkpoint.project_id,
                    checkpoint.last_completed_chapter_id,
                    checkpoint.last_completed_segment_id,
                    checkpoint.completed_segments,
                    checkpoint.total_segments,
                    checkpoint.status,
                ),
            )

    def get_latest_checkpoint(self, project_id: str) -> Checkpoint | None:
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT * FROM checkpoints
                WHERE project_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1;
                """,
                (project_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return Checkpoint(
                id=row["id"],
                project_id=row["project_id"],
                last_completed_chapter_id=row["last_chapter_id"],
                last_completed_segment_id=row["last_segment_id"],
                completed_segments=row["completed_segments"],
                total_segments=row["total_segments"],
                status=row["status"],
                created_at=str(row["created_at"]),
            )
        finally:
            cur.close()

    def log_event(self, event: EventLog) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO project_events (id, project_id, level, phase, message, details_json)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    event.id,
                    event.project_id,
                    event.level,
                    event.phase,
                    event.message,
                    json.dumps(event.details),
                ),
            )

    def close(self) -> None:
        """Flushes WAL and closes database connection."""
        try:
            wal_checkpoint(self.conn)
            self.conn.close()
        except Exception as exc:
            raise DatabaseError(f"Erro ao fechar conexão com banco: {exc}") from exc
