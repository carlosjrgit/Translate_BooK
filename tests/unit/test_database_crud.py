"""Testes completos das operações CRUD e integridade referencial do SQLiteDatabase."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.core.models import (
    Chapter,
    Checkpoint,
    DialogueBlock,
    Document,
    Entity,
    EventLog,
    Footnote,
    FormattingSpan,
    Heading,
    ImagePlaceholder,
    Paragraph,
    Project,
    ProjectMetadata,
    Section,
    Segment,
    SegmentStatus,
    SourceLocation,
)
from book_translator.database.connection import transaction
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.errors import DatabaseError
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    StyleBible,
    TranslationMemoryEntry,
)
from book_translator.qa.base import IssueSeverity, QAIssue, QAReport
from book_translator.translation.base import TranslationCandidate, TranslationDraft


@pytest.fixture
def db(tmp_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "crud_test.db")
    database.initialize()
    yield database
    database.close()


def test_project_crud(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Testa inserção e recuperação de projetos."""
    meta = ProjectMetadata(
        project_id="test_book",
        book_title="Test Book",
        source_file_path=str(tmp_path / "source.txt"),
        source_file_sha256="abcdef123456",
    )
    proj = Project(
        metadata=meta,
        project_dir=tmp_path,
        db_path=db.db_path,
        config={"model": "madlad"},
    )
    db.save_project(proj)

    loaded = db.load_project("test_book")
    assert loaded is not None
    assert loaded.metadata.book_title == "Test Book"
    assert loaded.metadata.source_file_sha256 == "abcdef123456"
    assert loaded.config.get("model") == "madlad"


def test_document_hierarchy_crud(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Testa persistência completa de Document -> Chapter -> Section -> Paragraph -> Segment."""
    # 1. Cria projeto
    meta = ProjectMetadata(
        project_id="doc_hierarchy_test",
        book_title="Hierarchy Test",
        source_file_path=str(tmp_path / "book.txt"),
    )
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))

    # 2. Cria documento
    doc = Document(
        id="doc_1",
        title="Hierarchy Test",
        author="Author Test",
        source_format="txt",
    )
    db.save_document(doc, project_id="doc_hierarchy_test")

    # 3. Cria capítulo
    ch = Chapter(id="ch_01", title="Chapter 1", order=1)
    db.save_chapter(ch, document_id="doc_1")

    # 4. Cria seção e parágrafo
    sec = Section(id="sec_01", chapter_id="ch_01", title="Section 1", order_index=1)
    db.save_section(sec)

    p = Paragraph(
        id="p_01",
        chapter_id="ch_01",
        section_id="sec_01",
        order_index=1,
        raw_text="Hello world.",
    )
    db.save_paragraph(p)

    # 5. Cria segmentos
    seg1 = Segment(
        id="seg_01",
        chapter_id="ch_01",
        paragraph_id="p_01",
        section_id="sec_01",
        sequence_order=1,
        original_text="Hello world.",
    )
    seg2 = Segment(
        id="seg_02",
        chapter_id="ch_01",
        sequence_order=2,
        original_text="Second sentence.",
    )
    db.save_segment(seg1)
    db.save_segment(seg2)

    # 6. Verifica contagens e buscas
    assert db.count_total_segments("doc_hierarchy_test") == 2
    assert db.count_translated_segments("doc_hierarchy_test") == 0

    pending = db.get_pending_segments("doc_hierarchy_test")
    assert len(pending) == 2

    # 7. Atualiza segmento com tradução
    seg1.translated_text = "Olá mundo."
    seg1.status = SegmentStatus.TRANSLATED
    db.save_segment(seg1)

    assert db.count_translated_segments("doc_hierarchy_test") == 1
    assert len(db.get_pending_segments("doc_hierarchy_test")) == 1

    fetched_seg = db.get_segment("seg_01")
    assert fetched_seg is not None
    assert fetched_seg.translated_text == "Olá mundo."
    assert fetched_seg.status == SegmentStatus.TRANSLATED


def test_memory_and_entities_crud(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Testa armazenamento de entidades, personagens, glossário, TM e style bible."""
    meta = ProjectMetadata(
        project_id="memory_test",
        book_title="Memory Test",
        source_file_path="dummy",
    )
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))

    # Entity
    ent = Entity(id="ent_01", project_id="memory_test", name="London", entity_type="location")
    db.save_entity(ent)
    entities = db.get_entities("memory_test")
    assert len(entities) == 1
    assert entities[0].name == "London"

    # Character
    char = CharacterEntry(
        id="char_01",
        name="Arthur Dent",
        gender="masculine",
        aliases=["Arthur", "Dent"],
    )
    db.save_character("memory_test", char)
    chars = db.get_characters("memory_test")
    assert len(chars) == 1
    assert chars[0].name == "Arthur Dent"

    # Glossary
    glo = GlossaryEntry(
        source_term="Babel Fish",
        target_term="Peixe-Babel",
        case_sensitive=True,
    )
    db.save_glossary_entry("memory_test", glo)
    glossary = db.get_glossary("memory_test")
    assert len(glossary) == 1
    assert glossary[0].target_term == "Peixe-Babel"

    # Translation Memory
    tm = TranslationMemoryEntry(
        source_term="Don't Panic",
        target_term="Não Entre em Pânico",
        locked=True,
    )
    db.save_tm_entry("memory_test", tm)
    tms = db.get_tm("memory_test")
    assert len(tms) == 1
    assert tms[0].target_term == "Não Entre em Pânico"

    # Style Bible
    sb = StyleBible(
        narrator="terceira pessoa",
        predominant_treatment="você",
    )
    db.save_style_bible("memory_test", sb)
    fetched_sb = db.get_style_bible("memory_test")
    assert fetched_sb is not None
    assert fetched_sb.predominant_treatment == "você"


