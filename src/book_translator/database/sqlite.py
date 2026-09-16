"""Implementação concreta de DatabaseInterface em SQLite com suporte transacional completo."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from book_translator.context.base import TranslationContext
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
    CharacterEntry,
    GlossaryEntry,
    StyleBible,
    TranslationMemoryEntry,
)
from book_translator.qa.base import QAReport
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
            loc_json = (
                json.dumps(asdict(h.source_location)) if h.source_location else "{}"
            )
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
            loc_json = (
                json.dumps(asdict(d.source_location)) if d.source_location else "{}"
            )
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
            loc_json = (
                json.dumps(asdict(fn.source_location)) if fn.source_location else "{}"
            )
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
            loc_json = (
                json.dumps(asdict(img.source_location)) if img.source_location else "{}"
            )
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
                    first_appearance, occurrences, notes, aliases_json, relations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    gender=excluded.gender,
                    speech_style=excluded.speech_style,
                    linguistic_traits=excluded.linguistic_traits,
                    first_appearance=excluded.first_appearance,
                    occurrences=excluded.occurrences,
                    notes=excluded.notes,
                    aliases_json=excluded.aliases_json,
                    relations_json=excluded.relations_json;
                """,
                (
                    character.id,
                    project_id,
                    character.name,
                    character.gender,
                    character.speech_style,
                    ",".join(character.linguistic_traits),
                    character.first_appearance,
                    character.occurrences,
                    character.notes,
                    json.dumps(character.aliases),
                    json.dumps(character.relations),
                ),
            )

    def get_characters(self, project_id: str) -> list[CharacterEntry]:
        cur = self.conn.cursor()
        try:
            sql = "SELECT * FROM characters WHERE project_id = ? ORDER BY occurrences DESC;"
            cur.execute(sql, (project_id,))
            return [
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
                )
                for r in cur.fetchall()
            ]
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
                    first_occurrence, occurrences, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    notes=excluded.notes;
                """,
                (
                    entry_id,
                    project_id,
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
                ),
            )

    def get_glossary(self, project_id: str) -> list[GlossaryEntry]:
        cur = self.conn.cursor()
        try:
            sql = "SELECT * FROM glossary WHERE project_id = ? ORDER BY source_term ASC;"
            cur.execute(sql, (project_id,))
            return [
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
                )
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def save_tm_entry(self, project_id: str, entry: TranslationMemoryEntry) -> None:
        entry_id = f"tm_{project_id}_{entry.source_term.lower()}"
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO translation_memory (
                    id, project_id, source_term, target_term,
                    entry_type, locked, first_chapter, occurrences
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    target_term=excluded.target_term,
                    locked=excluded.locked,
                    occurrences=excluded.occurrences;
                """,
                (
                    entry_id,
                    project_id,
                    entry.source_term,
                    entry.target_term,
                    entry.entry_type,
                    1 if entry.locked else 0,
                    entry.first_chapter,
                    entry.occurrences,
                ),
            )

    def get_tm(self, project_id: str) -> list[TranslationMemoryEntry]:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM translation_memory WHERE project_id = ?;", (project_id,))
            return [
                TranslationMemoryEntry(
                    source_term=r["source_term"],
                    target_term=r["target_term"],
                    entry_type=r["entry_type"],
                    locked=bool(r["locked"]),
                    first_chapter=r["first_chapter"],
                    occurrences=r["occurrences"],
                )
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def save_style_bible(self, project_id: str, style_bible: StyleBible) -> None:
        sb_id = f"style_{project_id}"
        with transaction(self.conn) as cur:
            cur.execute(
                """
                INSERT INTO style_bible (
                    id, project_id, narrator, register, dialogue_style, profanity_handling,
                    predominant_treatment, punctuation_standard, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    narrator=excluded.narrator,
                    register=excluded.register,
                    dialogue_style=excluded.dialogue_style,
                    profanity_handling=excluded.profanity_handling,
                    predominant_treatment=excluded.predominant_treatment,
                    punctuation_standard=excluded.punctuation_standard,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    sb_id,
                    project_id,
                    style_bible.narrator,
                    style_bible.register,
                    style_bible.dialogue_style,
                    style_bible.profanity_handling,
                    style_bible.predominant_treatment,
                    style_bible.punctuation_standard,
                    json.dumps(style_bible.metadata),
                ),
            )

    def get_style_bible(self, project_id: str) -> StyleBible | None:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM style_bible WHERE project_id = ? LIMIT 1;", (project_id,))
            row = cur.fetchone()
            if not row:
                return None
            return StyleBible(
                narrator=row["narrator"],
                register=row["register"],
                dialogue_style=row["dialogue_style"],
                profanity_handling=row["profanity_handling"],
                predominant_treatment=row["predominant_treatment"],
                punctuation_standard=row["punctuation_standard"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Contexto e Traduções
    # -------------------------------------------------------------------------
    def save_context(self, context: TranslationContext) -> None:
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
                    json.dumps(context.extra_metadata),
                ),
            )

    def get_context(self, segment_id: str) -> TranslationContext | None:
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT * FROM contexts WHERE segment_id = ?;", (segment_id,))
            row = cur.fetchone()
            if not row:
                return None
            return TranslationContext(
                segment_id=row["segment_id"],
                preceding_text=json.loads(row["preceding_text_json"] or "[]"),
                succeeding_text=json.loads(row["succeeding_text_json"] or "[]"),
                chapter_summary=row["chapter_summary"],
                extra_metadata=json.loads(row["extra_metadata_json"] or "{}"),
            )
        finally:
            cur.close()

    def save_translation_draft(self, draft: TranslationDraft) -> None:
        with transaction(self.conn) as cur:
            for idx, cand in enumerate(draft.candidates, start=1):
                cand_id = f"trans_{draft.segment_id}_{idx}"
                is_selected = 1 if cand.text == draft.selected_text else 0
                cur.execute(
                    """
                    INSERT INTO translations (
                        id, segment_id, translated_text, engine_name,
                        candidate_rank, score, is_selected, execution_time_ms, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        translated_text=excluded.translated_text,
                        score=excluded.score,
                        is_selected=excluded.is_selected;
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
                        json.dumps(cand.metadata),
                    ),
                )

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
