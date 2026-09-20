"""Estratégias substituíveis de recuperação de contexto (Pattern Strategy)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from book_translator.context.base import (
    ContextItemScore,
    ContextRetrievalStrategy,
    TranslationContext,
)
from book_translator.context.models import (
    ContextBudgetConfig,
    ContextMetrics,
    SemanticSnippet,
)
from book_translator.context.resolvers import (
    AliasResolver,
    LexicalSemanticMatcher,
    PronounResolver,
    RecurringTermMatcher,
)
from book_translator.core.models import Segment
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    PersistentFact,
    StoryRelationship,
    TranslationMemoryEntry,
)


def estimate_tokens(text: str) -> int:
    """Estimativa rápida e determinística de tokens (~4 caracteres por token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class BaseRetrievalStrategy:
    """Classe base contendo utilitários compartilhados de orçamentação e filtragem."""

    @staticmethod
    def extract_surrounding_segments(
        current_segment: Segment,
        all_segments: list[Segment],
        window_before: int = 2,
        window_after: int = 1,
        allow_future_leakage: bool = False,
    ) -> tuple[list[Segment], list[Segment]]:
        """Extrai os segmentos anteriores e posteriores imediatos respeitando os limites."""
        if not all_segments:
            return [], []

        # Se os segmentos contiverem múltiplos capítulos, a vizinhança imediata pertence ao mesmo capítulo
        chapter_segs = [s for s in all_segments if s.chapter_id == current_segment.chapter_id]
        sorted_segs = (
            sorted(chapter_segs, key=lambda s: s.sequence_order)
            if chapter_segs
            else list(all_segments)
        )

        curr_idx = -1
        for i, s in enumerate(sorted_segs):
            if s.id == current_segment.id:
                curr_idx = i
                break

        if curr_idx == -1:
            return [], []

        # Segmentos anteriores
        start_before = max(0, curr_idx - window_before)
        preceding = sorted_segs[start_before:curr_idx]

        # Segmentos posteriores (com guarda anti-vazamento)
        succeeding: list[Segment] = []
        if allow_future_leakage and window_after > 0:
            end_after = min(len(sorted_segs), curr_idx + 1 + window_after)
            succeeding = sorted_segs[curr_idx + 1 : end_after]

        return preceding, succeeding

    @staticmethod
    def filter_future_facts(
        facts: list[PersistentFact],
        current_chapter: str,
        allow_future_leakage: bool = False,
    ) -> list[PersistentFact]:
        """Impede que fatos revelados apenas em capítulos posteriores vazem prematuramente."""
        if allow_future_leakage or not current_chapter:
            return facts

        filtered: list[PersistentFact] = []
        for f in facts:
            # Se o fato tiver metadado de revelação futura
            if f.metadata.get("is_future_revelation", False):
                continue
            filtered.append(f)
        return filtered


class BalancedRetrievalStrategy(BaseRetrievalStrategy, ContextRetrievalStrategy):
    """Estratégia equilibrada: combina vizinhança, personagens, glossário, TM, trechos semânticos e fatos."""

    name: str = "balanced"

    def retrieve(
        self,
        segment: Segment,
        all_segments: list[Segment],
        memory: Any,
        config: ContextBudgetConfig,
    ) -> TranslationContext:
        scores: list[ContextItemScore] = []
        future_blocked_count = 0

        # 1. Vizinhança textual
        preceding_segs, succeeding_segs = self.extract_surrounding_segments(
            segment,
            all_segments,
            window_before=config.window_before,
            window_after=config.window_after,
            allow_future_leakage=config.allow_future_leakage,
        )
        preceding_texts = [s.original_text for s in preceding_segs]
        succeeding_texts = [s.original_text for s in succeeding_segs]

        for p_seg in preceding_segs:
            scores.append(
                ContextItemScore(
                    category="preceding",
                    item_id=p_seg.id,
                    score=0.90,
                    justification=f"Parágrafo imediatamente anterior #{p_seg.id}.",
                )
            )

        for s_seg in succeeding_segs:
            scores.append(
                ContextItemScore(
                    category="succeeding",
                    item_id=s_seg.id,
                    score=0.50,
                    justification=f"Parágrafo posterior #{s_seg.id} (permitido por configuração).",
                    is_future=True,
                )
            )

        # 2. Resumo do capítulo (StoryMemory)
        chapter_summary = ""
        if memory and hasattr(memory, "story"):
            sum_obj = memory.story.get_chapter_summary(segment.chapter_id)
            if sum_obj:
                chapter_summary = sum_obj.summary
                scores.append(
                    ContextItemScore(
                        category="summary",
                        item_id=segment.chapter_id,
                        score=0.85,
                        justification=f"Resumo editorial do capítulo '{segment.chapter_id}'.",
                    )
                )

        # 3. Personagens (Explícitos, Aliases e Resolução Pronominal)
        active_chars: list[CharacterEntry] = []
        seen_char_ids: set[str] = set()

        if memory and hasattr(memory, "characters"):
            # Aliases e menções explícitas
            alias_matches = AliasResolver.resolve_aliases(segment, memory.characters)
            for char, alias_found, sc, just in alias_matches:
                if char.id not in seen_char_ids:
                    active_chars.append(char)
                    seen_char_ids.add(char.id)
                    scores.append(
                        ContextItemScore(
                            category="character",
                            item_id=char.id,
                            score=sc,
                            justification=just,
                        )
                    )

            # Resolução pronominal
            all_known_chars = (
                memory.characters.list_characters()
                if hasattr(memory.characters, "list_characters")
                else list(getattr(memory.characters, "_characters", {}).values())
            )
            pronoun_matches = PronounResolver.resolve_pronominal_references(
                segment, preceding_segs, all_known_chars
            )
            for char, pron, sc, just in pronoun_matches:
                if char.id not in seen_char_ids:
                    active_chars.append(char)
                    seen_char_ids.add(char.id)
                    scores.append(
                        ContextItemScore(
                            category="pronoun",
                            item_id=char.id,
                            score=sc,
                            justification=just,
                        )
                    )

        # 4. Relações relevantes entre os personagens ativos (StoryMemory)
        relevant_rels: list[StoryRelationship] = []
        if memory and hasattr(memory, "story") and active_chars:
            active_ids = {c.id for c in active_chars}
            all_rels = memory.story.get_relationships()
            for r in all_rels:
                if r.source_character_id in active_ids or r.target_character_id in active_ids:
                    relevant_rels.append(r)
                    scores.append(
                        ContextItemScore(
                            category="relationship",
                            item_id=r.id,
                            score=0.80,
                            justification=(
                                f"Relação ativa entre '{r.source_character_id}' e '{r.target_character_id}': "
                                f"'{r.relation_type}' (evidência: {r.evidence[:60] if r.evidence else 'registro'})."
                            ),
                        )
                    )

        # 5. Termos do Glossário
        relevant_glossary: list[GlossaryEntry] = []
        if memory and hasattr(memory, "glossary"):
            gloss_matches = RecurringTermMatcher.match_glossary_terms(
                segment, memory.glossary, preceding_segs
            )
            for g_entry, sc, just in gloss_matches[: config.max_glossary_terms]:
                relevant_glossary.append(g_entry)
                scores.append(
                    ContextItemScore(
                        category="glossary",
                        item_id=g_entry.source_term,
                        score=sc,
                        justification=just,
                    )
                )

        # 6. Translation Memory
        established_tm: list[TranslationMemoryEntry] = []
        if memory and hasattr(memory, "tm"):
            tm_matches = RecurringTermMatcher.match_tm_entries(segment, memory.tm)
            for tm_entry, sc, just in tm_matches[: config.max_tm_matches]:
                established_tm.append(tm_entry)
                scores.append(
                    ContextItemScore(
                        category="tm",
                        item_id=tm_entry.source_term,
                        score=sc,
                        justification=just,
                    )
                )

        # 7. Trechos anteriores semanticamente relacionados
        semantic_snippets: list[SemanticSnippet] = []
        if all_segments:
            snippets = LexicalSemanticMatcher.find_similar_passages(
                target_segment=segment,
                all_segments=all_segments,
                allow_future_leakage=config.allow_future_leakage,
                min_threshold=config.min_similarity_threshold,
                top_k=config.max_semantic_snippets,
            )
            for snip in snippets:
                semantic_snippets.append(snip)
                scores.append(
                    ContextItemScore(
                        category="semantic",
                        item_id=snip.segment_id,
                        score=snip.similarity_score,
                        justification=snip.justification,
                    )
                )

        # 8. Fatos da Story Memory
        story_facts: list[PersistentFact] = []
        if memory and hasattr(memory, "story"):
            all_facts = memory.story.get_facts()
            safe_facts = self.filter_future_facts(
                all_facts, segment.chapter_id, config.allow_future_leakage
            )
            # Prioriza fatos que tocam personagens ativos ou o texto
            seg_lower = segment.original_text.lower()
            for fact in safe_facts:
                is_relevant = (
                    fact.locked
                    or any(c.id in fact.subject_entity_ids for c in active_chars)
                    or any(w in seg_lower for w in fact.statement.lower().split() if len(w) > 4)
                )
                if is_relevant:
                    story_facts.append(fact)
                    sc = 0.95 if fact.locked else 0.75
                    scores.append(
                        ContextItemScore(
                            category="fact",
                            item_id=fact.id,
                            score=sc,
                            justification=(
                                f"Fato persistente (locked={fact.locked}): '{fact.statement}' "
                                f"(evidência: {fact.evidence[:60] if fact.evidence else 'lore'})."
                            ),
                        )
                    )
                if len(story_facts) >= config.max_facts:
                    break

        # 9. Cálculo de métricas
        total_tokens = (
            sum(estimate_tokens(t) for t in preceding_texts)
            + sum(estimate_tokens(t) for t in succeeding_texts)
            + estimate_tokens(chapter_summary)
            + sum(estimate_tokens(s.source_text) for s in semantic_snippets)
            + sum(estimate_tokens(f.statement) for f in story_facts)
        )
        avg_score = sum(s.score for s in scores) / len(scores) if scores else 0.0
        cat_counts = Counter(s.category for s in scores)

        metrics = ContextMetrics(
            overall_relevance_score=round(avg_score, 3),
            total_tokens_estimated=total_tokens,
            budget_utilization_pct=round(
                min(1.0, total_tokens / max(1, config.max_tokens)) * 100, 1
            ),
            items_count_by_category=dict(cat_counts),
            future_items_blocked_count=future_blocked_count,
        )

        ctx = TranslationContext(
            segment_id=segment.id,
            preceding_text=preceding_texts,
            succeeding_text=succeeding_texts,
            chapter_summary=chapter_summary,
            active_characters=active_chars[: config.max_characters],
            relevant_glossary=relevant_glossary,
            established_translations=established_tm,
            relevant_relationships=relevant_rels,
            story_facts=story_facts,
            semantic_snippets=semantic_snippets,
            scores=scores,
            strategy_used=self.name,
            future_leakage_prevented=not config.allow_future_leakage,
            metrics=metrics,
        )
        return ctx


class MinimalRetrievalStrategy(BaseRetrievalStrategy, ContextRetrievalStrategy):
    """Estratégia minimalista: contexto imediato enxuto para orçamento estrito de tokens."""

    name: str = "minimal"

    def retrieve(
        self,
        segment: Segment,
        all_segments: list[Segment],
        memory: Any,
        config: ContextBudgetConfig,
    ) -> TranslationContext:
        scores: list[ContextItemScore] = []

        # Apenas 1 parágrafo imediatamente anterior
        preceding_segs, _ = self.extract_surrounding_segments(
            segment, all_segments, window_before=1, window_after=0, allow_future_leakage=False
        )
        preceding_texts = [s.original_text for s in preceding_segs]
        for p in preceding_segs:
            scores.append(
                ContextItemScore(
                    category="preceding",
                    item_id=p.id,
                    score=0.90,
                    justification=f"Contexto imediato #{p.id}.",
                )
            )

        # Apenas termos de glossário com locked=True
        relevant_glossary: list[GlossaryEntry] = []
        if memory and hasattr(memory, "glossary"):
            matches = RecurringTermMatcher.match_glossary_terms(segment, memory.glossary)
            for g, sc, just in matches:
                if g.locked:
                    relevant_glossary.append(g)
                    scores.append(
                        ContextItemScore(
                            category="glossary",
                            item_id=g.source_term,
                            score=1.0,
                            justification=f"Termo travado obrigatório: '{g.source_term}' -> '{g.target_term}'.",
                        )
                    )

        # Apenas personagens com menção estrita no segmento
        active_chars: list[CharacterEntry] = []
        if memory and hasattr(memory, "characters"):
            matches = AliasResolver.resolve_aliases(segment, memory.characters)
            for char, _, sc, just in matches:
                active_chars.append(char)
                scores.append(
                    ContextItemScore(
                        category="character",
                        item_id=char.id,
                        score=sc,
                        justification=just,
                    )
                )

        ctx = TranslationContext(
            segment_id=segment.id,
            preceding_text=preceding_texts,
            succeeding_text=[],
            chapter_summary="",
            active_characters=active_chars,
            relevant_glossary=relevant_glossary,
            established_translations=[],
            relevant_relationships=[],
            story_facts=[],
            semantic_snippets=[],
            scores=scores,
            strategy_used=self.name,
            future_leakage_prevented=True,
        )
        return ctx


class StoryHeavyRetrievalStrategy(BaseRetrievalStrategy, ContextRetrievalStrategy):
    """Estratégia com ênfase narrativa: maximiza estado de personagens, relações e fatos do universo."""

    name: str = "story_heavy"

    def retrieve(
        self,
        segment: Segment,
        all_segments: list[Segment],
        memory: Any,
        config: ContextBudgetConfig,
    ) -> TranslationContext:
        # Usa balanced como base e expande story facts e relationships
        balanced = BalancedRetrievalStrategy()
        ctx = balanced.retrieve(segment, all_segments, memory, config)
        ctx.strategy_used = self.name

        if memory and hasattr(memory, "story"):
            extra_facts = memory.story.get_facts(locked_only=False)
            safe_facts = self.filter_future_facts(
                extra_facts, segment.chapter_id, config.allow_future_leakage
            )
            seen_ids = {f.id for f in ctx.story_facts}
            for f in safe_facts:
                if f.id not in seen_ids:
                    ctx.story_facts.append(f)
                    seen_ids.add(f.id)
                    ctx.scores.append(
                        ContextItemScore(
                            category="fact",
                            item_id=f.id,
                            score=0.80,
                            justification=f"Fato da obra ampliado pela estratégia story_heavy: '{f.statement}'.",
                        )
                    )
                if len(ctx.story_facts) >= config.max_facts + 5:
                    break

        ctx.reproducibility_hash = ctx.calculate_reproducibility_hash()
        return ctx


class SemanticDenseRetrievalStrategy(BaseRetrievalStrategy, ContextRetrievalStrategy):
    """Estratégia com ênfase em memória de tradução e semântica frasal."""

    name: str = "semantic_dense"

    def retrieve(
        self,
        segment: Segment,
        all_segments: list[Segment],
        memory: Any,
        config: ContextBudgetConfig,
    ) -> TranslationContext:
        balanced = BalancedRetrievalStrategy()
        ctx = balanced.retrieve(segment, all_segments, memory, config)
        ctx.strategy_used = self.name

        # Aumenta top_k de similaridade semântica
        if all_segments:
            extra_snippets = LexicalSemanticMatcher.find_similar_passages(
                target_segment=segment,
                all_segments=all_segments,
                allow_future_leakage=config.allow_future_leakage,
                min_threshold=0.10,
                top_k=config.max_semantic_snippets + 3,
            )
            ctx.semantic_snippets = extra_snippets
            # Atualiza scores
            for s in extra_snippets:
                ctx.scores.append(
                    ContextItemScore(
                        category="semantic",
                        item_id=s.segment_id,
                        score=s.similarity_score,
                        justification=s.justification,
                    )
                )

        ctx.reproducibility_hash = ctx.calculate_reproducibility_hash()
        return ctx
