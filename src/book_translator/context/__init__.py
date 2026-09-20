"""Módulo de recuperação seletiva de contexto para tradução."""

from __future__ import annotations

from book_translator.context.base import (
    ContextRetrievalInterface,
    ContextRetrievalStrategy,
    TranslationContext,
)
from book_translator.context.engine import ContextRetrievalEngine
from book_translator.context.models import (
    ContextBudgetConfig,
    ContextItemScore,
    ContextMetrics,
    SemanticSnippet,
)
from book_translator.context.resolvers import (
    AliasResolver,
    LexicalSemanticMatcher,
    PronounResolver,
    RecurringTermMatcher,
)
from book_translator.context.strategies import (
    BalancedRetrievalStrategy,
    MinimalRetrievalStrategy,
    SemanticDenseRetrievalStrategy,
    StoryHeavyRetrievalStrategy,
)

__all__ = [
    "TranslationContext",
    "ContextRetrievalInterface",
    "ContextRetrievalStrategy",
    "ContextRetrievalEngine",
    "ContextItemScore",
    "SemanticSnippet",
    "ContextBudgetConfig",
    "ContextMetrics",
    "BalancedRetrievalStrategy",
    "MinimalRetrievalStrategy",
    "StoryHeavyRetrievalStrategy",
    "SemanticDenseRetrievalStrategy",
    "PronounResolver",
    "AliasResolver",
    "RecurringTermMatcher",
    "LexicalSemanticMatcher",
]
