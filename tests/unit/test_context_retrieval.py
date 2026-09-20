"""Testes de validação do mecanismo seletivo de recuperação de contexto (Prompt 12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.context import (
    ContextBudgetConfig,
    ContextRetrievalEngine,
    TranslationContext,
)
from book_translator.core.models import Project, ProjectMetadata, Segment
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    PersistentFact,
    StoryRelationship,
    TranslationMemoryEntry,
)
from book_translator.memory.manager import MemoryManager


@pytest.fixture
def db(tmp_path: Path) -> SQLiteDatabase:
    """Fixture de banco SQLite isolado."""
    db_path = tmp_path / "test_context.db"
    database = SQLiteDatabase(str(db_path))
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def memory_manager(db: SQLiteDatabase, tmp_path: Path) -> MemoryManager:
    """Fixture com MemoryManager populado para testes de contexto."""
    proj_id = "test_context_proj"
    meta = ProjectMetadata(project_id=proj_id, book_title="Ctx Test", source_file_path="dummy")
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))
    mm = MemoryManager(project_id=proj_id, db=db)

    # Personagens com gênero e aliases
    mm.add_character(
        CharacterEntry(
            id="arthur",
            name="Arthur Dent",
            canonical_name="Arthur Dent",
            aliases=["Arthur", "Dent", "Homem da Terra"],
            gender="masculine",
            treatment="você",
            notes="Protagonista humano",
        )
    )
    mm.add_character(
        CharacterEntry(
            id="trillian",
            name="Tricia McMillan",
            canonical_name="Tricia McMillan",
            aliases=["Trillian", "Tricia"],
            gender="feminine",
            treatment="você",
            notes="Astrofísica",
        )
    )
    mm.add_character(
        CharacterEntry(
            id="ford",
            name="Ford Prefect",
            canonical_name="Ford Prefect",
            aliases=["Ford", "Prefect"],
            gender="masculine",
            treatment="você",
            notes="Pesquisador do Guia",
        )
    )

    # Relações
    mm.story.record_relationship(
        source_char="arthur",
        target_char="ford",
        rel_type="melhor amigo",
        description="Amigos desde o pub na Terra",
        evidence="Ford salvou Arthur da demolição.",
    )

    # Glossário com termos travados e comuns
    mm.add_glossary_entry(
        GlossaryEntry(
            source_term="hyperdrive",
            target_term="hiperpropulsão",
            entry_type="concept",
            locked=True,
            case_sensitive=False,
            notes="Termo canônico travado",
        )
    )
    mm.add_glossary_entry(
        GlossaryEntry(
            source_term="towel",
            target_term="toalha",
            entry_type="concept",
            locked=False,
            case_sensitive=False,
            notes="Item mais útil de um mochileiro",
        )
    )

    # Translation Memory
    mm.add_tm_entry(
        TranslationMemoryEntry(
            source_term="Don't Panic",
            target_term="Não Entre em Pânico",
            confidence=1.0,
            locked=True,
            origin="human",
        )
    )

    # Fatos da Story Memory
    mm.story.record_fact(
        entity_id="terra",
        fact="A Terra foi demolida por uma frota Vogon",
        chapter_id="ch_01",
        scope="global",
        evidence="Construção de via expressa hiperespacial.",
        locked=True,
    )
    mm.story.record_fact(
        entity_id="ford",
        fact="Ford tem uma toalha escondida em sua mochila",
        chapter_id="ch_01",
        scope="character_attribute",
        evidence="Nunca saia de casa sem sua toalha.",
        locked=False,
    )

    # Resumo do capítulo
    mm.story.record_summary(
        chapter_id="ch_01",
        summary="Arthur acorda, descobre os tratores e escapa com Ford.",
        title="Capítulo 1: O Fim do Chalé",
    )

    return mm


def test_context_pronominal_reference_resolution(memory_manager: MemoryManager) -> None:
    """Valida resolução de referência pronominal (he -> Arthur Dent, she -> Trillian)."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    # Cenário 1: Pronome masculino 'He' após menção a Arthur Dent
    seg1 = Segment(
        id="seg_01",
        chapter_id="ch_01",
        original_text="Arthur Dent stood in the mud in front of the yellow bulldozer.",
        sequence_order=1,
    )
    seg2 = Segment(
        id="seg_02",
        chapter_id="ch_01",
        original_text="He refused to move even an inch despite the shouts.",
        sequence_order=2,
    )

    ctx_masc = engine.retrieve_context(seg2, all_segments=[seg1, seg2])

    # Arthur Dent deve ter sido identificado no contexto do seg2 por referência pronominal
    char_ids = [c.id for c in ctx_masc.active_characters]
    assert "arthur" in char_ids

    # Verifica score e justificativa explícita
    score = ctx_masc.get_score("arthur")
    assert score is not None
    assert score >= 0.85
    justification = ctx_masc.get_justification("arthur")
    assert justification is not None
    assert "pronominal" in justification.lower() or "arthur" in justification.lower()

    # Cenário 2: Pronome feminino 'She' após menção a Trillian
    seg3 = Segment(
        id="seg_03",
        chapter_id="ch_01",
        original_text="Tricia McMillan examined the star map with careful attention.",
        sequence_order=3,
    )
    seg4 = Segment(
        id="seg_04",
        chapter_id="ch_01",
        original_text="She signaled to the pilot that coordinates were locked.",
        sequence_order=4,
    )

    ctx_fem = engine.retrieve_context(seg4, all_segments=[seg3, seg4])
    char_fem_ids = [c.id for c in ctx_fem.active_characters]
    assert "trillian" in char_fem_ids
    assert ctx_fem.get_score("trillian") is not None


