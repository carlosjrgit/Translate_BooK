"""Testes unitários rigorosos do motor de QA determinístico (Prompt 17)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from book_translator.core.models import Segment, SegmentStatus
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.memory.base import CharacterEntry, GlossaryEntry
from book_translator.qa.base import IssueSeverity, QAFixAuditRecord, QAIssue, QAReport
from book_translator.qa.deterministic import DeterministicQAEngine


@pytest.fixture
def qa_engine() -> DeterministicQAEngine:
    return DeterministicQAEngine()


@pytest.fixture
def sample_segment() -> Segment:
    return Segment(
        id="seg_test_001",
        chapter_id="ch_01",
        paragraph_id=None,
        original_text="Sample English text.",
        sequence_order=1,
        status=SegmentStatus.PENDING,
    )


# -----------------------------------------------------------------------------
# 1. Testes de Números Trocados
# -----------------------------------------------------------------------------
def test_swapped_numbers_detected(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Verifica detecção de números trocados ou divergentes (ex: 42 vs 24)."""
    original = "There were 42 books on the shelf."
    translated = "Havia 24 livros na estante."

    report = qa_engine.evaluate(sample_segment, original, translated)

    assert not report.passed
    assert report.requires_human_review

    num_issues = [i for i in report.issues if i.check_type == "number_mismatch"]
    assert len(num_issues) >= 1
    issue = num_issues[0]
    assert issue.severity == IssueSeverity.REVIEW_REQUIRED
    assert issue.original_snippet == "42"
    assert issue.translated_snippet == "24"


