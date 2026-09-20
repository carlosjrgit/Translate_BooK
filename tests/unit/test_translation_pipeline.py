"""Testes unitários e de integração do pipeline de tradução incremental, cache e checkpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.context.engine import ContextRetrievalEngine
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
from book_translator.memory.base import GlossaryEntry
from book_translator.translation.madlad import (
    MadladTranslationEngine,
    RuntimeType,
)
from book_translator.translation.pipeline import (
    CancellationToken,
    TranslationPipeline,
    TranslationPipelineConfig,
)
from book_translator.translation.ranker import LiteraryCandidateRanker


@pytest.fixture
def test_project(tmp_path: Path) -> tuple[SQLiteDatabase, str]:
    """Cria um projeto sintético estruturado com 2 capítulos e 4 segmentos para validação do pipeline."""
    db_file = tmp_path / "pipeline_test.db"
    db = SQLiteDatabase(db_file)
    db.initialize()

    proj_id = "pipeline_proj_01"
    doc_id = "doc_proj_01"

    # Salva projeto e metadados
    proj = Project(
        metadata=ProjectMetadata(
            project_id=proj_id,
            book_title="The Sapphire Mystery",
            source_file_path=str(tmp_path / "source.txt"),
        ),
        project_dir=tmp_path,
        db_path=db_file,
    )
    db.save_project(proj)

    # Cria capítulos e documento
    chap1 = Chapter(id="chap_01", title="Chapter 1: The Theft", order=1)
    chap2 = Chapter(id="chap_02", title="Chapter 2: The Investigation", order=2)
    doc = Document(
        id=doc_id,
        metadata=DocumentMetadata(title="The Sapphire Mystery", author="Arthur C. Doyle"),
        chapters=[chap1, chap2],
    )
    db.save_document(doc, project_id=proj_id)

    # Cria parágrafos e segmentos
    # Segmento 1 (contém 'sapphire')
    s1 = Segment(
        id="seg_01",
        chapter_id="chap_01",
        original_text="The sapphire vanished at midnight from the safe.",
        sequence_order=1,
    )
    # Segmento 2 (diálogo com Holmes)
    s2 = Segment(
        id="seg_02",
        chapter_id="chap_01",
        original_text="'The thief was hasty,' said Holmes.",
        sequence_order=2,
    )
    # Segmento 3 (sem sapphire)
    s3 = Segment(
        id="seg_03",
        chapter_id="chap_02",
        original_text="Sherlock Holmes examined the footprint with his magnifying glass.",
        sequence_order=1,
    )
    # Segmento 4 (contém 'sapphire')
    s4 = Segment(
        id="seg_04",
        chapter_id="chap_02",
        original_text="Inspector Lestrade had sent an urgent telegram regarding the blackwood sapphire.",
        sequence_order=2,
    )

    for s in [s1, s2, s3, s4]:
        db.save_segment(s)

    # Cadastra termo no glossário
    db.save_glossary_entry(
        proj_id,
        GlossaryEntry(
            id="g_sapphire",
            project_id=proj_id,
            source_term="sapphire",
            target_term="safira",
            locked=True,
        ),
    )

    return db, proj_id


def test_translation_pipeline_end_to_end_and_persistence(
    test_project: tuple[SQLiteDatabase, str],
) -> None:
    """Valida tradução completa de documento, persistência auditável e imutabilidade do original."""
    db, project_id = test_project

    from book_translator.memory.manager import MemoryManager

    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    mem_mgr = MemoryManager(db=db, project_id=project_id)
    context_engine = ContextRetrievalEngine(memory_manager=mem_mgr, db=db)
    ranker = LiteraryCandidateRanker()
    config = TranslationPipelineConfig(n_best=2, checkpoint_frequency=1)

    pipeline = TranslationPipeline(
        db=db,
        translation_engine=engine,
        context_engine=context_engine,
        ranker=ranker,
        config=config,
    )

    result = pipeline.translate_project(project_id)

    assert result.status == "completed"
    assert result.total_segments == 4
    assert result.completed_segments == 4
    assert result.freshly_translated == 4
    assert result.cached_segments == 0

    # 1. Verifica se todos os segmentos foram atualizados e o texto original NUNCA foi sobrescrito
    segs = db.get_segments_by_chapter("chap_01") + db.get_segments_by_chapter("chap_02")
    for s in segs:
        assert s.status == SegmentStatus.TRANSLATED
        assert len(s.translated_text) > 0
        # O texto original deve permanecer intocado
        assert s.original_text in [
            "The sapphire vanished at midnight from the safe.",
            "'The thief was hasty,' said Holmes.",
            "Sherlock Holmes examined the footprint with his magnifying glass.",
            "Inspector Lestrade had sent an urgent telegram regarding the blackwood sapphire.",
        ]

    # 2. Verifica a persistência auditável na tabela de traduções
    trans_s1 = db.get_translations("seg_01")
    assert len(trans_s1) == 2  # n_best = 2
    assert trans_s1[0]["candidate_rank"] == 1
    assert trans_s1[0]["is_selected"] is True
    assert "safira" in trans_s1[0]["translated_text"].lower()

    # Metadados de auditoria completos
    meta_s1 = trans_s1[0]["metadata"]
    assert meta_s1["source_text"] == "The sapphire vanished at midnight from the safe."
    assert "model_name" in meta_s1
    assert "runtime" in meta_s1
    assert "parameters" in meta_s1
    assert "context_used" in meta_s1
    assert "version" in meta_s1
    assert "score_breakdown" in meta_s1

    # 3. Verifica se o checkpoint final está marcado como completed
    chk = db.get_latest_checkpoint(project_id)
    assert chk is not None
    assert chk.status == "completed"
    assert chk.completed_segments == 4


def test_translation_pipeline_cache_hit_on_second_run(
    test_project: tuple[SQLiteDatabase, str],
) -> None:
    """Execuções subsequentes devem reutilizar o cache sem invocar inferência linguística redundante."""
    db, project_id = test_project

    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    pipeline = TranslationPipeline(db=db, translation_engine=engine)

    # Primeira execução: tradução nova
    res1 = pipeline.translate_project(project_id)
    assert res1.freshly_translated == 4
    assert res1.cached_segments == 0

    # Segunda execução: cache hit em 100% dos segmentos
    res2 = pipeline.translate_project(project_id)
    assert res2.status == "completed"
    assert res2.freshly_translated == 0
    assert res2.cached_segments == 4


def test_translation_pipeline_selective_glossary_invalidation(
    test_project: tuple[SQLiteDatabase, str],
) -> None:
    """Mudança em termo do glossário deve invalidar apenas os segmentos que contêm o termo."""
    db, project_id = test_project

    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    pipeline = TranslationPipeline(db=db, translation_engine=engine)

    # 1. Primeira tradução completa
    pipeline.translate_project(project_id)

    # 2. Invalida cirurgicamente o termo 'sapphire'
    # Os segmentos que contêm 'sapphire' são seg_01 e seg_04. Os outros seg_02 e seg_03 NÃO contêm.
    invalidated_ids = pipeline.invalidate_glossary_term(project_id, "sapphire")
    assert "seg_01" in invalidated_ids
    assert "seg_04" in invalidated_ids
    assert "seg_02" not in invalidated_ids
    assert "seg_03" not in invalidated_ids

    # 3. Verifica estado no banco: seg_01 e seg_04 revertidos para pending
    s1 = db.get_segment("seg_01")
    s2 = db.get_segment("seg_02")
    assert s1 is not None and s1.status == SegmentStatus.PENDING
    assert s2 is not None and s2.status == SegmentStatus.TRANSLATED

    # 4. Reexecuta o pipeline: exatamente 2 segmentos devem ser re-traduzidos e 2 devem vir do cache
    res_after = pipeline.translate_project(project_id)
    assert res_after.freshly_translated == 2
    assert res_after.cached_segments == 2
    assert res_after.completed_segments == 4


def test_translation_pipeline_cancellation_and_resumption(
    test_project: tuple[SQLiteDatabase, str],
) -> None:
    """Interrupção segura deve salvar checkpoint com status paused e permitir retomada sem retrabalho."""
    db, project_id = test_project

    token = CancellationToken()
    engine = MadladTranslationEngine(runtime_type=RuntimeType.MOCK)
    pipeline = TranslationPipeline(db=db, translation_engine=engine)

    # Callback para acionar o cancelamento após processar o primeiro segmento
    def cancel_after_first(completed: int, total: int) -> None:
        if completed >= 1:
            token.cancel()

    # Executa com cancelamento planejado
    res_paused = pipeline.translate_project(
        project_id,
        cancellation_token=token,
        on_progress=cancel_after_first,
    )

    assert res_paused.status == "paused"
    assert res_paused.completed_segments >= 1
    assert res_paused.completed_segments < 4

    # Verifica persistência do checkpoint paused
    chk = db.get_latest_checkpoint(project_id)
    assert chk is not None
    assert chk.status == "paused"

    # Retomada com novo token sem cancelamento
    token_fresh = CancellationToken()
    res_resumed = pipeline.translate_project(
        project_id,
        cancellation_token=token_fresh,
    )

    assert res_resumed.status == "completed"
    assert res_resumed.completed_segments == 4
    # Os segmentos já concluídos antes da pausa são aproveitados via cache
    assert res_resumed.cached_segments >= 1
    assert (res_resumed.cached_segments + res_resumed.freshly_translated) == 4