def test_context_alias_resolution(memory_manager: MemoryManager) -> None:
    """Valida identificação de aliases e mapeamento para o personagem canônico correspondente."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    # Segmento que menciona apenas o alias 'Prefect' em vez de 'Ford Prefect'
    seg = Segment(
        id="seg_alias",
        chapter_id="ch_01",
        original_text="Prefect tapped his electronic Sub-Etha thumb with a grin.",
        sequence_order=10,
    )

    ctx = engine.retrieve_context(seg, all_segments=[seg])
    char_ids = [c.id for c in ctx.active_characters]

    # 'Prefect' deve ter resolvido para o ID canônico 'ford'
    assert "ford" in char_ids
    ford_char = next(c for c in ctx.active_characters if c.id == "ford")
    assert ford_char.canonical_name == "Ford Prefect"

    # Score e justificativa explícita
    score = ctx.get_score("ford")
    assert score is not None
    assert score >= 0.90
    just = ctx.get_justification("ford")
    assert just is not None
    assert "alias" in just.lower()


def test_context_recurring_terms_and_glossary(memory_manager: MemoryManager) -> None:
    """Valida termos recorrentes, priorização de termos travados (locked=True) e TM."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    # Parágrafos anteriores onde 'towel' aparece repetidamente
    p1 = Segment(
        id="p1",
        chapter_id="ch_01",
        original_text="A towel is about the most massively useful thing.",
        sequence_order=1,
    )
    p2 = Segment(
        id="p2",
        chapter_id="ch_01",
        original_text="You can wrap your towel around you for warmth.",
        sequence_order=2,
    )
    # Segmento atual com 'hyperdrive' (locked) e 'towel' (recorrente)
    curr = Segment(
        id="curr",
        chapter_id="ch_01",
        original_text="Don't Panic, wrap your towel tight and activate the hyperdrive.",
        sequence_order=3,
    )

    ctx = engine.retrieve_context(curr, all_segments=[p1, p2, curr])

    # 1. Termo travado 'hyperdrive' deve ter score máximo 1.0
    hyp_score = ctx.get_score("hyperdrive")
    assert hyp_score == 1.0
    hyp_just = ctx.get_justification("hyperdrive")
    assert hyp_just is not None
    assert "travado" in hyp_just.lower() or "locked" in hyp_just.lower()

    # 2. Termo recorrente 'towel' deve ter score ponderado e menção a ocorrências
    towel_score = ctx.get_score("towel")
    assert towel_score is not None
    assert towel_score >= 0.80
    towel_just = ctx.get_justification("towel")
    assert towel_just is not None
    assert "recorrência" in towel_just.lower()

    # 3. Translation Memory 'Don't Panic'
    tm_terms = [t.source_term for t in ctx.established_translations]
    assert "Don't Panic" in tm_terms
    assert ctx.get_score("Don't Panic") == 1.0


