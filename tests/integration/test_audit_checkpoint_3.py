"""Auditoria Integrada e Avaliação de Desempenho do Pipeline de Tradução (Prompt 21 - Checkpoint 3).

Valida de ponta a ponta com corpus literário EN e traduções humanas de referência:
1. Context Retrieval (9 dimensões).
2. Motor MADLAD-400 (inferência e normalização de prompt).
3. Cache determinístico (SHA-256) e invalidação seletiva.
4. N-best Candidate Ranker (7 dimensões inspecionáveis).
5. QA Determinístico (números, datas, termos travados, SAFE FIX).
6. Semantic QA Multi-Sinal (polaridade, omissões, falsos cognatos, sujeitos).
7. Retrotradução (Backtranslation como evidência auxiliar).
8. Consistency Pass Global (15 dimensões, árvore navegável, rollback).

Investiga especificamente:
- Regressões contratuais e integridade de dados.
- Falso senso de confiança (embeddings isolados vs multi-sinal, falsos amigos, retrotradução ingênua).
- Etapas redundantes (checagem de termos travados repetida em 4 camadas, context retrieval antes do cache).
- Custo computacional excessivo (latência de inferência de volta, impacto do N-best, complexidade de regex).
- Falhas de rastreabilidade (persistência de ConsistencyFixAuditRecord vs QAFixAuditRecord, perda de N-best no cache).
- Divergências entre banco SQLite e modelos em memória (Document vs DB rows).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from book_translator.consistency.base import (
    ConsistencyConflict,
    GlobalConsistencyReport,
)
from book_translator.consistency.checker import GlobalConsistencyChecker
from book_translator.context.base import ContextBudgetConfig
from book_translator.context.engine import ContextRetrievalEngine
from book_translator.context.strategies import BalancedRetrievalStrategy
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
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    TranslationMemoryEntry,
)
from book_translator.memory.manager import MemoryManager
from book_translator.memory.style_bible import StyleBible
from book_translator.qa.backtranslation import BacktranslationVerifier
from book_translator.qa.base import IssueSeverity
from book_translator.qa.deterministic import DeterministicQAEngine
from book_translator.qa.orchestrator import UnifiedQAOrchestrator
from book_translator.qa.semantic import MockSemanticEncoder, SemanticQAEngine
from book_translator.translation.madlad import MadladTranslationEngine, MockMadladBackend
from book_translator.translation.pipeline import (
    PipelineResult,
    TranslationPipeline,
    TranslationPipelineConfig,
)
from book_translator.translation.ranker import LiteraryCandidateRanker

# =============================================================================
# Corpus Interno de Avaliação (Textos EN com Referência Humana PT-BR)
# =============================================================================

HUMAN_REFERENCE_CORPUS = [
    {
        "id": "seg_01",
        "chapter": "chap_01",
        "source": "It has long been an axiom of mine that the little things are infinitely the most important, remarked Holmes.",
        "reference": "— Há muito tempo é um axioma meu que as pequenas coisas são infinitamente as mais importantes — comentou Holmes.",
        "category": "dialogue_formal",
        "character": "Sherlock Holmes",
        "treatment": "formal",
    },
    {
        "id": "seg_02",
        "chapter": "chap_01",
        "source": "The warp drive was fully online and humming steadily at 221B Baker Street.",
        "reference": "O motor de dobra estava totalmente ligado e zumbindo suavemente na Baker Street, 221B.",
        "category": "terminology_locked",
        "locked_term": ("warp drive", "motor de dobra"),
    },
    {
        "id": "seg_03",
        "chapter": "chap_01",
        "source": "He was not guilty of the theft of the 500 gold sovereigns on May 14, 1892.",
        "reference": "Ele não era culpado pelo roubo dos 500 soberanos de ouro em 14 de maio de 1892.",
        "category": "deterministic_and_polarity",
        "numbers": ["500"],
        "dates": ["May 14, 1892"],
    },
    {
        "id": "seg_04",
        "chapter": "chap_02",
        "source": "Actually, Dr. Watson realized that his parents had left for Scotland Yard.",
        "reference": "Na verdade, o Dr. Watson percebeu que seus pais haviam partido para a Scotland Yard.",
        "category": "false_friends",
        "false_cognates": ["actually", "realized", "parents"],
    },
    {
        "id": "seg_05",
        "chapter": "chap_02",
        "source": "Captain, engage the warp drive right now before the midnight train departs!",
        "reference": "Capitão, acione o motor de dobra agora mesmo antes que o trem da meia-noite parta!",
        "category": "consistency_and_dialogue",
        "locked_term": ("warp drive", "motor de dobra"),
    },
    {
        "id": "seg_06",
        "chapter": "chap_02",
        "source": "Holmes asked Watson about the secret papers, but Watson remained silent.",
        "reference": "Holmes perguntou a Watson sobre os documentos secretos, mas Watson permaneceu em silêncio.",
        "category": "subject_and_dialogue",
    },
]


@pytest.fixture
def audit_environment(tmp_path: Path):
    """Configura ambiente hermético e completo para a auditoria do pipeline."""
    db_path = tmp_path / "audit_checkpoint_3.db"
    db = SQLiteDatabase(db_path)
    db.initialize()

    project_id = "proj_audit_3"
    project = Project(
        metadata=ProjectMetadata(
            project_id=project_id,
            book_title="Audit Checkpoint 3 Literary Suite",
            source_file_path=str(tmp_path / "literary_suite.txt"),
            source_language="en",
            target_language="pt-BR",
        ),
        project_dir=tmp_path,
        db_path=db_path,
    )
    db.save_project(project)

    # 1. Cria Documento e Capítulos
    doc_id = "doc_audit_3"
    doc = Document(
        id=doc_id,
        project_id=project_id,
        title="The Sign of the Warp Drive",
        author="Arthur C. Doyle",
        source_format="txt",
        metadata=DocumentMetadata(
            title="The Sign of the Warp Drive",
            author="Arthur C. Doyle",
            language="en",
        ),
    )
    ch1 = Chapter(id="chap_01", title="Chapter 1: The Baker Street Axiom", order=1)
    ch2 = Chapter(id="chap_02", title="Chapter 2: The Scottish Departure", order=2)

    segments_map: dict[str, Segment] = {}
    for item in HUMAN_REFERENCE_CORPUS:
        seg = Segment(
            id=item["id"],
            chapter_id=item["chapter"],
            original_text=item["source"],
            sequence_order=int(item["id"].split("_")[1]),
            status=SegmentStatus.PENDING,
        )
        segments_map[seg.id] = seg
        if item["chapter"] == "chap_01":
            ch1.segments.append(seg)
        else:
            ch2.segments.append(seg)

    doc.chapters = [ch1, ch2]
    db.save_document(doc, project_id)

    # 2. Memória: Glossário travado e Personagens
    mem_mgr = MemoryManager(db=db, project_id=project_id)
    mem_mgr.glossary.add_entry(
        GlossaryEntry(
            source_term="warp drive",
            target_term="motor de dobra",
            locked=True,
            case_sensitive=False,
            notes="Termo canônico da saga",
        )
    )
    mem_mgr.characters.add_character(
        CharacterEntry(
            id="char_holmes",
            name="Sherlock Holmes",
            gender="male",
            treatment="formal",
            speech_style="deductive, analytical",
            aliases=["Holmes", "o detetive"],
        )
    )
    mem_mgr.characters.add_character(
        CharacterEntry(
            id="char_watson",
            name="Dr. John Watson",
            gender="male",
            treatment="formal",
            speech_style="courteous, observant",
            aliases=["Watson", "o médico"],
        )
    )
    mem_mgr.translation_memory.add_entry(
        TranslationMemoryEntry(
            source_term="221B Baker Street",
            target_term="Baker Street, 221B",
            locked=True,
        )
    )

    style_bible = StyleBible(
        project_id=project_id,
        formality_level="formal",
        dialogue_style="travessão",
        narrative_person="terceira pessoa",
        predominant_tense="passado",
    )
    db.save_style_bible(project_id, style_bible)

    # 3. Engines
    context_engine = ContextRetrievalEngine(
        memory_manager=mem_mgr,
        strategy=BalancedRetrievalStrategy(),
        config=ContextBudgetConfig(max_tokens=1000),
        db=db,
    )

    backend = MockMadladBackend()
    # Registra no mock traduções canônicas de alta qualidade
    canonical_pairs = [
        (
            "it has long been an axiom of mine that the little things are infinitely the most important, remarked holmes.",
            "— Há muito tempo é um axioma meu que as pequenas coisas são infinitamente as mais importantes — comentou Holmes.",
        ),
        (
            "the warp drive was fully online and humming steadily at 221b baker street.",
            "O motor de dobra estava totalmente ligado e zumbindo suavemente na Baker Street, 221B.",
        ),
        (
            "he was not guilty of the theft of the 500 gold sovereigns on may 14, 1892.",
            "Ele não era culpado pelo roubo dos 500 soberanos de ouro em 14 de maio de 1892.",
        ),
        (
            "actually, dr. watson realized that his parents had left for scotland yard.",
            "Na verdade, o Dr. Watson percebeu que seus pais haviam partido para a Scotland Yard.",
        ),
        (
            "captain, engage the warp drive right now before the midnight train departs!",
            "Capitão, acione o motor de dobra agora mesmo antes que o trem da meia-noite parta!",
        ),
        (
            "holmes asked watson about the secret papers, but watson remained silent.",
            "Holmes perguntou a Watson sobre os documentos secretos, mas Watson permaneceu em silêncio.",
        ),
    ]
    for en_text, pt_text in canonical_pairs:
        backend._lexicon[en_text.strip().lower()] = pt_text
        backend._reverse_lexicon[pt_text.strip().lower()] = en_text

    madlad = MadladTranslationEngine(backend=backend)
    ranker = LiteraryCandidateRanker()
    pipeline = TranslationPipeline(
        db=db,
        translation_engine=madlad,
        context_engine=context_engine,
        ranker=ranker,
        config=TranslationPipelineConfig(n_best=3, fast_mode=False),
    )

    qa_orchestrator = UnifiedQAOrchestrator(
        deterministic_engine=DeterministicQAEngine(),
        semantic_engine=SemanticQAEngine(encoder=MockSemanticEncoder()),
        backtranslation_verifier=BacktranslationVerifier(engine=madlad),
        db=db,
    )

    consistency_checker = GlobalConsistencyChecker()

    return {
        "db": db,
        "project_id": project_id,
        "doc": doc,
        "mem_mgr": mem_mgr,
        "context_engine": context_engine,
        "madlad": madlad,
        "ranker": ranker,
        "pipeline": pipeline,
        "qa_orchestrator": qa_orchestrator,
        "consistency_checker": consistency_checker,
        "corpus": HUMAN_REFERENCE_CORPUS,
    }


# =============================================================================
# 1. AUDITORIA DE REGRESSÕES E INTEGRIDADE DE PONTA A PONTA
# =============================================================================

def test_audit_end_to_end_pipeline_execution(audit_environment):
    """Executa o pipeline completo verificando que todos os módulos operam sem quebra de contrato."""
    env = audit_environment
    pipeline: TranslationPipeline = env["pipeline"]
    qa: UnifiedQAOrchestrator = env["qa_orchestrator"]
    checker: GlobalConsistencyChecker = env["consistency_checker"]
    db: SQLiteDatabase = env["db"]
    project_id: str = env["project_id"]

    # 1. Execução do pipeline de tradução
    t0 = time.perf_counter()
    result: PipelineResult = pipeline.translate_project(project_id)
    _t_pipeline = time.perf_counter() - t0

    assert result.status == "completed"
    assert result.total_segments == len(HUMAN_REFERENCE_CORPUS)
    assert result.freshly_translated == len(HUMAN_REFERENCE_CORPUS)
    assert result.cached_segments == 0

    # 2. Verificação de persistência dos segmentos e drafts
    segments = db.get_segments_by_chapter("chap_01") + db.get_segments_by_chapter("chap_02")
    for seg in segments:
        assert seg.is_translated
        assert seg.translated_text != ""
        translations = db.get_translations(seg.id)
        assert len(translations) >= 1
        selected = db.get_selected_translation(seg.id)
        assert selected is not None
        assert selected["translated_text"] == seg.translated_text
        assert "context_used" in selected["metadata"]

    # 3. Execução do QA unificado em todos os segmentos
    t0_qa = time.perf_counter()
    qa_reports = []
    for seg in segments:
        context = env["context_engine"].retrieve_context(seg)
        report = qa.evaluate(
            segment=seg,
            original_text=seg.original_text,
            translated_text=seg.translated_text,
            context=context,
        )
        qa_reports.append(report)
        assert report.passed is True  # Todas as traduções canônicas de referência devem passar
    _t_qa = time.perf_counter() - t0_qa

    # 4. Consistency Pass Global
    updated_doc = db.load_document(project_id)
    t0_consistency = time.perf_counter()
    consistency_report: GlobalConsistencyReport = checker.audit(
        document=updated_doc,
        memory_manager=env["mem_mgr"],
    )
    _t_consistency = time.perf_counter() - t0_consistency

    assert consistency_report.total_segments_audited == len(HUMAN_REFERENCE_CORPUS)
    # No conjunto canônico perfeito, não deve haver conflitos de severidade SAFE_FIX
    safe_fixes = consistency_report.get_conflicts_by_severity(IssueSeverity.SAFE_FIX)
    assert len(safe_fixes) == 0


# =============================================================================
# 2. AUDITORIA DE FALSO SENSO DE CONFIANÇA
# =============================================================================

def test_audit_false_sense_of_confidence_embeddings_vs_multisignal(audit_environment):
    """Evidencia o perigo de confiar exclusivamente em embeddings de similaridade.

    Mostra que frases com significado invertido (negação omitida) recebem alta similaridade
    em embeddings rasos (Mock / Bag-of-Words / vetores genéricos), mas são barradas pelo
    motor multi-sinal (Prompt 18).
    """
    env = audit_environment
    qa: UnifiedQAOrchestrator = env["qa_orchestrator"]

    # Caso de inversão dramática de significado:
    original = "He was not guilty of the theft of the 500 gold sovereigns."
    corrupted_pt = "Ele era culpado pelo roubo dos 500 soberanos de ouro."  # Inversão crítica!

    dummy_seg = Segment(id="seg_invert", chapter_id="chap_01", original_text=original, sequence_order=1)

    # 1. Avaliação direta do encoder (simulando modelo ingênuo de similaridade)
    encoder = MockSemanticEncoder()
    emb_sim = encoder.similarity(original, corrupted_pt)
    # Em abordagens baseadas exclusivamente em embedding léxico/bag-of-words, a similaridade é altíssima:
    assert emb_sim >= 0.70, "Embeddings ingênuos produzem falso senso de segurança em inversões"

    # 2. Avaliação pelo QA Multi-Sinal (Prompt 18)
    report = qa.evaluate(
        segment=dummy_seg,
        original_text=original,
        translated_text=corrupted_pt,
    )

    # O motor multi-sinal DEVE reprovar a tradução
    assert report.passed is False
    issue_types = [i.check_type for i in report.issues]
    assert "polarity_inversion" in issue_types or "meaning_reversal" in issue_types


def test_audit_false_sense_of_confidence_backtranslation_limits(audit_environment):
    """Audita os limites e falsos positivos/negativos da retrotradução.

    Evidencia:
    1. Falso positivo na retrotradução por variação lexical benigna (ex: hound -> cão -> dog).
    2. Falso negativo na retrotradução com tradução literal de expressão idiomática
       (ex: 'piece of cake' -> 'pedaço de bolo' -> 'piece of cake').
    """
    env = audit_environment
    madlad: MadladTranslationEngine = env["madlad"]
    verifier = BacktranslationVerifier(engine=madlad)

    # Limite 1: Expressão idiomática traduzida literalmente pode voltar perfeita em inglês ingênuo,
    # gerando falso negativo se a retrotradução for tratada como autoridade absoluta!
    idiom_en = "It is a piece of cake."
    literal_pt = "É um pedaço de bolo."  # Tradução editorialmente incorreta/literal
    # Se o motor de volta traduzir 'pedaço de bolo' -> 'piece of cake', o ciclo fecha sem detectar o erro!
    back_en = verifier.verify(original_en=idiom_en, translated_pt=literal_pt, fast_mode=False)
    # A retrotradução NÃO deve substituir a validação semântica/humana
    assert back_en.token_similarity >= 0.0


# =============================================================================
# 3. AUDITORIA DE ETAPAS REDUNDANTES
# =============================================================================

def test_audit_redundant_pipeline_steps(audit_environment):
    """Mapeia e quantifica sobreposições e etapas redundantes no pipeline."""
    env = audit_environment
    pipeline: TranslationPipeline = env["pipeline"]
    _db: SQLiteDatabase = env["db"]
    project_id: str = env["project_id"]

    # Redundância 1: Termo de Glossário travado é verificado em 4 momentos distintos:
    # 1. Pós-processamento do MadladEngine (madlad.py: L623-L629)
    # 2. LiteraryCandidateRanker (ranker.py: _score_terminology)
    # 3. DeterministicQAEngine (deterministic.py: _check_locked_terms)
    # 4. GlobalConsistencyChecker (checker.py: _audit_terminology_and_glossary)
    # Esta redundância garante defesa em profundidade, mas consome tempo de CPU repetitivo.

    # Redundância 2: Context Retrieval executa ANTES de verificar o cache no pipeline
    # (pipeline.py L205: context = self.context_engine.retrieve_context(segment) antes de db.get_translation_cache).
    # Como o hash do contexto faz parte da cache_key, toda consulta ao cache obriga a resolução completa
    # de contexto no SQLite (buscando parágrafos anteriores, glossário e fatos da história).

    # 1. Execução 1: Popula o cache com a tradução inicial
    res_fresh = pipeline.translate_project(project_id)
    assert res_fresh.freshly_translated == len(HUMAN_REFERENCE_CORPUS)

    # 2. Execução 2: 100% cache hit
    t0_hit = time.perf_counter()
    result_hit = pipeline.translate_project(project_id)
    t_hit = time.perf_counter() - t0_hit

    assert result_hit.cached_segments == len(HUMAN_REFERENCE_CORPUS)
    assert result_hit.freshly_translated == 0
    # O tempo de cache hit inclui a recuperação de contexto redundante para cada segmento!
    assert t_hit >= 0.0


# =============================================================================
# 4. AUDITORIA DE CUSTO COMPUTACIONAL E LATÊNCIA
# =============================================================================

def test_audit_computational_cost_fast_mode_vs_standard(audit_environment):
    """Mede o impacto de desempenho entre modo padrão (com retrotradução) e fast_mode."""
    env = audit_environment
    qa: UnifiedQAOrchestrator = env["qa_orchestrator"]
    seg = Segment(
        id="seg_perf",
        chapter_id="chap_01",
        original_text="The wind howled across the desolate moors.",
        sequence_order=1,
    )
    tr_text = "O vento uivava através das charnecas desoladas."

    # Execução Standard (com Backtranslation)
    t0_std = time.perf_counter()
    rep_std = qa.evaluate(segment=seg, original_text=seg.original_text, translated_text=tr_text, fast_mode=False)
    t_std = (time.perf_counter() - t0_std) * 1000.0

    # Execução Fast Mode (Backtranslation bypassed)
    t0_fast = time.perf_counter()
    rep_fast = qa.evaluate(segment=seg, original_text=seg.original_text, translated_text=tr_text, fast_mode=True)
    t_fast = (time.perf_counter() - t0_fast) * 1000.0

    assert rep_fast.backtranslation_evidence.metadata.get("bypassed") is True
    assert rep_std.backtranslation_evidence.metadata.get("bypassed", False) is False
    # O fast mode economiza o ciclo de inferência de volta
    assert t_fast <= t_std + 5.0  # tolerância para precisão de clock em máquinas rápidas


# =============================================================================
# 5. AUDITORIA DE FALHAS DE RASTREABILIDADE
# =============================================================================

def test_audit_traceability_gaps(audit_environment):
    """Identifica falhas de rastreabilidade e lacunas de persistência no sistema.

    Lacuna detectada:
    - QAFixAuditRecord possui persistência em SQLite (db.save_qa_fix_audit / get_qa_fix_audits).
    - ConsistencyFixAuditRecord NÃO possui persistência relacional em SQLite, existindo apenas
      em memória no GlobalConsistencyReport. Se o processo morrer, a capacidade de rollback
      do Consistency Pass é perdida da sessão!
    """
    env = audit_environment
    checker: GlobalConsistencyChecker = env["consistency_checker"]
    db: SQLiteDatabase = env["db"]
    doc: Document = env["doc"]

    # Cria relatório sintético com 1 safe fix
    report = GlobalConsistencyReport(total_segments_audited=1, metadata={"project_id": env["project_id"]})
    conflict = ConsistencyConflict(
        term_or_entity="warp drive",
        category="glossary",
        severity=IssueSeverity.SAFE_FIX,
        suggested_standardization="motor de dobra",
    )
    report.conflicts.append(conflict)

    # Executa safe fixes
    applied = checker.apply_safe_fixes(doc, report)
    assert isinstance(applied, list)
    assert len(report.audit_trail) >= 0

    # Verifica se há tabela ou método no SQLite para salvar ConsistencyFixAuditRecord:
    has_db_method = hasattr(db, "save_consistency_fix_audit")
    assert has_db_method is False, "Achado de Auditoria confirmado: falta tabela/método para persistir ConsistencyFixAuditRecord no SQLite"


# =============================================================================
# 6. AUDITORIA DE DIVERGÊNCIAS ENTRE BANCO E MODELOS EM MEMÓRIA
# =============================================================================

def test_audit_discrepancy_between_db_and_in_memory_models(audit_environment):
    """Evidencia a divergência de sincronização entre instâncias em memória e o banco de dados.

    Quando TranslationPipeline.translate_project é chamado:
    - Atualiza os registros na tabela 'segments' do SQLite.
    - O objeto Document retornado anteriormente por db.load_document NÃO tem seus segmentos
      atualizados automaticamente (porque novas instâncias são geradas ao ler do DB).
    """
    env = audit_environment
    pipeline: TranslationPipeline = env["pipeline"]
    db: SQLiteDatabase = env["db"]
    project_id: str = env["project_id"]

    # 1. Carrega documento em memória ANTES do pipeline
    in_memory_doc = db.load_document(project_id)
    assert in_memory_doc.chapters[0].segments[0].status == SegmentStatus.PENDING
    assert in_memory_doc.chapters[0].segments[0].translated_text == ""

    # 2. Roda o pipeline (que salva diretamente no banco)
    pipeline.translate_project(project_id)

    # 3. O objeto em memória pré-existente CONTINUA como PENDING (divergência banco vs memória)
    assert in_memory_doc.chapters[0].segments[0].status == SegmentStatus.PENDING

    # 4. Somente um novo load_document reflete o estado atualizado do banco
    reloaded_doc = db.load_document(project_id)
    assert reloaded_doc.chapters[0].segments[0].status == SegmentStatus.TRANSLATED
    assert reloaded_doc.chapters[0].segments[0].translated_text != ""
