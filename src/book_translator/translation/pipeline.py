"""Pipeline de tradução incremental com checkpoints, cache, invalidação e cancelamento seguro."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from book_translator.core.models import Checkpoint, EventLog, Segment, SegmentStatus
from book_translator.logging import get_logger
from book_translator.translation.base import (
    CandidateRankerInterface,
    TranslationEngine,
)

if TYPE_CHECKING:
    from book_translator.context.engine import ContextRetrievalEngine
    from book_translator.database.base import DatabaseInterface

logger = get_logger("translation.pipeline")


class CancellationToken:
    """Token cooperativo de cancelamento seguro para interrupção atômica do pipeline."""

    def __init__(self) -> None:
        self._cancelled: bool = False

    def cancel(self) -> None:
        """Sinaliza pedido de cancelamento da execução."""
        self._cancelled = True
        logger.info("CancellationToken: cancelamento solicitado.")

    @property
    def is_cancelled(self) -> bool:
        """Indica se houve solicitação de interrupção."""
        return self._cancelled

    def reset(self) -> None:
        """Restaura o estado inicial do token."""
        self._cancelled = False


@dataclass
class TranslationPipelineConfig:
    """Configurações operacionais do pipeline de tradução incremental."""

    n_best: int = 1
    fast_mode: bool = False
    checkpoint_frequency: int = 1
    batch_size: int = 1
    temperature: float = 0.0
    max_tokens: int = 512
    version: str = "1.0.0"


@dataclass
class PipelineResult:
    """Resultado final da execução incremental do pipeline."""

    project_id: str
    status: str  # 'completed', 'paused', 'error'
    total_segments: int
    completed_segments: int
    cached_segments: int
    freshly_translated: int
    execution_time_ms: float
    last_completed_segment_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class TranslationPipeline:
    """Orquestrador do pipeline de tradução incremental, cache e checkpoints da obra.

    Garante:
    1. Tradução segmento a segmento com salvamento de progresso atômico (checkpoints).
    2. Retomada resiliente após interrupção.
    3. Cache com cálculo de chave determinística.
    4. Invalidação seletiva de cache por termo do glossário.
    5. Imutabilidade absoluta do texto original (`original_text` nunca é alterado).
    6. Cancelamento cooperativo seguro sem corrupção de estado.
    """

    def __init__(
        self,
        db: DatabaseInterface,
        translation_engine: TranslationEngine,
        context_engine: ContextRetrievalEngine | None = None,
        ranker: CandidateRankerInterface | None = None,
        config: TranslationPipelineConfig | None = None,
    ) -> None:
        self.db = db
        self.translation_engine = translation_engine
        self.context_engine = context_engine
        self.ranker = ranker
        self.config = config or TranslationPipelineConfig()

    @staticmethod
    def compute_cache_key(
        source_text: str,
        model_name: str,
        runtime: str,
        parameters: dict[str, Any],
        context_hash: str,
    ) -> str:
        """Gera um hash SHA-256 canônico e determinístico para indexação em cache."""
        sorted_params = json.dumps(parameters, sort_keys=True)
        payload = f"{source_text.strip()}|{model_name}|{runtime}|{sorted_params}|{context_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def translate_project(
        self,
        project_id: str,
        cancellation_token: CancellationToken | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> PipelineResult:
        """Executa a tradução incremental de todos os segmentos pendentes do projeto."""
        t0 = time.perf_counter()

        # 1. Recupera o documento completo e seus segmentos ordenados
        doc = self.db.load_document(project_id)
        if not doc or not doc.chapters:
            logger.warning(f"Projeto '{project_id}' não possui documento ou capítulos cadastrados.")
            return PipelineResult(
                project_id=project_id,
                status="completed",
                total_segments=0,
                completed_segments=0,
                cached_segments=0,
                freshly_translated=0,
                execution_time_ms=0.0,
            )

        all_segments: list[Segment] = []
        for chapter in doc.chapters:
            segs = self.db.get_segments_by_chapter(chapter.id)
            all_segments.extend(segs)

        total_segments = len(all_segments)
        if total_segments == 0:
            return PipelineResult(
                project_id=project_id,
                status="completed",
                total_segments=0,
                completed_segments=0,
                cached_segments=0,
                freshly_translated=0,
                execution_time_ms=0.0,
            )

        style_bible = self.db.get_style_bible(project_id)

        cached_segments = 0
        freshly_translated = 0
        completed_segments = 0
        last_seg_id = ""
        last_chap_id = ""

        # Registra evento inicial
        self.db.log_event(
            EventLog(
                id=f"evt_{project_id}_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                level="INFO",
                phase="translation",
                message=f"Iniciando pipeline incremental para {total_segments} segmentos.",
            )
        )

        for idx, segment in enumerate(all_segments, start=1):
            # 2. Verificação de Cancelamento Seguro (Cooperativo)
            if cancellation_token and cancellation_token.is_cancelled:
                logger.info(
                    f"Pipeline cancelado com segurança no segmento #{segment.id} ({idx}/{total_segments})"
                )
                chk = Checkpoint(
                    id=f"chk_{project_id}",
                    project_id=project_id,
                    last_completed_chapter_id=last_chap_id,
                    last_completed_segment_id=last_seg_id,
                    completed_segments=completed_segments,
                    total_segments=total_segments,
                    status="paused",
                )
                self.db.save_checkpoint(chk)

                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return PipelineResult(
                    project_id=project_id,
                    status="paused",
                    total_segments=total_segments,
                    completed_segments=completed_segments,
                    cached_segments=cached_segments,
                    freshly_translated=freshly_translated,
                    execution_time_ms=elapsed_ms,
                    last_completed_segment_id=last_seg_id,
                )

            # 3. Se o segmento já está traduzido com texto preenchido, verifica se o cache ainda é válido
            context = None
            if self.context_engine:
                context = self.context_engine.retrieve_context(segment)

            context_hash = context.reproducibility_hash if context else ""
            model_name = self.translation_engine.engine_name
            runtime_name = getattr(self.translation_engine, "backend", None)
            runtime_str = runtime_name.runtime_name if runtime_name else "default"

            params = {
                "n_best": self.config.n_best,
                "temperature": self.config.temperature,
                "version": self.config.version,
            }
            cache_key = self.compute_cache_key(
                source_text=segment.original_text,
                model_name=model_name,
                runtime=runtime_str,
                parameters=params,
                context_hash=context_hash,
            )

            # 4. Consulta ao Cache
            cached_entry = self.db.get_translation_cache(cache_key)

            if cached_entry:
                # Cache Hit! Não chama o motor de inferência
                logger.debug(f"Cache hit para segmento #{segment.id}")
                cached_segments += 1
                completed_segments += 1
                last_seg_id = segment.id
                last_chap_id = segment.chapter_id

                # Garante que o segmento está marcado como TRANSLATED no banco com o texto do cache
                if (
                    not segment.is_translated
                    or segment.translated_text != cached_entry["target_text"]
                ):
                    segment.translated_text = cached_entry["target_text"]
                    segment.status = SegmentStatus.TRANSLATED
                    self.db.save_segment(segment)

            elif segment.is_translated and segment.translated_text:
                # Segmento já possuía tradução anterior válida (resumo/retomada)
                completed_segments += 1
                last_seg_id = segment.id
                last_chap_id = segment.chapter_id

            else:
                # Cache Miss: executa a tradução real com o motor
                logger.debug(f"Processando tradução do segmento #{segment.id}")
                draft = self.translation_engine.translate_segment(
                    segment=segment,
                    context=context,
                    n_best=self.config.n_best,
                    ranker=self.ranker,
                    style_bible=style_bible,
                )

                # Persiste a tradução e seus candidatos
                self.db.save_translation_draft(draft)

                # Atualiza o segmento (SEM ALTERAR original_text!)
                segment.translated_text = draft.selected_text
                segment.status = SegmentStatus.TRANSLATED
                self.db.save_segment(segment)

                # Grava no cache indexado
                glossary_terms = (
                    [g.source_term for g in context.relevant_glossary] if context else []
                )
                self.db.save_translation_cache(
                    cache_key=cache_key,
                    project_id=project_id,
                    segment_id=segment.id,
                    source_text=segment.original_text,
                    target_text=draft.selected_text,
                    model_name=model_name,
                    runtime=runtime_str,
                    parameters=params,
                    context_hash=context_hash,
                    glossary_terms=glossary_terms,
                )

                freshly_translated += 1
                completed_segments += 1
                last_seg_id = segment.id
                last_chap_id = segment.chapter_id

            # Notifica progresso
            if on_progress:
                on_progress(completed_segments, total_segments)

            # Grava Checkpoint periódico
            if (idx % self.config.checkpoint_frequency == 0) or (idx == total_segments):
                chk = Checkpoint(
                    id=f"chk_{project_id}",
                    project_id=project_id,
                    last_completed_chapter_id=last_chap_id,
                    last_completed_segment_id=last_seg_id,
                    completed_segments=completed_segments,
                    total_segments=total_segments,
                    status="in_progress" if completed_segments < total_segments else "completed",
                )
                self.db.save_checkpoint(chk)

        # Finalização com status completed
        final_chk = Checkpoint(
            id=f"chk_{project_id}",
            project_id=project_id,
            last_completed_chapter_id=last_chap_id,
            last_completed_segment_id=last_seg_id,
            completed_segments=completed_segments,
            total_segments=total_segments,
            status="completed",
        )
        self.db.save_checkpoint(final_chk)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            f"Pipeline concluído para '{project_id}': "
            f"{completed_segments}/{total_segments} segmentos (cached={cached_segments}, fresh={freshly_translated}) em {elapsed_ms:.1f}ms"
        )

        return PipelineResult(
            project_id=project_id,
            status="completed",
            total_segments=total_segments,
            completed_segments=completed_segments,
            cached_segments=cached_segments,
            freshly_translated=freshly_translated,
            execution_time_ms=elapsed_ms,
            last_completed_segment_id=last_seg_id,
        )

    def invalidate_glossary_term(self, project_id: str, glossary_term: str) -> list[str]:
        """Invalida cirurgicamente o cache apenas para os segmentos afetados pelo termo."""
        affected = self.db.invalidate_cache_by_glossary_term(project_id, glossary_term)
        logger.info(
            f"Invalidação de glossário para '{glossary_term}' no projeto '{project_id}': "
            f"{len(affected)} segmentos invalidados e revertidos para PENDING."
        )
        self.db.log_event(
            EventLog(
                id=f"evt_inv_{project_id}_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                level="INFO",
                phase="cache_invalidation",
                message=f"Termo de glossário '{glossary_term}' invalidou {len(affected)} segmentos.",
                details={"glossary_term": glossary_term, "affected_segments": affected},
            )
        )
        return affected
