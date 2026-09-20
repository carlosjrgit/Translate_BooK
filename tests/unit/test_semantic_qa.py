"""Testes unitários rigorosos para o motor de QA Semântico Multi-Sinal (Prompt 18)."""

from __future__ import annotations

import pytest

from book_translator.core.models import Segment, SegmentStatus
from book_translator.memory.base import StyleBible
from book_translator.qa.base import IssueSeverity, SemanticEvaluationResult
from book_translator.qa.semantic import MockSemanticEncoder, SemanticQAEngine


@pytest.fixture
def semantic_engine() -> SemanticQAEngine:
    return SemanticQAEngine(encoder=MockSemanticEncoder())


@pytest.fixture
def sample_segment() -> Segment:
    return Segment(
        id="seg_sem_001",
        chapter_id="ch_01",
        paragraph_id=None,
        original_text="Original text.",
        sequence_order=1,
        status=SegmentStatus.PENDING,
    )


# -----------------------------------------------------------------------------
# 1. Testes de Omissão e Adição Semântica
# -----------------------------------------------------------------------------
def test_semantic_omission_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta truncamento semântico onde a maior parte dos conceitos foi omitida."""
    original = "The sapphire vanished at midnight from the heavy iron safe in the master bedroom."
    translated = "A safira sumiu."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert not result.passed
    om_issues = [i for i in result.issues if i.check_type == "semantic_omission"]
    assert len(om_issues) >= 1
    assert om_issues[0].severity == IssueSeverity.REVIEW_REQUIRED
    assert result.signal_scores.content_preservation < 0.6


def test_semantic_addition_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta alucinação de conteúdo não existente no original."""
    original = "She looked out the window."
    translated = (
        "Ela olhou pela janela contemplando os vastos campos verdes onde os cavalos pastavam alegremente "
        "sob a luz dourada do sol poente de outono."
    )

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert not result.passed
    add_issues = [i for i in result.issues if i.check_type == "semantic_addition"]
    assert len(add_issues) >= 1
    assert add_issues[0].severity == IssueSeverity.REVIEW_REQUIRED


# -----------------------------------------------------------------------------
# 2. Testes de Inversão de Sentido e Polaridade
# -----------------------------------------------------------------------------
def test_meaning_reversal_antonyms_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta tradução com significado antagônico (ex: guilty vs inocente)."""
    original = "The prisoner was found guilty by the jury."
    translated = "O prisioneiro foi considerado inocente pelo júri."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert not result.passed
    rev_issues = [i for i in result.issues if i.check_type == "meaning_reversal"]
    assert len(rev_issues) >= 1
    assert rev_issues[0].severity == IssueSeverity.REVIEW_REQUIRED
    assert rev_issues[0].original_snippet == "guilty"
    assert rev_issues[0].translated_snippet == "inocente"
    assert result.signal_scores.polarity_consistency <= 0.3


def test_polarity_inversion_negation_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta oração negativa traduzida como afirmativa sem negação."""
    original = "Holmes did not touch the weapon on the table."
    translated = "Holmes tocou na arma sobre a mesa."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert not result.passed
    pol_issues = [i for i in result.issues if i.check_type == "polarity_inversion"]
    assert len(pol_issues) >= 1
    assert pol_issues[0].severity == IssueSeverity.REVIEW_REQUIRED


# -----------------------------------------------------------------------------
# 3. Testes de Mudança de Sujeito Gramatical
# -----------------------------------------------------------------------------
def test_subject_shift_in_dialogue_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta quando o sujeito/agente da fala é invertido entre os interlocutores."""
    original = "Holmes asked Watson about the mysterious footprint."
    translated = "Watson perguntou a Holmes sobre a pegada misteriosa."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert not result.passed
    shift_issues = [i for i in result.issues if i.check_type == "subject_shift"]
    assert len(shift_issues) >= 1
    assert shift_issues[0].severity == IssueSeverity.REVIEW_REQUIRED
    assert shift_issues[0].suggested_fix == "Holmes"


def test_subject_shift_pronouns_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta troca de gênero de sujeito pronominal (He vs Ela)."""
    original = "He stared into the darkness."
    translated = "Ela encarou a escuridão."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert not result.passed
    shift_issues = [i for i in result.issues if i.check_type == "subject_shift"]
    assert len(shift_issues) >= 1
    assert shift_issues[0].original_snippet == "He"
    assert shift_issues[0].translated_snippet == "Ela"


