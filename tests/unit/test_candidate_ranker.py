"""Testes unitários do ranqueador multicritério LiteraryCandidateRanker."""

from __future__ import annotations

from book_translator.context.base import TranslationContext
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    TranslationMemoryEntry,
)
from book_translator.translation.base import TranslationCandidate
from book_translator.translation.ranker import (
    LiteraryCandidateRanker,
)


def test_candidate_ranker_inspectability_and_all_7_dimensions() -> None:
    """Verifica se o ranker avalia e documenta de forma inspecionável todas as 7 dimensões exigidas."""
    ranker = LiteraryCandidateRanker()

    context = TranslationContext(
        segment_id="seg_001",
        preceding_text=[],
        succeeding_text=[],
        chapter_summary="",
        active_characters=[
            CharacterEntry(id="char_1", project_id="p1", canonical_name="Sherlock Holmes")
        ],
        relevant_glossary=[
            GlossaryEntry(
                id="g1", project_id="p1", source_term="sapphire", target_term="safira", locked=True
            )
        ],
        established_translations=[
            TranslationMemoryEntry(
                id="tm1",
                project_id="p1",
                source_term="Baker Street",
                target_term="Baker Street",
                locked=True,
            )
        ],
    )

    c1 = TranslationCandidate(
        text="— A safira foi encontrada em Baker Street por Sherlock Holmes.", rank=1
    )
    c2 = TranslationCandidate(text='"The sapphire foi encontrada por Holmes na rua."', rank=2)

    ranked = ranker.rank_candidates(
        [c1, c2],
        context=context,
        source_text="The sapphire was found on Baker Street by Sherlock Holmes.",
    )

    assert len(ranked) == 2
    top = ranked[0]
    assert top.text == c1.text
    assert top.rank == 1

    # Inspeciona metadados e os 7 sub-scores
    meta = top.metadata
    assert "score_breakdown" in meta
    breakdown = meta["score_breakdown"]
    assert "fidelity" in breakdown
    assert "naturalness" in breakdown
    assert "terminology" in breakdown
    assert "consistency" in breakdown
    assert "character" in breakdown
    assert "style" in breakdown
    assert "fluency" in breakdown
    assert "final_score" in breakdown
    assert isinstance(meta.get("justifications"), list)

    # O candidato 1 deve ter pontuação significativamente maior que o candidato 2
    assert top.score > ranked[1].score


def test_candidate_ranker_penalizes_glossary_violation() -> None:
    """Candidato que viola termo travado de glossário deve ser superado pelo candidato conforme."""
    ranker = LiteraryCandidateRanker()

    context = TranslationContext(
        segment_id="seg_002",
        preceding_text=[],
        succeeding_text=[],
        chapter_summary="",
        active_characters=[],
        relevant_glossary=[
            GlossaryEntry(
                id="g1",
                project_id="p1",
                source_term="dark stone",
                target_term="pedra sombria",
                locked=True,
            )
        ],
    )

    c_violator = TranslationCandidate(
        text="Ele segurava a dark stone em suas mãos trêmulas.", rank=1
    )
    c_conformant = TranslationCandidate(
        text="Ele segurava a pedra sombria em suas mãos trêmulas.", rank=2
    )

    ranked = ranker.rank_candidates(
        [c_violator, c_conformant],
        context=context,
        source_text="He held the dark stone in his trembling hands.",
    )

    assert ranked[0].text == c_conformant.text
    assert ranked[0].rank == 1
    assert ranked[1].text == c_violator.text
    assert ranked[1].rank == 2

    # Verifica justificativa de penalidade no violador
    violator_meta = ranked[1].metadata
    assert any("terminologia" in j.lower() for j in violator_meta["justifications"])


def test_candidate_ranker_penalizes_ngram_repetition_loops() -> None:
    """Candidato com degeneração de repetição de n-gramas deve receber severa penalidade de naturalidade."""
    ranker = LiteraryCandidateRanker()

    c_loop = TranslationCandidate(text="O homem o homem o homem caminhava pela escuridão.", rank=1)
    c_natural = TranslationCandidate(
        text="O homem caminhava tranquilamente pela escuridão.", rank=2
    )

    ranked = ranker.rank_candidates(
        [c_loop, c_natural],
        source_text="The man walked through the darkness.",
    )

    assert ranked[0].text == c_natural.text
    assert ranked[1].text == c_loop.text
    loop_breakdown = ranked[1].metadata["score_breakdown"]
    assert loop_breakdown["naturalness"] < 0.7


def test_candidate_ranker_penalizes_severe_truncation() -> None:
    """Candidato severamente truncado (< 40% do tamanho do original) deve ser penalizado em fidelidade."""
    ranker = LiteraryCandidateRanker()

    source = "The inspector carefully examined every single detail of the magnificent room before speaking."
    c_truncated = TranslationCandidate(text="O inspetor.", rank=1)
    c_complete = TranslationCandidate(
        text="O inspetor examinou cuidadosamente cada detalhe da magnífica sala antes de falar.",
        rank=2,
    )

    ranked = ranker.rank_candidates([c_truncated, c_complete], source_text=source)
    assert ranked[0].text == c_complete.text
    assert ranked[1].text == c_truncated.text
    assert ranked[1].metadata["score_breakdown"]["fidelity"] < 0.7


def test_candidate_ranker_reproducibility() -> None:
    """O ranqueamento deve ser 100% determinístico e estável entre execuções repetidas."""
    ranker = LiteraryCandidateRanker()

    candidates1 = [
        TranslationCandidate(text="Hipótese alfa com estilo e terminologia.", rank=1),
        TranslationCandidate(text="Hipótese beta com palavras repetidas repetidas.", rank=2),
    ]
    candidates2 = [
        TranslationCandidate(text="Hipótese alfa com estilo e terminologia.", rank=1),
        TranslationCandidate(text="Hipótese beta com palavras repetidas repetidas.", rank=2),
    ]

    r1 = ranker.rank_candidates(candidates1, source_text="Hypothesis test.")
    r2 = ranker.rank_candidates(candidates2, source_text="Hypothesis test.")

    assert [c.text for c in r1] == [c.text for c in r2]
    assert [c.score for c in r1] == [c.score for c in r2]
    assert [c.rank for c in r1] == [c.rank for c in r2]


def test_candidate_ranker_fast_mode_bypass() -> None:
    """No modo rápido ou com 1 candidato, o ranqueador deve agir em bypass sem overhead computacional."""
    fast_ranker = LiteraryCandidateRanker(fast_mode=True)
    candidates = [
        TranslationCandidate(text="Primeira opção rápida.", score=0.9, rank=1),
        TranslationCandidate(text="Segunda opção rápida.", score=0.8, rank=2),
    ]

    ranked = fast_ranker.rank_candidates(candidates)
    assert len(ranked) == 2
    assert ranked[0].metadata["score_breakdown"]["mode"] == "fast_bypass"
