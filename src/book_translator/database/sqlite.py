"""Implementação concreta de DatabaseInterface em SQLite com suporte transacional completo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from book_translator.context.base import TranslationContext
from book_translator.core.models import (
    Chapter,
    Checkpoint,
    Document,
    Entity,
    EventLog,
    Paragraph,
    Project,
    ProjectMetadata,
    Section,
    Segment,
    SegmentStatus,
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
                    json.dumps(document.metadata),
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
            doc = Document(
                id=doc_id,
                title=row["title"],
                author=row["author"],
                source_format=row["source_format"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

            # Carrega capítulos
            cur.execute(
                "SELECT * FROM chapters WHERE document_id = ? ORDER BY order_index ASC;",
                (doc_id,),
            )
            for ch_row in cur.fetchall():
                ch_id = ch_row["id"]
                chapter = Chapter(
                    id=ch_id,
                    title=ch_row["title"],
                    order=ch_row["order_index"],
                    metadata=json.loads(ch_row["metadata_json"] or "{}"),
                )
                chapter.segments = self.get_segments_by_chapter(ch_id)
                doc.chapters.append(chapter)

            return doc
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Estrutura: Capítulos, Seções, Parágrafos e Segmentos
    # -------------------------------------------------------------------------
    def save_chapter(self, chapter: Chapter, document_id: str) -> None:
        with transaction(self.conn) as cur:
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
