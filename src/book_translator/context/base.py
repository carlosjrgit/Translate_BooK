"""Contratos e modelos para recuperação seletiva de contexto (Context Retrieval)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from book_translator.core.models import Segment
from book_translator.memory.base import CharacterEntry, GlossaryEntry, TranslationMemoryEntry


@dataclass
class TranslationContext:
    """Contexto útil empacotado para alimentar a tradução de um segmento específico."""

    segment_id: str
    preceding_text: list[str] = field(default_factory=list)
    succeeding_text: list[str] = field(default_factory=list)
    chapter_summary: str = ""
    active_characters: list[CharacterEntry] = field(default_factory=list)
    relevant_glossary: list[GlossaryEntry] = field(default_factory=list)
    established_translations: list[TranslationMemoryEntry] = field(default_factory=list)
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ContextRetrievalInterface(Protocol):
    """Protocolo formal para o mecanismo seletivo de recuperação de contexto."""

    def retrieve_context(self, segment: Segment) -> TranslationContext:
        """Determina e compõe o contexto relevante para traduzir o segmento."""
        ...
