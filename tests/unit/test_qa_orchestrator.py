"""Testes unitários para o UnifiedQAOrchestrator integrando QA Determinístico, Semântico e Retrotradução."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from book_translator.core.models import (
    Chapter,
    Document,
    DocumentMetadata,
    Project,
    ProjectMetadata,
    Segment,
    SegmentStatus,
)
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.qa.backtranslation import BacktranslationVerifier
from book_translator.qa.deterministic import DeterministicQAEngine
from book_translator.qa.orchestrator import UnifiedQAOrchestrator
from book_translator.qa.semantic import MockSemanticEncoder, SemanticQAEngine
from book_translator.translation.madlad import MadladTranslationEngine, MockMadladBackend


@pytest.fixture
def orchestrator() -> UnifiedQAOrchestrator:
    engine = MadladTranslationEngine(backend=MockMadladBackend())
    return UnifiedQAOrchestrator(
        deterministic_engine=DeterministicQAEngine(),
        semantic_engine=SemanticQAEngine(encoder=MockSemanticEncoder()),
        backtranslation_verifier=BacktranslationVerifier(engine=engine),
    )


@pytest.fixture
def sample_segment() -> Segment:
    return Segment(
        id="seg_orch_001",
        chapter_id="ch_01",
        paragraph_id=None,
        original_text="The sapphire vanished at midnight from the safe.",
        sequence_order=1,
        status=SegmentStatus.PENDING,
    )


def test_unified_qa_clean_translation_passes(
    orchestrator: UnifiedQAOrchestrator, sample_segment: Segment
):
    """Tradução fiel é aprovada em todos os 3 níveis de validação."""
    original = "The sapphire vanished at midnight from the safe."
    translated = "A safira desapareceu à meia-noite do cofre."

    report = orchestrator.evaluate(
        sample_segment,
        original,
        translated,
    )

    assert report.passed
    assert not report.requires_human_review
    assert len(report.issues) == 0
    assert report.semantic_result.overall_score >= 0.70
    assert report.backtranslation_evidence is not None


def test_unified_qa_combines_deterministic_and_semantic_issues(
    orchestrator: UnifiedQAOrchestrator, sample_segment: Segment
):
    """Detecta simultaneamente anomalias determinísticas (data/número) e semânticas (falso cognato)."""
    # Original tem data 1888 e termo "actually"
    original = "Actually, the expedition departed on October 14, 1888."
    # Tradução troca a data para dia 15 e traduz "actually" como falso cognato "atualmente"
    translated = "Atualmente, a expedição partiu no dia 15 de outubro de 1888."

    report = orchestrator.evaluate(sample_segment, original, translated)

    assert not report.passed
    assert report.requires_human_review

    det_types = [i.check_type for i in report.deterministic_issues]
    sem_types = [i.check_type for i in report.semantic_issues]

    assert "date_mismatch" in det_types
    assert "problematic_literal_translation" in sem_types


def test_unified_qa_corroborates_with_backtranslation(
    orchestrator: UnifiedQAOrchestrator, sample_segment: Segment
):
    """Evidência de retrotradução corrobora anomalia semântica de polaridade/negação."""
    original = "Holmes did not touch the weapon on the table."
    translated = "Holmes tocou na arma sobre a mesa."

    report = orchestrator.evaluate(sample_segment, original, translated)

    assert not report.passed
    # Verifica que a evidência de retrotradução foi anexada e detectou negação invertida
    assert report.backtranslation_evidence.has_potential_issue
    assert not report.backtranslation_evidence.negation_preserved

    # Verifica anotação de corroboração na issue
    pol_issue = next(i for i in report.semantic_issues if i.check_type == "polarity_inversion")
    assert "Confirmado por retrotradução" in pol_issue.description


def test_unified_qa_db_persistence(sample_segment: Segment):
    """Valida gravação do relatório de QA consolidado na base SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_orch.db"
        db = SQLiteDatabase(db_path)
        try:
            db.initialize()

            # Configura projeto e documento
            proj = Project(
                metadata=ProjectMetadata(
                    project_id="p_orch",
                    book_title="Orchestrator Test",
                    source_file_path="source.txt",
                ),
                project_dir=Path(tmpdir),
                db_path=db_path,
            )
            db.save_project(proj)

            chap = Chapter(id="ch_01", title="Chapter 1", order=1)
            doc = Document(id="doc_01", metadata=DocumentMetadata(title="Book"), chapters=[chap])
            db.save_document(doc, project_id="p_orch")
            db.save_segment(sample_segment)

            orchestrator = UnifiedQAOrchestrator(
                deterministic_engine=DeterministicQAEngine(),
                semantic_engine=SemanticQAEngine(encoder=MockSemanticEncoder()),
                backtranslation_verifier=BacktranslationVerifier(),
                db=db,
            )

            # Executa com anomalia
            original = "There were 42 books on the shelf."
            translated = "Havia 24 livros na estante."

            report = orchestrator.evaluate(sample_segment, original, translated)
            assert not report.passed

            # Recupera as issues salvas no SQLite
            saved_issues = db.get_qa_issues(sample_segment.id)
            assert len(saved_issues) >= 1
            assert any(i.check_type == "number_mismatch" for i in saved_issues)
        finally:
            db.close()
