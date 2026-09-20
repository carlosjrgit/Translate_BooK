"""Teste de integração e auditoria pré-tradução para o Checkpoint 2 (Prompt 13).

Valida todo o pipeline pré-tradução de ponta a ponta com corpus sintético:
1. Ingestão e representação rica de documentos (Capítulos, Parágrafos, Segmentos).
2. Análise global e NER (Extração de entidades, personagens, aliases, organizações, locais).
3. Prevenção de falsos positivos (advérbios e marcadores de transição não viram personagens).
4. Integridade de IDs, rastreabilidade, evidências e cálculo de confiança.
5. População idempotente de Style Bible, Story Memory e Entidades (sem bloat no SQLite).
6. Recuperação de Contexto com orquestração dos 9 eixos, métricas, scores e prevenção estrita de spoiler.
"""

from __future__ import annotations

import time
from pathlib import Path

from book_translator.analysis.book_analyzer import BookAnalyzer
from book_translator.context.base import ContextBudgetConfig
from book_translator.context.engine import ContextRetrievalEngine
from book_translator.context.strategies import BalancedRetrievalStrategy
from book_translator.core.models import (
    Chapter,
    Document,
    DocumentMetadata,
    Paragraph,
    Project,
    ProjectMetadata,
    Segment,
)
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.memory.base import (
    GlossaryEntry,
    PersistentFact,
    StoryRelationship,
    TranslationMemoryEntry,
)


