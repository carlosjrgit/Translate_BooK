"""Testes unitários completos para StoryMemory (Prompt 11)."""

from __future__ import annotations

from book_translator.memory import MemoryManager
from book_translator.memory.base import (
    StoryMemory,
)


def test_story_memory_recording_all_structures_with_evidence() -> None:
    """Verifica registro de resumo, estado, relações, eventos, cronologia, fatos e referências cruzadas com evidência."""
    sm = StoryMemory(project_id="test_book")

    # 1. Resumo por capítulo/seção
    sm.record_summary(
        chapter_id="ch_01",
        summary="A esquadra Vogon chega à Terra para construir a via expressa.",
        section_id="sec_01",
        key_developments=["Naves pairam sobre as cidades", "Prostetnic Vogon Jeltz fala"],
        open_questions=["Como Arthur vai escapar?"],
    )
    summary = sm.get_chapter_summary("ch_01")
    assert summary is not None
    assert "Vogon" in summary.summary
    assert len(summary.key_developments) == 2

    # 2. Estado de personagens
    sm.record_character_state(
        character_id="arthur",
        chapter_id="ch_01",
        state="alive",
        location="casa de campo",
        physical_condition="ferido",
        emotional_state="desesperado",
        evidence="Arthur deitou-se na lama na frente do trator.",
        confidence=1.0,
        is_inferred=False,
    )
    state = sm.get_character_state("arthur", "ch_01")
    assert state is not None
    assert state.state == "alive"
    assert state.location == "casa de campo"
    assert state.evidence == "Arthur deitou-se na lama na frente do trator."
    assert state.is_inferred is False

    # 3. Relações entre personagens
    sm.record_relationship(
        source_char="arthur",
        target_char="ford",
        rel_type="aliado",
        description="Ford resgata Arthur da destruição iminente",
        chapter_id="ch_01",
        evidence="Ford puxou Arthur pelo braço dizendo: temos que ir agora!",
        confidence=0.9,
        is_inferred=False,
    )
    rels = sm.get_character_relationships("arthur")
    assert len(rels) == 1
    assert rels[0].target_character_id == "ford"
    assert rels[0].evidence == "Ford puxou Arthur pelo braço dizendo: temos que ir agora!"
    assert rels[0].is_inferred is False

    # 4. Eventos e Cronologia
    sm.record_event(
        chapter_id="ch_01",
        order_index=1,
        title="Destruição da Terra",
        description="Feixe desintegrador destrói o planeta",
        impact="Catastrófico",
        characters=["arthur", "ford", "jeltz"],
        evidence="O feixe atingiu o solo e o planeta explodiu em silêncio.",
        is_inferred=False,
    )
    events = sm.get_chronology(chapter_id="ch_01")
    assert len(events) == 1
    assert events[0].title == "Destruição da Terra"
    assert events[0].evidence == "O feixe atingiu o solo e o planeta explodiu em silêncio."

    # 5. Fatos persistentes
    sm.record_fact(
        entity_id="terra",
        fact="A Terra foi destruída para abrir caminho para uma via hiperespacial",
        chapter_id="ch_01",
        scope="global",
        evidence="Anúncio oficial transmitido em ondas curtas pelo capitão Vogon.",
        is_inferred=False,
    )
    facts = sm.get_persistent_facts("terra")
    assert len(facts) == 1
    assert "via hiperespacial" in facts[0].fact
    assert facts[0].is_inferred is False

    # 6. Referências cruzadas
    sm.record_cross_reference(
        source_chapter="ch_01",
        target_chapter="ch_03",
        ref_type="causalidade",
        description="A destruição da Terra motiva a busca por Magrathea",
        evidence="Se a Terra se foi, precisamos saber quem a encomendou.",
        is_inferred=True,
    )
    xrefs = sm.get_cross_references(chapter_id="ch_01")
    assert len(xrefs) == 1
    assert xrefs[0].ref_type == "causalidade"
    assert xrefs[0].is_inferred is True