# -----------------------------------------------------------------------------
# 4. Testes de Perda de Intensidade
# -----------------------------------------------------------------------------
def test_intensity_loss_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta atenuação indevida de intensidade emocional (furious vs chateado)."""
    original = "Lord Blackwood was furious when the safe was opened."
    translated = "Lord Blackwood estava chateado quando o cofre foi aberto."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    loss_issues = [i for i in result.issues if i.check_type == "intensity_loss"]
    assert len(loss_issues) >= 1
    assert loss_issues[0].severity == IssueSeverity.SUGGESTED_FIX
    assert "furioso" in loss_issues[0].suggested_fix


def test_intensity_loss_feminine_inflection(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta atenuação com concordância de gênero feminino (terrified vs preocupada)."""
    original = "Lady Margaret was terrified by the ghostly hound."
    translated = "Lady Margaret estava preocupada com o cão fantasmagórico."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    loss_issues = [i for i in result.issues if i.check_type == "intensity_loss"]
    assert len(loss_issues) >= 1
    assert loss_issues[0].translated_snippet == "preocupada"


# -----------------------------------------------------------------------------
# 5. Testes de Falsos Cognatos e Tradução Literal Problemática
# -----------------------------------------------------------------------------
def test_false_cognate_actually_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta falso cognato 'actually' traduzido como 'atualmente'."""
    original = "Actually, the thief did not leave through the main garden door."
    translated = "Atualmente, o ladrão não saiu pela porta principal do jardim."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    lit_issues = [i for i in result.issues if i.check_type == "problematic_literal_translation"]
    assert len(lit_issues) >= 1
    assert lit_issues[0].severity == IssueSeverity.SUGGESTED_FIX
    assert "na verdade" in lit_issues[0].suggested_fix.lower()


def test_false_cognate_realize_inflected_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta falso cognato 'realize' traduzido como 'realizou'."""
    original = "He did not realize that the footprints belonged to a hound."
    translated = "Ele não realizou que as pegadas pertenciam a um cão de caça."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    lit_issues = [i for i in result.issues if i.check_type == "problematic_literal_translation"]
    assert len(lit_issues) >= 1
    assert "perceber" in lit_issues[0].suggested_fix.lower()


# -----------------------------------------------------------------------------
# 6. Testes de Mudança de Relações
# -----------------------------------------------------------------------------
def test_relationship_shift_informality_detected(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Detecta quebra de registro formal em diálogos institucionais."""
    original = "The witness addressed the high magistrate respectfully."
    translated = "A testemunha falou com o magistrado tipo assim respeitosamente, né."

    class DummyContext:
        style_bible = StyleBible(project_id="p1", formality_level="formal")

    result = semantic_engine.evaluate_semantic(
        sample_segment, original, translated, context=DummyContext()
    )

    rel_issues = [i for i in result.issues if i.check_type == "relationship_shift"]
    assert len(rel_issues) >= 1
    assert rel_issues[0].severity == IssueSeverity.REVIEW_REQUIRED


# -----------------------------------------------------------------------------
# 7. Testes de Validação Positiva (Ausência de Falsos Positivos)
# -----------------------------------------------------------------------------
def test_valid_literary_translations_pass(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Traduções literárias fluídas e paráfrases válidas não geram falsos positivos."""
    valid_pairs = [
        (
            "Dr. John Watson sat near the fireplace at 221B Baker Street, listening carefully.",
            "O Dr. John Watson sentou-se perto da lareira na Baker Street, 221B, ouvindo atentamente.",
        ),
        (
            "Sherlock Holmes examined the footprint with his magnifying glass.",
            "Sherlock Holmes analisou a pegada através de sua lupa.",
        ),
        (
            "'The thief was hasty,' said Holmes.",
            "— O ladrão foi apressado — afirmou Holmes.",
        ),
        (
            "The train arrived at Dartmoor under heavy rain and ominous thunder.",
            "O trem alcançou Dartmoor sob tempestade intensa e trovões ameaçadores.",
        ),
    ]

    for orig, trans in valid_pairs:
        result = semantic_engine.evaluate_semantic(sample_segment, orig, trans)
        assert result.passed, f"Falso positivo gerado para '{orig}': {result.issues}"
        assert len(result.issues) == 0
        assert result.overall_score >= 0.70


# -----------------------------------------------------------------------------
# 8. Inspecionabilidade de Scores e Justificativas
# -----------------------------------------------------------------------------
def test_semantic_evaluation_inspectability(
    semantic_engine: SemanticQAEngine, sample_segment: Segment
):
    """Garante que todos os sub-scores e justificativas são calculados e acessíveis."""
    original = "He carefully inspected the ancient brass lock on the mahogany door."
    translated = "Ele examinou com cautela a velha fechadura de latão na porta de mogno."

    result = semantic_engine.evaluate_semantic(sample_segment, original, translated)

    assert isinstance(result, SemanticEvaluationResult)
    assert 0.0 <= result.overall_score <= 1.0
    assert 0.0 <= result.signal_scores.embedding_similarity <= 1.0
    assert 0.0 <= result.signal_scores.subject_consistency <= 1.0
    assert 0.0 <= result.signal_scores.polarity_consistency <= 1.0
    assert 0.0 <= result.signal_scores.content_preservation <= 1.0
    assert 0.0 <= result.signal_scores.intensity_preservation <= 1.0
    assert 0.0 <= result.signal_scores.literal_correctness <= 1.0
    assert len(result.justifications) > 0
