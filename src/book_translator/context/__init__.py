"""Módulo de recuperação seletiva de contexto para tradução."""

from __future__ import annotations

from book_translator.context.base import (
    ContextRetrievalInterface,
    TranslationContext,
)

__all__ = ["TranslationContext", "ContextRetrievalInterface"]