def test_story_memory_explicit_vs_inferred_filtering() -> None:
    """Verifica separação clara e consultas filtradas entre fatos explícitos e inferências."""
    sm = StoryMemory(project_id="test_filter")

    # Fato explícito
    sm.record_fact(
        entity_id="arthur",
        fact="Arthur é um humano nascido na Inglaterra",
        chapter_id="ch_01",
        evidence="Passaporte britânico mencionado no texto.",
        is_inferred=False,
        source_type="explicit",
    )
    # Fato inferido
    sm.record_fact(
        entity_id="arthur",
        fact="Arthur aparenta ter cerca de trinta e poucos anos",
        chapter_id="ch_01",
        evidence="Descrição de suas roupas e carreira profissional.",
        is_inferred=True,
        source_type="inference",
    )

    explicit_facts = sm.get_persistent_facts("arthur", explicit_only=True)
    inferred_facts = sm.get_persistent_facts("arthur", inferred_only=True)

    assert len(explicit_facts) == 1
    assert explicit_facts[0].fact == "Arthur é um humano nascido na Inglaterra"

    assert len(inferred_facts) == 1
    assert "trinta" in inferred_facts[0].fact

    # Relações explícitas vs inferidas
    sm.record_relationship(
        source_char="arthur",
        target_char="ford",
        rel_type="amigo",
        description="Amigos",
        chapter_id="ch_01",
        evidence="Eles se abraçaram.",
        is_inferred=False,
    )
    sm.record_relationship(
        source_char="arthur",
        target_char="trillian",
        rel_type="crush",
        description="Arthur parece ter interesse romântico nela",
        chapter_id="ch_01",
        evidence="Ele olhava para ela timidamente em Islington.",
        is_inferred=True,
    )

    explicit_rels = sm.get_character_relationships("arthur", explicit_only=True)
    inferred_rels = sm.get_character_relationships("arthur", inferred_only=True)

    assert len(explicit_rels) == 1
    assert explicit_rels[0].target_character_id == "ford"

    assert len(inferred_rels) == 1
    assert inferred_rels[0].target_character_id == "trillian"


def test_scene_context_snapshot_prioritizes_explicit_and_avoids_giant_prompt() -> None:
    """Verifica que o snapshot de contexto é cirúrgico e prioriza fatos explícitos (adequado a MADLAD-400)."""
    sm = StoryMemory(project_id="test_snapshot")

    # Registra vários fatos: alguns explícitos, alguns inferidos
    for i in range(5):
        sm.record_fact(
            entity_id="arthur",
            fact=f"Fato explícito {i}",
            chapter_id="ch_01",
            evidence=f"Evidência explícita {i}",
            is_inferred=False,
        )
    for i in range(5):
        sm.record_fact(
            entity_id="arthur",
            fact=f"Inferência {i}",
            chapter_id="ch_01",
            evidence=f"Evidência inferida {i}",
            is_inferred=True,
        )

    sm.record_character_state(
        character_id="arthur",
        chapter_id="ch_01",
        state="alive",
        location="nave",
        evidence="Ele está no compartimento de carga.",
        is_inferred=False,
    )

    # Solicita snapshot limitado a 3 fatos
    snapshot = sm.get_scene_context_snapshot(
        chapter_id="ch_01",
        unit_id="p_05",
        character_ids=["arthur"],
        max_facts=3,
    )

    assert len(snapshot.active_facts) == 3
    # Todos os 3 selecionados devem ser explícitos pois explícitos têm prioridade
    for fact in snapshot.active_facts:
        assert fact.is_inferred is False
        assert "explícito" in fact.fact

    # Snapshot registra a contagem de explícitos e inferidos
    assert snapshot.explicit_items_count >= 3
    assert snapshot.inferred_items_count >= 0


def test_story_memory_fact_compliance_validation() -> None:
    """Verifica validação de conformidade de fatos persistentes no texto traduzido."""
    sm = StoryMemory(project_id="test_qa_facts")
    sm.record_fact(
        entity_id="arthur",
        fact="Arthur nunca viajou para fora da Inglaterra",
        chapter_id="ch_01",
        evidence="Texto cap 1: Nunca antes saíra do país.",
        is_inferred=False,
    )

    # Texto que viola o fato de 'nunca viajou'
    anomalies = sm.validate_facts_compliance(
        "Arthur lembrou-se de quando viajou para o Japão e visitou Tóquio."
    )
    assert len(anomalies) > 0
    assert any(a.anomaly_type == "fact_contradiction" for a in anomalies)