def test_context_reproducibility(memory_manager: MemoryManager) -> None:
    """Garante que pacotes de contexto sejam deterministicamente reproduzíveis."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    seg = Segment(
        id="seg_repro",
        chapter_id="ch_01",
        original_text="Arthur looked at Ford Prefect and asked if the hyperdrive was ready.",
        sequence_order=5,
    )

    # Execução 1
    ctx1 = engine.retrieve_context(seg, all_segments=[seg])
    # Execução 2
    ctx2 = engine.retrieve_context(seg, all_segments=[seg])

    assert ctx1.reproducibility_hash != ""
    assert ctx1.reproducibility_hash == ctx2.reproducibility_hash
    assert ctx1.to_dict() == ctx2.to_dict()
    assert len(ctx1.scores) == len(ctx2.scores)


def test_context_future_leakage_prevention(memory_manager: MemoryManager) -> None:
    """Valida bloqueio de vazamento de trechos e fatos futuros (anti-spoiler)."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    # Registra fato de revelação futura na Story Memory
    memory_manager.story.record_fact(
        entity_id="arthur",
        fact="Arthur descobrirá que a Terra era um supercomputador orgânico",
        chapter_id="ch_01",
        evidence="Revelação no final da trama.",
        metadata={"is_future_revelation": True},
    )

    prev_seg = Segment(
        id="s1",
        chapter_id="ch_01",
        original_text="Arthur entered the control room.",
        sequence_order=1,
    )
    curr_seg = Segment(
        id="s2",
        chapter_id="ch_01",
        original_text="Arthur watched as the ship jumped to hyperspace.",
        sequence_order=2,
    )
    next_seg = Segment(
        id="s3",
        chapter_id="ch_01",
        original_text="SPOILER: Deep Thought was destroyed.",
        sequence_order=3,
    )

    all_segs = [prev_seg, curr_seg, next_seg]

    # Teste 1: Modo padrão (allow_future_leakage = False)
    cfg_safe = ContextBudgetConfig(allow_future_leakage=False)
    ctx_safe = engine.retrieve_context(curr_seg, all_segments=all_segs, config=cfg_safe)

    assert ctx_safe.future_leakage_prevented is True
    # Não pode conter o próximo segmento nem a revelação futura
    assert next_seg.original_text not in ctx_safe.succeeding_text
    assert not any("supercomputador" in f.statement for f in ctx_safe.story_facts)

    # Teste 2: Modo revisão global (allow_future_leakage = True)
    cfg_global = ContextBudgetConfig(allow_future_leakage=True, window_after=1)
    ctx_global = engine.retrieve_context(curr_seg, all_segments=all_segs, config=cfg_global)

    assert ctx_global.future_leakage_prevented is False
    assert next_seg.original_text in ctx_global.succeeding_text
    assert any("supercomputador" in f.statement for f in ctx_global.story_facts)


