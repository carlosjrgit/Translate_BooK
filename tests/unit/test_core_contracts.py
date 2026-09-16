"""Testes dos modelos de domínio canônicos e contratos de protocolo."""

from __future__ import annotations

from pathlib import Path

from book_translator.core.models import (
    Chapter,
    Document,
    Project,
    ProjectMetadata,
    Segment,
    SegmentStatus,
)
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    StyleBible,
    TranslationMemoryEntry,
)
from book_translator.qa.base import IssueSeverity, QAIssue, QAReport
from book_translator.translation.base import TranslationCandidate, TranslationDraft


def test_segment_creation_and_status() -> None:
    """Valida a criação de um Segment e suas propriedades de status."""
    seg = Segment(
        id="chapter_001_segment_0001",
        chapter_id="chapter_001",
        original_text="Call me Ishmael.",
        sequence_order=1,
    )
    assert seg.status == SegmentStatus.PENDING
    assert not seg.is_translated

    seg.translated_text = "Pode me chamar de Ishmael."
    seg.status = SegmentStatus.TRANSLATED
    assert seg.is_translated


def test_chapter_and_document_structure() -> None:
    """Valida a hierarquia Document -> Chapter -> Segment."""
    seg1 = Segment(
        id="ch1_seg1",
        chapter_id="ch1",
        original_text="First sentence.",
    )
    seg2 = Segment(
        id="ch1_seg2",
        chapter_id="ch1",
        original_text="Second sentence of the chapter.",
    )

    ch = Chapter(
        id="ch1",
        title="Chapter 1: Loomings",
        order=1,
        segments=[seg1, seg2],
    )
    assert ch.total_words() == 7

    doc = Document(
        id="doc_moby_dick",
        title="Moby-Dick",
        author="Herman Melville",
        source_format="epub",
        chapters=[ch],
    )
    assert doc.total_chapters == 1
    assert doc.total_segments == 2


def test_project_instantiation(tmp_path: Path) -> None:
    """Valida o agrupamento de informações no objeto Project."""
    meta = ProjectMetadata(
        project_id="the_book",
        book_title="The Book",
        source_file_path=str(tmp_path / "book.epub"),
    )
    proj = Project(
        metadata=meta,
        project_dir=tmp_path / "projects" / "the_book",
        db_path=tmp_path / "projects" / "the_book" / "project.db",
    )
    assert proj.metadata.project_id == "the_book"
    assert proj.db_path.name == "project.db"


def test_memory_models() -> None:
    """Valida os modelos de memória Character, TM, Glossary e StyleBible."""
    char = CharacterEntry(
        id="char_01",
        name="Margaret Henderson",
        aliases=["Margaret", "Mrs. Henderson", "Maggie"],
        gender="feminine",
        relations=["mother of Jack"],
    )
    assert char.gender == "feminine"
    assert "Maggie" in char.aliases

    tm = TranslationMemoryEntry(
        source_term="The Royal Guard",
        target_term="Guarda Real",
        entry_type="organization",
        locked=True,
    )
    assert tm.locked is True

    glossary = GlossaryEntry(
        source_term="The Watch",
        target_term="A Patrulha",
        context="militar",
    )
    assert glossary.source_term == "The Watch"

    style = StyleBible()
    assert style.predominant_treatment == "você"


def test_qa_models() -> None:
    """Valida modelos de QA e reporte de anomalias."""
    issue = QAIssue(
        check_type="number_mismatch",
        severity=IssueSeverity.SAFE_FIX,
        description="Ano 1974 foi traduzido como 1978",
        original_snippet="1974",
        translated_snippet="1978",
        suggested_fix="1974",
    )
    report = QAReport(
        segment_id="ch1_seg1",
        passed=False,
        issues=[issue],
    )
    assert not report.passed
    assert report.has_safe_fixes
    assert not report.requires_human_review


def test_translation_draft_and_candidates() -> None:
    """Valida criação de rascunhos de tradução com candidatos N-best."""
    c1 = TranslationCandidate(text="Opção 1", score=0.95, rank=1)
    c2 = TranslationCandidate(text="Opção 2", score=0.88, rank=2)
    draft = TranslationDraft(
        segment_id="ch1_seg1",
        selected_text="Opção 1",
        candidates=[c1, c2],
        engine_name="madlad-400-10b-mt",
    )
    assert draft.selected_text == "Opção 1"
    assert len(draft.candidates) == 2