def test_matching_numbers_pass(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Números coincidentes não geram falsos positivos."""
    original = "Chapter 42 has 150 pages and 3 illustrations."
    translated = "O Capítulo 42 tem 150 páginas e 3 ilustrações."

    report = qa_engine.evaluate(sample_segment, original, translated)
    num_issues = [i for i in report.issues if i.check_type == "number_mismatch"]
    assert len(num_issues) == 0


# -----------------------------------------------------------------------------
# 2. Testes de Datas Alteradas
# -----------------------------------------------------------------------------
def test_altered_dates_detected(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Verifica detecção de datas alteradas (ex: 14 de outubro vs 15 de outubro)."""
    original = "The expedition set sail on October 14, 1888."
    translated = "A expedição partiu no dia 15 de outubro de 1888."

    report = qa_engine.evaluate(sample_segment, original, translated)

    date_issues = [i for i in report.issues if i.check_type == "date_mismatch"]
    assert len(date_issues) >= 1
    issue = date_issues[0]
    assert issue.severity == IssueSeverity.REVIEW_REQUIRED
    assert "14" in issue.original_snippet
    assert "15" in issue.translated_snippet


def test_altered_month_detected(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Verifica detecção de mês alterado (ex: August vs setembro)."""
    original = "He passed away in August 1914."
    translated = "Ele faleceu em setembro de 1914."

    report = qa_engine.evaluate(sample_segment, original, translated)
    date_issues = [i for i in report.issues if i.check_type == "date_mismatch"]
    assert len(date_issues) >= 1
    assert date_issues[0].severity == IssueSeverity.REVIEW_REQUIRED
    assert "August" in date_issues[0].original_snippet
    assert "setembro" in date_issues[0].translated_snippet


def test_correct_date_translation_passes(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Tradução correta de data em formato natural passa sem anomalia."""
    original = "On July 4, 1776, the declaration was signed."
    translated = "Em 4 de julho de 1776, a declaração foi assinada."

    report = qa_engine.evaluate(sample_segment, original, translated)
    date_issues = [i for i in report.issues if i.check_type == "date_mismatch"]
    assert len(date_issues) == 0


# -----------------------------------------------------------------------------
# 3. Testes de Nomes Próprios Inconsistentes
# -----------------------------------------------------------------------------
def test_inconsistent_proper_names_detected(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Detecta grafias corrompidas de nomes próprios conhecidos (ex: Sherlock Holmes vs Sherlock Holms)."""
    original = "Sherlock Holmes examined the suspicious stain."
    translated = "Sherlock Holms examinou a mancha suspeita."

    characters = [
        CharacterEntry(
            id="char_01",
            canonical_name="Sherlock Holmes",
            aliases=["Holmes", "Mr. Holmes"],
        )
    ]

    report = qa_engine.evaluate(
        sample_segment,
        original,
        translated,
        characters=characters,
    )

    name_issues = [i for i in report.issues if i.check_type == "proper_name_inconsistency"]
    assert len(name_issues) >= 1
    issue = name_issues[0]
    assert issue.severity == IssueSeverity.SUGGESTED_FIX
    assert issue.original_snippet == "Sherlock Holmes"
    assert issue.translated_snippet == "Sherlock Holms"
    assert issue.suggested_fix == "Sherlock Holmes"


def test_proper_names_correct_passes(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Nomes próprios preservados ou com aliases válidos passam sem alerta."""
    original = "Sherlock Holmes and Dr. John Watson left the room."
    translated = "Sherlock Holmes e o Dr. John Watson saíram da sala."

    characters = [
        CharacterEntry(id="c1", canonical_name="Sherlock Holmes"),
        CharacterEntry(id="c2", canonical_name="John Watson"),
    ]

    report = qa_engine.evaluate(
        sample_segment,
        original,
        translated,
        characters=characters,
    )
    name_issues = [i for i in report.issues if i.check_type == "proper_name_inconsistency"]
    assert len(name_issues) == 0


# -----------------------------------------------------------------------------
# 4. Testes de Termos Locked
# -----------------------------------------------------------------------------
def test_locked_term_untranslated_safe_fix(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Termo locked mantido em inglês na tradução gera SAFE FIX com substituto canônico."""
    original = "The spacecraft entered the Wormhole near Saturn."
    translated = "A nave entrou no Wormhole perto de Saturno."

    glossary = [
        GlossaryEntry(
            source_term="Wormhole",
            target_term="Buraco de Minhoca",
            locked=True,
        )
    ]

    report = qa_engine.evaluate(sample_segment, original, translated, glossary=glossary)

    locked_issues = [i for i in report.issues if i.check_type == "locked_term_violation"]
    assert len(locked_issues) >= 1
    issue = locked_issues[0]
    assert issue.severity == IssueSeverity.SAFE_FIX
    assert issue.original_snippet == "Wormhole"
    assert issue.translated_snippet == "Wormhole"
    assert issue.suggested_fix == "Buraco de Minhoca"


def test_locked_term_missing_translation_review_required(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Termo locked traduzido incorretamente por sinônimo não-canônico gera REVIEW REQUIRED."""
    original = "The spacecraft entered the Wormhole near Saturn."
    translated = "A nave entrou no túnel cósmico perto de Saturno."

    glossary = [
        GlossaryEntry(
            source_term="Wormhole",
            target_term="Buraco de Minhoca",
            locked=True,
        )
    ]

    report = qa_engine.evaluate(sample_segment, original, translated, glossary=glossary)

    locked_issues = [i for i in report.issues if i.check_type == "locked_term_violation"]
    assert len(locked_issues) >= 1
    issue = locked_issues[0]
    assert issue.severity == IssueSeverity.REVIEW_REQUIRED
    assert issue.original_snippet == "Wormhole"
    assert issue.suggested_fix == "Buraco de Minhoca"


# -----------------------------------------------------------------------------
# 5. Testes de Negações e Inversão de Polaridade
# -----------------------------------------------------------------------------
def test_polarity_inversion_negative_to_affirmative(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Sentença negativa traduzida como afirmativa gera REVIEW REQUIRED."""
    original = "He did not open the door."
    translated = "Ele abriu a porta."

    report = qa_engine.evaluate(sample_segment, original, translated)

    pol_issues = [i for i in report.issues if i.check_type == "polarity_mismatch"]
    assert len(pol_issues) >= 1
    issue = pol_issues[0]
    assert issue.severity == IssueSeverity.REVIEW_REQUIRED
    assert "not" in issue.original_snippet.lower()


def test_polarity_inversion_affirmative_to_negative(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Sentença afirmativa traduzida com negação espúria gera REVIEW REQUIRED."""
    original = "The witness confirmed the statement."
    translated = "A testemunha não confirmou a declaração."

    report = qa_engine.evaluate(sample_segment, original, translated)

    pol_issues = [i for i in report.issues if i.check_type == "polarity_mismatch"]
    assert len(pol_issues) >= 1
    assert pol_issues[0].severity == IssueSeverity.REVIEW_REQUIRED
    assert "não" in pol_issues[0].translated_snippet.lower()


# -----------------------------------------------------------------------------
# 6. Testes de Percentuais, Moedas e Medidas
# -----------------------------------------------------------------------------
def test_percentage_mismatch_and_spacing_fix(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Percentual com valor trocado gera REVIEW REQUIRED; com espaço gera SAFE FIX."""
    # Valor trocado
    report_bad = qa_engine.evaluate(sample_segment, "Profits rose by 15%.", "O lucro subiu 50%.")
    pct_issues = [i for i in report_bad.issues if i.check_type == "percentage_mismatch"]
    assert len(pct_issues) >= 1
    assert pct_issues[0].severity == IssueSeverity.REVIEW_REQUIRED

    # Espaço supérfluo ("15 %" -> "15%")
    report_fix = qa_engine.evaluate(sample_segment, "Profits rose by 15%.", "O lucro subiu 15 %.")
    fix_issues = [i for i in report_fix.issues if i.check_type == "percentage_mismatch"]
    assert len(fix_issues) >= 1
    assert fix_issues[0].severity == IssueSeverity.SAFE_FIX
    assert fix_issues[0].suggested_fix == "15%"


def test_currency_mismatch(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Moeda divergente ($ vs £ ou euros) gera REVIEW REQUIRED."""
    report = qa_engine.evaluate(sample_segment, "The price is $500.", "O preço é 500 euros.")
    curr_issues = [i for i in report.issues if i.check_type == "currency_mismatch"]
    assert len(curr_issues) >= 1
    assert curr_issues[0].severity == IssueSeverity.REVIEW_REQUIRED


def test_measurement_untranslated_safe_fix(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Medida mantida em inglês ("10 miles") gera SAFE FIX ("10 milhas")."""
    report = qa_engine.evaluate(
        sample_segment,
        "They walked for 10 miles in the desert.",
        "Eles caminharam por 10 miles no deserto.",
    )
    meas_issues = [i for i in report.issues if i.check_type == "measurement_mismatch"]
    assert len(meas_issues) >= 1
    assert meas_issues[0].severity == IssueSeverity.SAFE_FIX
    assert meas_issues[0].suggested_fix == "10 milhas"


# -----------------------------------------------------------------------------
# 7. Testes de URLs e Referências/Notas
# -----------------------------------------------------------------------------
def test_corrupted_url_safe_fix(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """URL corrompida por tradução gera SAFE FIX restaurando a URL original."""
    original = "See https://example.com/archive for full details."
    translated = "Veja https://exemplo.com/arquivo para mais detalhes."

    report = qa_engine.evaluate(sample_segment, original, translated)

    url_issues = [i for i in report.issues if i.check_type == "url_mismatch"]
    assert len(url_issues) >= 1
    assert url_issues[0].severity == IssueSeverity.SAFE_FIX
    assert url_issues[0].suggested_fix == "https://example.com/archive"


def test_missing_footnote_marker(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Nota de rodapé ou marcador de citação ausente gera REVIEW REQUIRED."""
    original = "According to the ancient codex[1], the temple was sealed."
    translated = "De acordo com o antigo códice, o templo foi selado."

    report = qa_engine.evaluate(sample_segment, original, translated)

    fn_issues = [i for i in report.issues if i.check_type == "footnote_mismatch"]
    assert len(fn_issues) >= 1
    assert fn_issues[0].severity == IssueSeverity.REVIEW_REQUIRED
    assert "[1]" in fn_issues[0].original_snippet


# -----------------------------------------------------------------------------
# 8. Testes de Omissão, Truncamento e Duplicação
# -----------------------------------------------------------------------------
def test_severe_omission_truncation(qa_engine: DeterministicQAEngine, sample_segment: Segment):
    """Truncamento severo de conteúdo (> 40 chars cortado para < 35%) gera REVIEW REQUIRED."""
    original = "This is a very long and detailed sentence containing extensive context about the plot and characters."
    translated = "Isso é curto."

    report = qa_engine.evaluate(sample_segment, original, translated)

    om_issues = [i for i in report.issues if i.check_type == "omission_or_duplication"]
    assert len(om_issues) >= 1
    assert om_issues[0].severity == IssueSeverity.REVIEW_REQUIRED


def test_contiguous_phrase_duplication_safe_fix(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Duplicação contígua de frase por gagueira de pipeline gera SAFE FIX."""
    original = "The detective walked into the dark alley."
    translated = "O detetive entrou no beco escuro. O detetive entrou no beco escuro."

    report = qa_engine.evaluate(sample_segment, original, translated)

    dup_issues = [
        i
        for i in report.issues
        if i.check_type == "omission_or_duplication" and i.severity == IssueSeverity.SAFE_FIX
    ]
    assert len(dup_issues) >= 1
    assert dup_issues[0].suggested_fix == "O detetive entrou no beco escuro."


# -----------------------------------------------------------------------------
# 9. Testes de Aplicação de SAFE FIX e Trilha de Auditoria
# -----------------------------------------------------------------------------
def test_apply_safe_fixes_generates_audit_trail(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Aplica SAFE FIXes cumulativos e produz registros auditáveis de cada alteração."""
    original = "They walked 10 miles to the Wormhole station."
    translated = "Eles caminharam 10 miles para a estação Wormhole."

    glossary = [
        GlossaryEntry(
            source_term="Wormhole",
            target_term="Buraco de Minhoca",
            locked=True,
        )
    ]

    report = qa_engine.evaluate(sample_segment, original, translated, glossary=glossary)

    # Executa aplicação de correções determinísticas
    fixed_text, audit_records = qa_engine.apply_safe_fixes(
        segment_id=sample_segment.id,
        original_text=original,
        translated_text=translated,
        report=report,
    )

    assert "10 milhas" in fixed_text
    assert "Buraco de Minhoca" in fixed_text
    assert "10 miles" not in fixed_text
    assert "Wormhole" not in fixed_text

    # Verifica auditoria
    assert len(audit_records) >= 2
    for record in audit_records:
        assert isinstance(record, QAFixAuditRecord)
        assert record.segment_id == sample_segment.id
        assert record.old_text != record.new_text
        assert record.rule_applied.startswith("safe_fix:")
        assert record.timestamp != ""
        assert record.id.startswith("fix_seg_test_001_")


def test_review_required_never_auto_fixed(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Garante que issues categorizadas como REVIEW REQUIRED NUNCA são aplicadas automaticamente."""
    original = "There were 42 books on the shelf."
    translated = "Havia 24 livros na estante."

    report = qa_engine.evaluate(sample_segment, original, translated)

    fixed_text, audit_records = qa_engine.apply_safe_fixes(
        segment_id=sample_segment.id,
        original_text=original,
        translated_text=translated,
        report=report,
    )

    # O texto deve permanecer inalterado e nenhum audit record de SAFE FIX deve ser criado
    assert fixed_text == translated
    assert len(audit_records) == 0


# -----------------------------------------------------------------------------
# 10. Teste de Persistência no Banco de Dados
# -----------------------------------------------------------------------------
def test_db_qa_report_and_audit_persistence(
    qa_engine: DeterministicQAEngine, sample_segment: Segment
):
    """Valida salvamento e recuperação de QAIssues e QAFixAuditRecord no SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_qa.db"
        db = SQLiteDatabase(db_path)
        try:
            db.initialize()

            # Configura projeto, documento e capítulo para satisfazer chaves estrangeiras
            from book_translator.core.models import (
                Chapter,
                Document,
                DocumentMetadata,
                Project,
                ProjectMetadata,
            )

            project = Project(
                metadata=ProjectMetadata(
                    project_id="p_qa",
                    book_title="QA Test Book",
                    source_file_path="source.txt",
                    source_language="en",
                    target_language="pt-BR",
                ),
                project_dir=Path(tmpdir),
                db_path=db_path,
            )
            db.save_project(project)

            chap = Chapter(id="ch_01", title="Chapter 1", order=1)
            doc = Document(
                id="doc_qa",
                metadata=DocumentMetadata(title="QA Test Book"),
                chapters=[chap],
            )
            db.save_document(doc, project_id="p_qa")

            # Salva o segmento
            db.save_segment(sample_segment)

            # Cria e salva relatório de QA
            report = QAReport(
                segment_id=sample_segment.id,
                passed=False,
                issues=[
                    QAIssue(
                        check_type="number_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description="Número divergente.",
                        original_snippet="42",
                        translated_snippet="24",
                    ),
                    QAIssue(
                        check_type="locked_term_violation",
                        severity=IssueSeverity.SAFE_FIX,
                        description="Termo locked não traduzido.",
                        original_snippet="Wormhole",
                        translated_snippet="Wormhole",
                        suggested_fix="Buraco de Minhoca",
                    ),
                ],
            )
            db.save_qa_report(report)

            # Recupera issues salvas
            saved_issues = db.get_qa_issues(sample_segment.id)
            assert len(saved_issues) == 2
            assert saved_issues[0].check_type == "number_mismatch"
            assert saved_issues[0].original_snippet == "42"
            assert saved_issues[0].translated_snippet == "24"
            assert saved_issues[1].severity == IssueSeverity.SAFE_FIX
            assert saved_issues[1].suggested_fix == "Buraco de Minhoca"

            # Salva e recupera auditoria de SAFE FIX
            audit_record = QAFixAuditRecord(
                id="audit_001",
                segment_id=sample_segment.id,
                check_type="locked_term_violation",
                old_text="Entrou no Wormhole.",
                new_text="Entrou no Buraco de Minhoca.",
                rule_applied="safe_fix:locked_term_violation",
                metadata={"original_snippet": "Wormhole"},
            )
            db.save_qa_fix_audit(audit_record)

            saved_audits = db.get_qa_fix_audits(sample_segment.id)
            assert len(saved_audits) == 1
            assert saved_audits[0].id == "audit_001"
            assert saved_audits[0].old_text == "Entrou no Wormhole."
            assert saved_audits[0].new_text == "Entrou no Buraco de Minhoca."
            assert saved_audits[0].rule_applied == "safe_fix:locked_term_violation"
        finally:
            db.close()