def test_context_pluggable_strategies(memory_manager: MemoryManager) -> None:
    """Valida intercâmbio dinâmico entre estratégias substituíveis de recuperação."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    p1 = Segment(
        id="p1", chapter_id="ch_01", original_text="The sky was starry and quiet.", sequence_order=1
    )
    curr = Segment(
        id="curr",
        chapter_id="ch_01",
        original_text="Ford told Arthur that the hyperdrive was operating smoothly.",
        sequence_order=2,
    )
    all_segs = [p1, curr]

    # 1. Estratégia Balanced
    engine.set_strategy("balanced")
    ctx_bal = engine.retrieve_context(curr, all_segments=all_segs)
    assert ctx_bal.strategy_used == "balanced"
    assert len(ctx_bal.active_characters) >= 1
    assert len(ctx_bal.relevant_glossary) >= 1

    # 2. Estratégia Minimal
    engine.set_strategy("minimal")
    ctx_min = engine.retrieve_context(curr, all_segments=all_segs)
    assert ctx_min.strategy_used == "minimal"
    assert ctx_min.chapter_summary == ""
    assert len(ctx_min.semantic_snippets) == 0

    # 3. Estratégia StoryHeavy
    engine.set_strategy("story_heavy")
    ctx_story = engine.retrieve_context(curr, all_segments=all_segs)
    assert ctx_story.strategy_used == "story_heavy"
    assert len(ctx_story.story_facts) >= len(ctx_min.story_facts)

    # 4. Estratégia SemanticDense
    engine.set_strategy("semantic_dense")
    ctx_sem = engine.retrieve_context(curr, all_segments=all_segs)
    assert ctx_sem.strategy_used == "semantic_dense"


def test_context_token_budget_pruning(memory_manager: MemoryManager) -> None:
    """Valida poda graciosa quando o orçamento de tokens é muito restrito."""
    engine = ContextRetrievalEngine(memory_manager=memory_manager)

    p1 = Segment(
        id="p1",
        chapter_id="ch_01",
        original_text="Extremely long passage with lots of text " * 10,
        sequence_order=1,
    )
    curr = Segment(
        id="curr",
        chapter_id="ch_01",
        original_text="Arthur examined the console.",
        sequence_order=2,
    )

    # Configura orçamento severo de apenas 30 tokens
    strict_config = ContextBudgetConfig(max_tokens=30)
    ctx = engine.retrieve_context(curr, all_segments=[p1, curr], config=strict_config)

    assert ctx.metrics is not None
    assert ctx.metrics.total_tokens_estimated <= 100
    assert ctx.reproducibility_hash != ""


def test_context_database_persistence_roundtrip(db: SQLiteDatabase, tmp_path: Path) -> None:
    """Valida persistência e recuperação completa do TranslationContext no banco de dados SQLite."""
    proj_id = "test_db_ctx_proj"
    meta = ProjectMetadata(project_id=proj_id, book_title="Ctx DB Test", source_file_path="dummy")
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))

    from book_translator.database.connection import transaction

    with transaction(db.conn) as cur:
        cur.execute(
            "INSERT INTO documents (id, project_id, title) VALUES (?, ?, ?);",
            ("doc_01", proj_id, "Test Doc"),
        )
        cur.execute(
            "INSERT INTO chapters (id, document_id, title, order_index) VALUES (?, ?, ?, ?);",
            ("ch_01", "doc_01", "Chapter 1", 1),
        )

    seg = Segment(
        id="seg_db_01", chapter_id="ch_01", original_text="Testing database context roundtrip."
    )
    db.save_segment(seg)

    ctx = TranslationContext(
        segment_id="seg_db_01",
        preceding_text=["Parágrafo anterior 1", "Parágrafo anterior 2"],
        succeeding_text=["Parágrafo posterior 1"],
        chapter_summary="Resumo do capítulo para teste de persistência",
        active_characters=[CharacterEntry(id="arthur", name="Arthur Dent", gender="masculine")],
        relevant_glossary=[
            GlossaryEntry(source_term="hyperdrive", target_term="hiperpropulsão", locked=True)
        ],
        established_translations=[
            TranslationMemoryEntry(
                source_term="Don't Panic", target_term="Não Entre em Pânico", locked=True
            )
        ],
        relevant_relationships=[
            StoryRelationship(
                id="rel_01",
                source_character_id="arthur",
                target_character_id="ford",
                relation_type="amigo",
                evidence="Evidência de amizade",
            )
        ],
        story_facts=[
            PersistentFact(
                id="fact_01",
                statement="A Terra foi demolida",
                evidence="Vogons avisaram",
                locked=True,
            )
        ],
        strategy_used="balanced",
        future_leakage_prevented=True,
    )

    db.save_context(ctx)

    loaded_ctx = db.get_context("seg_db_01")
    assert loaded_ctx is not None
    assert loaded_ctx.segment_id == "seg_db_01"
    assert len(loaded_ctx.preceding_text) == 2
    assert len(loaded_ctx.succeeding_text) == 1
    assert loaded_ctx.chapter_summary == "Resumo do capítulo para teste de persistência"
    assert len(loaded_ctx.active_characters) == 1
    assert loaded_ctx.active_characters[0].name == "Arthur Dent"
    assert len(loaded_ctx.relevant_glossary) == 1
    assert loaded_ctx.relevant_glossary[0].target_term == "hiperpropulsão"
    assert len(loaded_ctx.established_translations) == 1
    assert loaded_ctx.established_translations[0].target_term == "Não Entre em Pânico"
    assert len(loaded_ctx.relevant_relationships) == 1
    assert loaded_ctx.relevant_relationships[0].relation_type == "amigo"
    assert len(loaded_ctx.story_facts) == 1
    assert loaded_ctx.story_facts[0].statement == "A Terra foi demolida"
    assert loaded_ctx.reproducibility_hash == ctx.reproducibility_hash