def _build_synthetic_document(doc_id: str = "doc_blackwood") -> Document:
    """Gera um documento sintético multi-capítulo contendo diálogos, aliases e termos-chave."""
    doc = Document(
        id=doc_id,
        title="The Mystery of the Blackwood Manor",
        author="Arthur C. Doyle",
        source_format="txt",
        metadata=DocumentMetadata(
            title="The Mystery of the Blackwood Manor",
            author="Arthur C. Doyle",
            language="en",
        ),
    )

    # Capítulo 1: The Baker Street Consultation
    ch1 = Chapter(id="chap_0001", title="The Baker Street Consultation", order=1)
    p1 = Paragraph(
        id="p1_1",
        chapter_id="chap_0001",
        reading_order=1,
        raw_text="Dr. John Watson sat near the fireplace at 221B Baker Street, listening carefully.",
    )
    s1 = Segment(
        id="seg_1_1",
        chapter_id="chap_0001",
        paragraph_id="p1_1",
        sequence_order=1,
        original_text="Dr. John Watson sat near the fireplace at 221B Baker Street, listening carefully.",
    )
    ch1.segments.append(s1)

    p2 = Paragraph(
        id="p1_2",
        chapter_id="chap_0001",
        reading_order=2,
        raw_text="Sherlock Holmes examined the footprint with his magnifying glass. 'The thief was hasty,' said Holmes.",
    )
    s2 = Segment(
        id="seg_1_2",
        chapter_id="chap_0001",
        paragraph_id="p1_2",
        sequence_order=2,
        original_text="Sherlock Holmes examined the footprint with his magnifying glass.",
    )
    s3 = Segment(
        id="seg_1_3",
        chapter_id="chap_0001",
        paragraph_id="p1_2",
        sequence_order=3,
        original_text="'The thief was hasty,' said Holmes.",
    )
    ch1.segments.extend([s2, s3])

    p3 = Paragraph(
        id="p1_3",
        chapter_id="chap_0001",
        reading_order=3,
        raw_text="Suddenly Watson stood up. 'Do you believe Scotland Yard will arrive in time, Holmes?' asked Watson.",
    )
    s4 = Segment(
        id="seg_1_4",
        chapter_id="chap_0001",
        paragraph_id="p1_3",
        sequence_order=4,
        original_text="Suddenly Watson stood up.",
    )
    s5 = Segment(
        id="seg_1_5",
        chapter_id="chap_0001",
        paragraph_id="p1_3",
        sequence_order=5,
        original_text="'Do you believe Scotland Yard will arrive in time, Holmes?' asked Watson.",
    )
    ch1.segments.extend([s4, s5])

    p4 = Paragraph(
        id="p1_4",
        chapter_id="chap_0001",
        reading_order=4,
        raw_text="Inspector Lestrade had sent an urgent telegram regarding the Blackwood sapphire.",
    )
    s6 = Segment(
        id="seg_1_6",
        chapter_id="chap_0001",
        paragraph_id="p1_4",
        sequence_order=6,
        original_text="Inspector Lestrade had sent an urgent telegram regarding the Blackwood sapphire.",
    )
    ch1.segments.append(s6)

    ch1.paragraphs.extend([p1, p2, p3, p4])
    doc.chapters.append(ch1)

    # Capítulo 2: The Journey to Blackwood Manor
    ch2 = Chapter(id="chap_0002", title="The Journey to Blackwood Manor", order=2)
    p5 = Paragraph(
        id="p2_1",
        chapter_id="chap_0002",
        reading_order=1,
        raw_text="The train arrived at Dartmoor under heavy rain and ominous thunder.",
    )
    s7 = Segment(
        id="seg_2_1",
        chapter_id="chap_0002",
        paragraph_id="p2_1",
        sequence_order=1,
        original_text="The train arrived at Dartmoor under heavy rain and ominous thunder.",
    )
    ch2.segments.append(s7)

    p6 = Paragraph(
        id="p2_2",
        chapter_id="chap_0002",
        reading_order=2,
        raw_text="Sherlock Holmes and Watson met Lady Margaret at the grand entrance. She was trembling.",
    )
    s8 = Segment(
        id="seg_2_2",
        chapter_id="chap_0002",
        paragraph_id="p2_2",
        sequence_order=2,
        original_text="Sherlock Holmes and Watson met Lady Margaret at the grand entrance.",
    )
    s9 = Segment(
        id="seg_2_3",
        chapter_id="chap_0002",
        paragraph_id="p2_2",
        sequence_order=3,
        original_text="She was trembling.",
    )
    ch2.segments.extend([s8, s9])

    p7 = Paragraph(
        id="p2_3",
        chapter_id="chap_0002",
        reading_order=3,
        raw_text="'The sapphire vanished at midnight from the safe,' whispered Lady Margaret. Meanwhile Holmes inspected the lock.",
    )
    s10 = Segment(
        id="seg_2_4",
        chapter_id="chap_0002",
        paragraph_id="p2_3",
        sequence_order=4,
        original_text="'The sapphire vanished at midnight from the safe,' whispered Lady Margaret.",
    )
    s11 = Segment(
        id="seg_2_5",
        chapter_id="chap_0002",
        paragraph_id="p2_3",
        sequence_order=5,
        original_text="Meanwhile Holmes inspected the lock.",
    )
    ch2.segments.extend([s10, s11])

    ch2.paragraphs.extend([p5, p6, p7])
    doc.chapters.append(ch2)

    return doc