def test_translations_and_qa_crud(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Testa persistência de rascunhos de tradução, histórico de revisões e relatórios de QA."""
    meta = ProjectMetadata(project_id="qa_test", book_title="QA Test", source_file_path="dummy")
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))

    doc = Document(id="doc_qa", title="QA Test")
    db.save_document(doc, "qa_test")
    ch = Chapter(id="ch_qa", title="Ch QA", order=1)
    db.save_chapter(ch, "doc_qa")

    seg = Segment(id="seg_qa", chapter_id="ch_qa", original_text="Original text.")
    db.save_segment(seg)

    # Translation Draft
    c1 = TranslationCandidate(text="Texto 1", score=0.9, rank=1)
    c2 = TranslationCandidate(text="Texto 2", score=0.8, rank=2)
    draft = TranslationDraft(
        segment_id="seg_qa",
        selected_text="Texto 1",
        candidates=[c1, c2],
    )
    db.save_translation_draft(draft)

    # Revision
    db.save_revision("seg_qa", "Texto 1", "Texto 1 Revisado", "editor", "ajuste de estilo")

    # QA Report
    issue = QAIssue(
        check_type="style",
        severity=IssueSeverity.SUGGESTED_FIX,
        description="Ajuste sugerido",
        suggested_fix="Texto 1 Revisado",
    )
    report = QAReport(segment_id="seg_qa", passed=False, issues=[issue])
    db.save_qa_report(report)


def test_checkpoint_and_events(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Testa checkpoints de retomada e log persistente de eventos."""
    meta = ProjectMetadata(project_id="chk_test", book_title="Chk Test", source_file_path="dummy")
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))

    chk = Checkpoint(
        id="chk_01",
        project_id="chk_test",
        last_completed_chapter_id="ch_01",
        last_completed_segment_id="seg_10",
        completed_segments=10,
        total_segments=100,
        status="in_progress",
    )
    db.save_checkpoint(chk)

    latest = db.get_latest_checkpoint("chk_test")
    assert latest is not None
    assert latest.completed_segments == 10
    assert latest.last_completed_segment_id == "seg_10"

    # EventLog
    evt = EventLog(
        id="evt_01",
        project_id="chk_test",
        level="INFO",
        phase="translation",
        message="Iniciando capítulo 2",
    )
    db.log_event(evt)


def test_transaction_rollback_on_error(db: SQLiteDatabase) -> None:
    """Verifica que transações com erro executam rollback sem corromper o banco."""
    with pytest.raises(DatabaseError):
        with transaction(db.conn) as cur:
            cur.execute(
                "INSERT INTO projects (id, title, source_file_path, source_file_sha256) "
                "VALUES ('p1', 'T', 'F', 'H');"
            )
            # Força erro de sintaxe SQL para provocar rollback
            cur.execute("INSERT INTO non_existent_table VALUES (1, 2, 3);")

    # Garante que p1 não foi gravado devido ao rollback
    cur = db.conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id = 'p1';")
    assert cur.fetchone() is None
    cur.close()


