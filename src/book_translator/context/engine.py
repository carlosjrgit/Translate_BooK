"""Motor central de recuperação seletiva de contexto para tradução."""

from __future__ import annotations

from typing import Any

from book_translator.context.base import (
    ContextRetrievalInterface,
    ContextRetrievalStrategy,
    TranslationContext,
)
from book_translator.context.models import ContextBudgetConfig
from book_translator.context.strategies import (
    BalancedRetrievalStrategy,
    MinimalRetrievalStrategy,
    SemanticDenseRetrievalStrategy,
    StoryHeavyRetrievalStrategy,
    estimate_tokens,
)
from book_translator.core.models import Segment
from book_translator.logging import get_logger

logger = get_logger("context.engine")


class ContextRetrievalEngine(ContextRetrievalInterface):
    """Orquestrador do mecanismo de recuperação de contexto com suporte a estratégias substituíveis."""

    STRATEGIES: dict[str, type[ContextRetrievalStrategy]] = {
        "balanced": BalancedRetrievalStrategy,
        "minimal": MinimalRetrievalStrategy,
        "story_heavy": StoryHeavyRetrievalStrategy,
        "semantic_dense": SemanticDenseRetrievalStrategy,
    }

    def __init__(
        self,
        memory_manager: Any = None,
        strategy: str | ContextRetrievalStrategy = "balanced",
        config: ContextBudgetConfig | None = None,
        db: Any = None,
    ) -> None:
        self.memory = memory_manager
        self.db = db
        self.config = config or ContextBudgetConfig()
        self._strategy: ContextRetrievalStrategy = self._resolve_strategy(strategy)

    def _resolve_strategy(
        self, strategy: str | ContextRetrievalStrategy
    ) -> ContextRetrievalStrategy:
        if isinstance(strategy, str):
            strat_class = self.STRATEGIES.get(strategy.lower())
            if not strat_class:
                raise ValueError(
                    f"Estratégia de recuperação desconhecida: '{strategy}'. "
                    f"Opções válidas: {list(self.STRATEGIES.keys())}"
                )
            return strat_class()
        return strategy

    def set_strategy(self, strategy: str | ContextRetrievalStrategy) -> None:
        """Substitui a estratégia ativa em tempo de execução (Strategy Pattern)."""
        self._strategy = self._resolve_strategy(strategy)
        logger.info(f"Estratégia de contexto alterada para '{self._strategy.name}'.")

    @property
    def strategy(self) -> ContextRetrievalStrategy:
        return self._strategy

    def retrieve_context(
        self,
        segment: Segment,
        all_segments: list[Segment] | None = None,
        config: ContextBudgetConfig | None = None,
    ) -> TranslationContext:
        """Executa a recuperação seletiva com orçamentação e auditoria completa."""
        active_config = config or self.config

        # Se a lista completa de segmentos não for fornecida, tenta buscar do banco
        segments_list = all_segments or []
        if not segments_list and self.db and hasattr(self.db, "get_segments_by_chapter"):
            segments_list = self.db.get_segments_by_chapter(segment.chapter_id)
        if not segments_list:
            segments_list = [segment]

        # 1. Executa a estratégia selecionada
        context = self._strategy.retrieve(
            segment=segment,
            all_segments=segments_list,
            memory=self.memory,
            config=active_config,
        )

        # 2. Orçamentação e poda se exceder max_tokens
        context = self._apply_budget_pruning(context, active_config)

        # 3. Consolidação final do hash de reprodutibilidade
        context.reproducibility_hash = context.calculate_reproducibility_hash()

        return context

    def _apply_budget_pruning(
        self, context: TranslationContext, config: ContextBudgetConfig
    ) -> TranslationContext:
        """Poda elementos de menor relevância caso o orçamento de tokens seja ultrapassado."""
        total_estimated = (
            sum(estimate_tokens(t) for t in context.preceding_text)
            + sum(estimate_tokens(t) for t in context.succeeding_text)
            + estimate_tokens(context.chapter_summary)
            + sum(estimate_tokens(s.source_text) for s in context.semantic_snippets)
            + sum(estimate_tokens(f.statement) for f in context.story_facts)
        )

        if total_estimated <= config.max_tokens:
            return context

        # Poda primeiro trechos semânticos de menor score
        while total_estimated > config.max_tokens and context.semantic_snippets:
            removed = context.semantic_snippets.pop()  # já ordenados do maior para o menor
            total_estimated -= estimate_tokens(removed.source_text)

        # Se ainda exceder, poda fatos não travados de menor score
        while total_estimated > config.max_tokens and context.story_facts:
            unlocked = [f for f in context.story_facts if not f.locked]
            if not unlocked:
                break
            removed_fact = unlocked[-1]
            context.story_facts.remove(removed_fact)
            total_estimated -= estimate_tokens(removed_fact.statement)

        # Se ainda exceder, reduz texto subsequente
        while total_estimated > config.max_tokens and context.succeeding_text:
            rem = context.succeeding_text.pop()
            total_estimated -= estimate_tokens(rem)

        # Se ainda exceder, remove parágrafos anteriores mais distantes
        while total_estimated > config.max_tokens and len(context.preceding_text) > 1:
            oldest = context.preceding_text.pop(0)
            total_estimated -= estimate_tokens(oldest)

        # Se mesmo com apenas 1 parágrafo ainda exceder, trunca o parágrafo anterior
        if total_estimated > config.max_tokens and context.preceding_text:
            excess_tokens = total_estimated - config.max_tokens
            excess_chars = excess_tokens * 4
            p_last = context.preceding_text[-1]
            if len(p_last) > excess_chars + 20:
                truncated = p_last[: max(20, len(p_last) - excess_chars)] + "..."
                total_estimated -= estimate_tokens(p_last) - estimate_tokens(truncated)
                context.preceding_text[-1] = truncated

        # Recalcula métricas
        if context.metrics:
            context.metrics.total_tokens_estimated = total_estimated
            context.metrics.budget_utilization_pct = round(
                min(1.0, total_estimated / max(1, config.max_tokens)) * 100, 1
            )

        return context