def test_full_pre_translation_pipeline_audit(tmp_path: Path) -> None:
    """Executa e audita todo o pipeline pré-tradução conforme critérios do Checkpoint 2."""
    db_path = tmp_path / "audit_checkpoint_2.db"
    db = SQLiteDatabase(db_path)
    db.initialize()

    project_id = "proj_audit_001"
    project = Project(
        metadata=ProjectMetadata(
            project_id=project_id,
            book_title="The Mystery of the Blackwood Manor",
            source_file_path=str(tmp_path / "blackwood.txt"),
            source_language="en",
            target_language="pt-BR",
        ),
        project_dir=tmp_path,
        db_path=db_path,
    )
    db.save_project(project)

    doc = _build_synthetic_document()
    db.save_document(doc, project_id)

    # 1. Verificação de Perda de Informação
    all_segs = db.get_pending_segments(project_id)
    assert len(all_segs) == 11, f"Esperado 11 segmentos persistidos, encontrado {len(all_segs)}"

    # 2. Configuração de Memória Léxica (Glossário e TM)
    db.save_glossary_entry(
        project_id,
        GlossaryEntry(
            source_term="sapphire",
            target_term="safira",
            entry_type="concept",
            locked=True,
            notes="Joia central da trama",
        ),
    )
    db.save_glossary_entry(
        project_id,
        GlossaryEntry(
            source_term="consulting detective",
            target_term="detetive consultor",
            entry_type="concept",
            locked=True,
        ),
    )
    db.save_tm_entry(
        project_id,
        TranslationMemoryEntry(
            source_term="'The thief was hasty,' said Holmes.",
            target_term="'O ladrão foi precipitado,' disse Holmes.",
            entry_type="exact_sentence",
            locked=True,
        ),
    )

    # 3. Execução da Análise Global e NER
    analyzer = BookAnalyzer()
    t0 = time.perf_counter()
    report = analyzer.analyze(doc)
    analysis_duration = time.perf_counter() - t0

    assert analysis_duration < 2.0, f"Análise muito lenta: {analysis_duration:.2f}s"

    # 4. Auditoria de Falsos Positivos de Entidades
    entity_names = {ent.canonical_name for ent in report.entities}
    # Advérbios e conectores NÃO devem ser identificados como personagens!
    assert "Suddenly" not in entity_names, (
        "Falso positivo: 'Suddenly' foi classificado como entidade!"
    )
    assert "Meanwhile" not in entity_names, (
        "Falso positivo: 'Meanwhile' foi classificado como entidade!"
    )
    assert "Suddenly Watson" not in entity_names, (
        "Falso positivo composto: 'Suddenly Watson' detectado!"
    )

    # Personagens e organizações esperados DEVEM estar presentes
    assert "John Watson" in entity_names or "Dr. John Watson" in entity_names
    assert "Sherlock Holmes" in entity_names
    assert "Scotland Yard" in entity_names

    # 5. População e Idempotência no Banco de Dados
    analyzer.populate_project_memory(report, db, project_id, doc)

    # Adiciona fatos manuais e relacionamentos
    db.save_story_relationship(
        project_id,
        StoryRelationship(
            id="rel_holmes_watson",
            source_character_id="char_holmes",
            target_character_id="char_watson",
            relation_type="colleague",
            description="Parceiro e biógrafo de Holmes",
            confidence=0.95,
        ),
    )
    db.save_story_fact(
        project_id,
        PersistentFact(
            id="fact_sapphire",
            category="plot_fact",
            statement="A safira de Blackwood foi roubada à meia-noite.",
            confidence=1.0,
            locked=True,
        ),
    )

    # Verifica contagens antes de re-popular
    chars_before = len(db.get_characters(project_id))
    entities_before = len(db.get_entities(project_id))

    # Re-executa populate_project_memory para testar idempotência e ausência de bloat
    analyzer.populate_project_memory(report, db, project_id, doc)

    chars_after = len(db.get_characters(project_id))
    entities_after = len(db.get_entities(project_id))

    assert chars_before == chars_after, (
        f"Bloat detectado em characters: {chars_before} -> {chars_after}"
    )
    assert entities_before == entities_after, (
        f"Bloat detectado em entities: {entities_before} -> {entities_after}"
    )

    # 6. Auditoria de Style Bible e Evidências
    sb = db.get_style_bible(project_id)
    assert sb is not None
    assert sb.narrative_person in ("terceira pessoa", "3ª pessoa")
    assert sb.formality_level != ""

    # 7. Auditoria de Recuperação de Contexto (Context Retrieval)
    from book_translator.memory.manager import MemoryManager

    mm = MemoryManager(project_id=project_id, db=db)
    engine = ContextRetrievalEngine(
        memory_manager=mm,
        db=db,
        strategy=BalancedRetrievalStrategy(),
        config=ContextBudgetConfig(max_tokens=600, allow_future_leakage=False),
    )

    # Teste para o Segmento 4 do Capítulo 1 ("Suddenly Watson stood up.")
    target_seg = next(s for s in all_segs if s.id == "seg_1_4")
    ctx_pkg = engine.retrieve_context(
        segment=target_seg,
        all_segments=all_segs,
    )

    # Validações estritas do Pacote de Contexto:
    # A) Prevenção de vazamento / spoilers futuros
    assert ctx_pkg.future_leakage_prevented is True
    assert len(ctx_pkg.succeeding_text) == 0, "Vazamento detectado: texto futuro não foi omitido!"

    # NENHUM elemento do capítulo 2 deve vazar no contexto do capítulo 1!
    context_str = str(ctx_pkg.to_dict()).lower()
    assert "dartmoor" not in context_str, (
        "Vazamento crítico: 'Dartmoor' (Cap 2) vazou para o Cap 1!"
    )
    assert "lady margaret" not in context_str, (
        "Vazamento crítico: 'Lady Margaret' (Cap 2) vazou para o Cap 1!"
    )

    # B) Parágrafos e sentenças anteriores presentes
    assert len(ctx_pkg.preceding_text) >= 1
    assert any("Sherlock Holmes" in p for p in ctx_pkg.preceding_text)

    # C) Personagens ativos identificados com evidência e score
    char_names_present = {c.name for c in ctx_pkg.active_characters}
    assert any("Watson" in name for name in char_names_present), (
        f"Watson não encontrado em {char_names_present}"
    )

    # Valida segmento com diálogo duplo (seg_1_5: Watson pergunta para Holmes)
    target_seg_5 = next(s for s in all_segs if s.id == "seg_1_5")
    ctx_pkg_5 = engine.retrieve_context(
        segment=target_seg_5,
        all_segments=all_segs,
    )
    char_names_5 = {c.name for c in ctx_pkg_5.active_characters}
    assert any("Watson" in name for name in char_names_5), (
        f"Watson não encontrado em {char_names_5}"
    )
    assert any("Holmes" in name for name in char_names_5), (
        f"Holmes não encontrado em {char_names_5}"
    )

    # D) Justificativas e scores presentes para todos os componentes
    assert len(ctx_pkg.scores) > 0
    for item in ctx_pkg.scores:
        assert 0.0 <= item.score <= 1.0
        assert len(item.justification) > 5

    # E) Reprodutibilidade estrita
    assert len(ctx_pkg.reproducibility_hash) == 16
    ctx_pkg_recheck = engine.retrieve_context(
        segment=target_seg,
        all_segments=all_segs,
    )
    assert ctx_pkg.reproducibility_hash == ctx_pkg_recheck.reproducibility_hash, (
        "Hash de reprodutibilidade divergiu!"
    )

    # 8. Teste para Segmento com Termo Travado de Glossário (Capítulo 2, Seg 10: "The sapphire vanished...")
    seg_sapphire = next(s for s in all_segs if s.id == "seg_2_4")
    ctx_sapphire = engine.retrieve_context(
        segment=seg_sapphire,
        all_segments=all_segs,
    )
    glossary_terms = {g.source_term for g in ctx_sapphire.relevant_glossary}
    assert "sapphire" in glossary_terms, "Glossário não recuperou termo travado 'sapphire'!"
    sapphire_score = next(
        item
        for item in ctx_sapphire.scores
        if item.category == "glossary" and item.item_id == "sapphire"
    )
    assert sapphire_score.score == 1.0, "Termo travado do glossário deve ter score máximo 1.0!"

    # 9. Verificação de Persistência do Contexto no SQLite
    db.save_context(ctx_pkg)
    saved_ctx = db.get_context(target_seg.id)
    assert saved_ctx is not None
    assert saved_ctx.reproducibility_hash == ctx_pkg.reproducibility_hash
    assert saved_ctx.future_leakage_prevented is True
    assert len(saved_ctx.scores) == len(ctx_pkg.scores)
