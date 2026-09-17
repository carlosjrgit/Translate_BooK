"""Estruturas e contratos para as memórias da obra (Characters, TM, Glossary, Style Bible)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from book_translator.memory.models import (
    CharacterEntry,
    ConflictReport,
    GlossaryEntry,
    LockedVerificationResult,
    MemoryRevision,
    StyleBible,
    TranslationMemoryEntry,
)


@runtime_checkable
class MemoryManagerInterface(Protocol):
    """Protocolo central para gerenciamento unificado das memórias do projeto."""

    def add_character(self, character: CharacterEntry) -> None: ...

    def get_character(self, character_id: str) -> CharacterEntry | None: ...

    def add_tm_entry(self, entry: TranslationMemoryEntry) -> None: ...

    def get_tm_entry(self, source_term: str) -> TranslationMemoryEntry | None: ...

    def add_glossary_entry(self, entry: GlossaryEntry) -> None: ...

    def get_glossary_entry(self, source_term: str) -> GlossaryEntry | None: ...

    def get_style_bible(self) -> StyleBible: ...


__all__ = [
    "CharacterEntry",
    "TranslationMemoryEntry",
    "GlossaryEntry",
    "StyleBible",
    "MemoryRevision",
    "ConflictReport",
    "LockedVerificationResult",
    "MemoryManagerInterface",
]
