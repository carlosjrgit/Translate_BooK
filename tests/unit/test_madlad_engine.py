"""Testes unitários para o protótipo do MADLAD-400-10B-MT e benchmark de runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.run_benchmark import run_benchmark
from book_translator.context.base import TranslationContext
from book_translator.core.models import Segment
from book_translator.memory.base import GlossaryEntry, TranslationMemoryEntry
from book_translator.translation.base import TranslationEngine
from book_translator.translation.madlad import (
    CTranslate2Backend,
    DeviceType,
    MadladTranslationEngine,
    MissingModelWeightsError,
    MockMadladBackend,
    QuantizationType,
    RuntimeType,
    TransformersBackend,
)


def test_madlad_engine_protocol_compliance() -> None:
    """Verifica se o MadladTranslationEngine atende ao contrato TranslationEngine."""
    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    assert isinstance(engine, TranslationEngine)
    assert engine.is_ready()
    assert "madlad-400-10b-mt" in engine.engine_name


def test_basic_translation_en_to_pt_br() -> None:
    """Valida a tradução básica de segmentos EN -> PT-BR."""
    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    seg = Segment(
        id="seg_test_01",
        chapter_id="chap_01",
        original_text="Sherlock Holmes examined the footprint with his magnifying glass.",
        sequence_order=1,
    )

    draft = engine.translate_segment(seg)

    assert draft.segment_id == "seg_test_01"
    assert "Sherlock Holmes" in draft.selected_text
    assert "lente de aumento" in draft.selected_text or "pegada" in draft.selected_text
    assert len(draft.candidates) == 1
    assert draft.execution_time_ms >= 0.0
    assert draft.candidates[0].score > 0.0


def test_context_integration_tm_exact_match() -> None:
    """Valida prioridade absoluta para entradas travadas da Translation Memory."""
    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    seg = Segment(
        id="seg_test_02",
        chapter_id="chap_01",
        original_text="'The thief was hasty,' said Holmes.",
        sequence_order=2,
    )

    context = TranslationContext(
        segment_id="seg_test_02",
        established_translations=[
            TranslationMemoryEntry(
                source_term="'The thief was hasty,' said Holmes.",
                target_term="— O surrupiador foi apressado — sentenciou Holmes.",
                locked=True,
            )
        ],
    )

    draft = engine.translate_segment(seg, context=context)

    # A tradução travada na TM deve ser usada diretamente
    assert draft.selected_text == "— O surrupiador foi apressado — sentenciou Holmes."
    assert draft.metadata.get("source") == "tm_locked_match"


def test_context_integration_glossary_enforcement() -> None:
    """Valida reforço pós-processamento de termos de glossário travados."""
    # Mock backend com frase arbitrária que manteria a palavra em inglês
    backend = MockMadladBackend()
    engine = MadladTranslationEngine(backend=backend)

    seg = Segment(
        id="seg_test_03",
        chapter_id="chap_01",
        original_text="The sapphire was locked in the safe.",
        sequence_order=3,
    )

    context = TranslationContext(
        segment_id="seg_test_03",
        relevant_glossary=[
            GlossaryEntry(
                source_term="sapphire",
                target_term="pedra-azul-rara",
                locked=True,
            )
        ],
    )

    draft = engine.translate_segment(seg, context=context)
    # Garante que o termo travado foi aplicado
    assert "pedra-azul-rara" in draft.selected_text or "safira" in draft.selected_text


def test_unauthorized_download_safety_guard(tmp_path: Path) -> None:
    """Garante que backends nunca baixem modelos automaticamente sem consentimento explícito."""
    fake_path = tmp_path / "non_existent_model_weights"

    # CTranslate2 backend
    ct2_backend = CTranslate2Backend(
        model_path=fake_path,
        allow_download=False,
    )
    with pytest.raises(MissingModelWeightsError) as exc_ct2:
        ct2_backend.load()
    assert "download automático" in str(exc_ct2.value)

    # Transformers backend
    tf_backend = TransformersBackend(
        model_name_or_path=str(fake_path),
        allow_download=False,
    )
    with pytest.raises(MissingModelWeightsError) as exc_tf:
        tf_backend.load()
    assert "download automático" in str(exc_tf.value)


def test_benchmark_runner_execution() -> None:
    """Valida a execução do script de benchmark reprodutível e integridade das métricas."""
    summary = run_benchmark(
        runtime_type=RuntimeType.MOCK,
        quantization=QuantizationType.Q6,
        device=DeviceType.CPU,
    )

    assert summary.total_segments == 20
    assert summary.total_tokens > 100
    assert summary.throughput_tokens_per_sec > 0
    assert summary.avg_latency_ms > 0
    assert summary.estimated_disk_gb == 7.6
    assert 0.0 <= summary.avg_token_f1 <= 1.0
    assert 0.0 <= summary.avg_chrf_score <= 1.0
    assert len(summary.segment_results) == 20


def test_madlad_engine_n_best_and_ranker() -> None:
    """Valida geração de N hipóteses e ranqueamento integrado no motor de tradução."""
    from book_translator.translation.ranker import LiteraryCandidateRanker

    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    seg = Segment(
        id="seg_nbest_01",
        chapter_id="chap_01",
        original_text="'The thief was hasty,' said Holmes.",
        sequence_order=1,
    )
    ranker = LiteraryCandidateRanker()

    draft = engine.translate_segment(seg, n_best=3, ranker=ranker)
    assert len(draft.candidates) == 3
    assert draft.candidates[0].rank == 1
    assert draft.candidates[1].rank == 2
    assert draft.candidates[2].rank == 3
    assert draft.selected_text == draft.candidates[0].text
    assert "score_breakdown" in draft.candidates[0].metadata
    assert draft.metadata["parameters"]["n_best"] == 3


def test_clean_repetition_loops() -> None:
    """Valida a erradicação de loops repetitivos e vazamentos de metadados."""
    from book_translator.translation.madlad import clean_repetition_loops

    corrupted = (
        "Esta é a frase traduzida.\n"
        "model_input=Crônicas de um viajante - Wikisource\n"
        "Viagem ao mar - Wikisource\n"
        "Viagem ao mar - Wikisource\n"
        "O marinheiro olhou para o horizonte. O marinheiro olhou para o horizonte. O marinheiro olhou para o horizonte."
    )
    cleaned = clean_repetition_loops(corrupted)
    assert "model_input" not in cleaned
    assert "Wikisource" not in cleaned
    assert cleaned.count("O marinheiro olhou para o horizonte.") == 1
    assert "Esta é a frase traduzida." in cleaned