def test_end_to_end_parsed_document_sqlite_roundtrip(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Verifica persistência e reconstituição completa de documento com elementos ricos."""
    proj_meta = ProjectMetadata(
        project_id="roundtrip_prj",
        book_title="Full Document Roundtrip",
        source_file_path=str(tmp_path / "book.txt"),
    )
    db.save_project(Project(metadata=proj_meta, project_dir=tmp_path, db_path=db.db_path))

    doc = Document(
        id="doc_roundtrip",
        title="Full Document Roundtrip",
        author="Arthur Conan Doyle",
        source_format="txt",
    )
    ch = Chapter(id="ch_rt_01", title="Chapter I: The Arrival", order=1)

    h = Heading(
        id="h_rt_01",
        chapter_id="ch_rt_01",
        level=1,
        raw_text="Chapter I: The Arrival",
        normalized_text="Chapter I: The Arrival",
        reading_order=1,
        source_location=SourceLocation(file_path="book.txt", line_number=1),
    )

    p = Paragraph(
        id="p_rt_01",
        chapter_id="ch_rt_01",
        reading_order=2,
        raw_text="It was a dark and stormy night.",
        normalized_text="It was a dark and stormy night.",
        spans=[FormattingSpan(start=0, end=2, style="bold")],
        source_location=SourceLocation(file_path="book.txt", line_number=3),
    )

    d = DialogueBlock(
        id="d_rt_01",
        chapter_id="ch_rt_01",
        dialogue_marker="—",
        speaker_hint="Holmes",
        reading_order=3,
        raw_text="— Watson, look outside!",
        normalized_text="— Watson, look outside!",
        spans=[FormattingSpan(start=2, end=8, style="italic")],
        source_location=SourceLocation(file_path="book.txt", line_number=5),
    )

    fn = Footnote(
        id="fn_rt_01",
        chapter_id="ch_rt_01",
        marker="[1]",
        raw_text="[1] A historical reference.",
        normalized_text="[1] A historical reference.",
        referencing_unit_id="p_rt_01",
        reading_order=4,
        source_location=SourceLocation(file_path="book.txt", line_number=7),
    )

    img = ImagePlaceholder(
        id="img_rt_01",
        chapter_id="ch_rt_01",
        caption_raw="Figure 1: The manor in the rain.",
        caption_normalized="Figure 1: The manor in the rain.",
        alt_text="Rainy manor",
        relative_path="images/fig1.png",
        reading_order=5,
        source_location=SourceLocation(file_path="book.txt", line_number=9),
    )

    ch.headings.append(h)
    ch.paragraphs.append(p)
    ch.dialogue_blocks.append(d)
    ch.footnotes.append(fn)
    ch.image_placeholders.append(img)
    doc.chapters.append(ch)

    # Persiste o documento completo
    db.save_document(doc, project_id="roundtrip_prj")

    # Carrega o documento do banco
    loaded_doc = db.load_document("roundtrip_prj")
    assert loaded_doc is not None
    assert loaded_doc.id == "doc_roundtrip"
    assert loaded_doc.title == "Full Document Roundtrip"
    assert loaded_doc.author == "Arthur Conan Doyle"
    assert len(loaded_doc.chapters) == 1

    loaded_ch = loaded_doc.chapters[0]
    assert loaded_ch.id == "ch_rt_01"
    assert loaded_ch.title == "Chapter I: The Arrival"

    # Valida Heading
    assert len(loaded_ch.headings) == 1
    assert loaded_ch.headings[0].id == "h_rt_01"
    assert loaded_ch.headings[0].level == 1
    assert loaded_ch.headings[0].source_location.line_number == 1

    # Valida Paragraph e Spans
    assert len(loaded_ch.paragraphs) == 1
    assert loaded_ch.paragraphs[0].id == "p_rt_01"
    assert len(loaded_ch.paragraphs[0].spans) == 1
    assert loaded_ch.paragraphs[0].spans[0].style == "bold"
    assert loaded_ch.paragraphs[0].source_location.line_number == 3

    # Valida DialogueBlock e Spans
    assert len(loaded_ch.dialogue_blocks) == 1
    assert loaded_ch.dialogue_blocks[0].dialogue_marker == "—"
    assert loaded_ch.dialogue_blocks[0].speaker_hint == "Holmes"
    assert loaded_ch.dialogue_blocks[0].spans[0].style == "italic"

    # Valida Footnote
    assert len(loaded_ch.footnotes) == 1
    assert loaded_ch.footnotes[0].marker == "[1]"
    assert loaded_ch.footnotes[0].referencing_unit_id == "p_rt_01"

    # Valida ImagePlaceholder
    assert len(loaded_ch.image_placeholders) == 1
    assert loaded_ch.image_placeholders[0].caption_raw == "Figure 1: The manor in the rain."
    assert loaded_ch.image_placeholders[0].relative_path == "images/fig1.png"
    assert loaded_ch.image_placeholders[0].source_location.line_number == 9