def test_story_memory_contradiction_detection() -> None:
    """Testa detecção programática de contradições em StoryMemory."""
    sm = StoryMemory(project_id="test_contradictions")

    # 1. Personagem morto agindo em momento posterior sem flashback
    sm.record_character_state(
        character_id="boromir",
        chapter_id="ch_01",
        order_index=1,
        state="dead",
        evidence="Boromir foi trespassado por flechas e deu seu último suspiro.",
        is_inferred=False,
    )
    sm.record_character_state(
        character_id="boromir",
        chapter_id="ch_02",
        order_index=2,
        state="alive",
        evidence="Boromir correu e golpeou o orc com sua espada.",
        is_inferred=False,
    )

    # 2. Personagem em dois locais conflitantes no mesmo instante
    sm.record_character_state(
        character_id="gandalf",
        chapter_id="ch_01",
        order_index=5,
        state="alive",
        location="Moria profunda",
        evidence="Gandalf caiu no abismo.",
    )
    sm.record_character_state(
        character_id="gandalf",
        chapter_id="ch_01",
        order_index=5,
        state="alive",
        location="Condado tranquilo",
        evidence="Gandalf fumava cachimbo em Bolsão.",
    )

    # 3. Relações mutuamente exclusivas ativas simultaneamente
    sm.record_relationship(
        source_char="romeu",
        target_char="julieta",
        rel_type="casados",
        description="Casados secretamente",
        chapter_id="ch_02",
        evidence="Frei Lourenço realizou o casamento.",
    )
    sm.record_relationship(
        source_char="romeu",
        target_char="julieta",
        rel_type="inimigos mortais",
        description="Ódio absoluto declarado",
        chapter_id="ch_02",
        evidence="Eles prometeram destruir um ao outro.",
    )

    anomalies = sm.detect_contradictions()
    assert len(anomalies) >= 3

    # Verifica anomalia de estado após morte
    dead_anomaly = next(
        (a for a in anomalies if a.anomaly_type == "character_state_contradiction"), None
    )
    assert dead_anomaly is not None
    assert "boromir" in dead_anomaly.entity_id

    # Verifica anomalia de localização simultânea
    loc_anomaly = next(
        (a for a in anomalies if a.anomaly_type == "character_location_contradiction"), None
    )
    assert loc_anomaly is not None
    assert "gandalf" in loc_anomaly.entity_id

    # Verifica relação excludente
    rel_anomaly = next(
        (a for a in anomalies if a.anomaly_type == "relationship_contradiction"), None
    )
    assert rel_anomaly is not None
    assert "romeu" in rel_anomaly.entity_id or "julieta" in rel_anomaly.entity_id


def test_memory_manager_unified_conflict_detection_includes_story_and_style() -> None:
    """Verifica que MemoryManager.detect_all_conflicts() inclui contradições da Style Bible e da Story Memory."""
    mm = MemoryManager(project_id="unified_test")

    # Contradição na Style Bible
    mm.style_bible.narrator = "primeira pessoa"
    mm.style_bible.narrative_person = "3a"

    # Contradição na Story Memory
    mm.story.record_character_state(
        character_id="ned_stark",
        chapter_id="ch_01",
        order_index=1,
        state="dead",
        evidence="Ned foi decapitado no cadafalso.",
    )
    mm.story.record_character_state(
        character_id="ned_stark",
        chapter_id="ch_02",
        order_index=2,
        state="alive",
        evidence="Ned cavalgou em direção a Porto Real.",
    )

    conflicts = mm.detect_all_conflicts()

    assert any(c.memory_type == "style_bible" for c in conflicts)
    assert any(c.memory_type == "story_memory" and "ned_stark" in c.term_or_name for c in conflicts)
