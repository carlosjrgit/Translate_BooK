"""Testes unitários para o módulo de Retrotradução (Backtranslation) como Evidência Auxiliar (Prompt 19)."""

from __future__ import annotations

import pytest

from book_translator.qa.backtranslation import BacktranslationVerifier
from book_translator.translation.madlad import MadladTranslationEngine, MockMadladBackend


@pytest.fixture
def backtranslation_verifier() -> BacktranslationVerifier:
    engine = MadladTranslationEngine(backend=MockMadladBackend())
    return BacktranslationVerifier(engine=engine, enabled=True)


# -----------------------------------------------------------------------------
# 1. Ciclo Completo EN -> PT-BR -> EN
# -----------------------------------------------------------------------------
def test_backtranslation_cycle_legitimate_translation(
    backtranslation_verifier: BacktranslationVerifier,
):
    """Tradução legítima gera reconstrução de alta fidelidade sem alertas críticos."""
    original_en = "Sherlock Holmes examined the footprint with his magnifying glass."
    translated_pt = "Sherlock Holmes examinou a pegada com sua lente de aumento."

    evidence = backtranslation_verifier.verify(original_en, translated_pt)

    assert not evidence.has_potential_issue
    assert evidence.negation_preserved
    assert evidence.subject_preserved
    assert evidence.lexical_chrf > 0.60
    assert "sherlock holmes" in evidence.reconstructed_en.lower()


# -----------------------------------------------------------------------------
# 2. Detecção de Casos Artificiais: Omissão
# -----------------------------------------------------------------------------
def test_backtranslation_detects_severe_omission(
    backtranslation_verifier: BacktranslationVerifier,
):
    """Detecta truncamento severo onde o texto reconstruído perdeu metade do conteúdo."""
    original_en = (
        "The sapphire vanished at midnight from the heavy iron safe in the master bedroom of the manor."
    )
    # Tradução truncada apenas para "A safira sumiu"
    translated_pt = "A safira desapareceu."

    evidence = backtranslation_verifier.verify(original_en, translated_pt)

    assert evidence.has_potential_issue
    assert any("perdeu mais de 50% do tamanho" in note for note in evidence.divergence_notes)


# -----------------------------------------------------------------------------
# 3. Detecção de Casos Artificiais: Inversão de Negação
# -----------------------------------------------------------------------------
def test_backtranslation_detects_negation_inversion(
    backtranslation_verifier: BacktranslationVerifier,
):
    """Detecta quando uma oração negativa no original virou afirmativa na reconstrução."""
    original_en = "Holmes did not touch the weapon on the table."
    # Tradução invertida espúria (sem negação)
    translated_pt = "Holmes tocou na arma sobre a mesa."

    evidence = backtranslation_verifier.verify(original_en, translated_pt)

    assert evidence.has_potential_issue
    assert not evidence.negation_preserved
    assert any("oração original continha negação" in note for note in evidence.divergence_notes)


# -----------------------------------------------------------------------------
# 4. Detecção de Casos Artificiais: Mudança de Sujeito
# -----------------------------------------------------------------------------
def test_backtranslation_detects_subject_alteration(
    backtranslation_verifier: BacktranslationVerifier,
):
    """Detecta quando o sujeito pronominal (He vs She) foi alterado na volta."""
    original_en = "He stared into the dark corridor."
    # Traduzido com pronome feminino trocado
    translated_pt = "Ela encarou o corredor escuro."

    evidence = backtranslation_verifier.verify(original_en, translated_pt)

    assert evidence.has_potential_issue
    assert not evidence.subject_preserved
    assert any("sujeito pronominal alternado" in note for note in evidence.divergence_notes)


# -----------------------------------------------------------------------------
# 5. Não-Autoridade e Documentação de Falsos Positivos (Paráfrases Legítimas)
# -----------------------------------------------------------------------------
def test_backtranslation_non_authoritative_for_benign_synonyms(
    backtranslation_verifier: BacktranslationVerifier,
):
    """Variações léxicas legítimas são documentadas como seguras e não quebram o pipeline."""
    original_en = "The train arrived at Dartmoor under heavy rain and ominous thunder."
    # Tradução usando sinônimos poéticos
    translated_pt = "O comboio alcançou Dartmoor sob temporal furioso."

    evidence = backtranslation_verifier.verify(original_en, translated_pt)

    # Não deve haver falha catastrófica nem alerta bloqueante indevido
    assert isinstance(evidence.divergence_notes, list)
    # A evidência registra as diferenças transparentemente
    assert "reconstructed_en" in evidence.metadata


# -----------------------------------------------------------------------------
# 6. Modo Rápido (Bypass) e Desativação
# -----------------------------------------------------------------------------
def test_backtranslation_fast_mode_bypass(
    backtranslation_verifier: BacktranslationVerifier,
):
    """Em modo rápido, a retrotradução é ignorada instantaneamente sem custo computacional."""
    original_en = "Sherlock Holmes examined the footprint with his magnifying glass."
    translated_pt = "Sherlock Holmes examinou a pegada com sua lente de aumento."

    evidence = backtranslation_verifier.verify(
        original_en, translated_pt, fast_mode=True
    )

    assert evidence.metadata.get("bypassed") is True
    assert evidence.metadata.get("fast_mode") is True
    assert evidence.reconstructed_en == ""
    assert not evidence.has_potential_issue


def test_backtranslation_disabled_verifier():
    """Verificador desabilitado via configuração não executa retrotradução."""
    engine = MadladTranslationEngine(backend=MockMadladBackend())
    verifier = BacktranslationVerifier(engine=engine, enabled=False)

    evidence = verifier.verify("Hello world.", "Olá mundo.", fast_mode=False)

    assert evidence.metadata.get("bypassed") is True
    assert not evidence.has_potential_issue
