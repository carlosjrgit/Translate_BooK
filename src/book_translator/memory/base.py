"""Estruturas e contratos para as memórias da obra (Characters, TM, Glossary, Style Bible)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class CharacterEntry:
    """Entrada da Character Memory."""

    id: str  # ex: "character_0042"
    name: str
    aliases: list[str] = field(default_factory=list)
    gender: str = "neutral"  # 'feminine', 'masculine', 'neutral'
    relations: list[str] = field(default_factory=list)
    speech_style: str = ""
    linguistic_traits: list[str] = field(default_factory=list)
    first_appearance: str = ""
    occurrences: int = 0
    notes: str = ""


@dataclass
class TranslationMemoryEntry:
    """Entrada da Translation Memory (termos e expressões com tradução travada)."""

    source_term: str
    target_term: str
    entry_type: str = "phrase"  # 'phrase', 'organization', 'place', etc.
    locked: bool = True
    first_chapter: str = ""
    occurrences: int = 1


@dataclass
class GlossaryEntry:
    """Entrada do Glossário conceitual da obra."""

    source_term: str
    target_term: str
    entry_type: str = "concept"
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    case_sensitive: bool = False
    locked: bool = True
    gender: str = ""
    plural: str = ""
    context: str = ""
    first_occurrence: str = ""
    occurrences: int = 0
    notes: str = ""


@dataclass
class StyleBible:
    """Manual de estilo e diretrizes editoriais da obra."""

    narrator: str = "terceira pessoa"
    register: str = "literário contemporâneo"
    dialogue_style: str = "natural em PT-BR"
    profanity_handling: str = "preservar intensidade do original"
    predominant_treatment: str = "você"
    punctuation_standard: str = "editorial brasileiro"
    metadata: dict[str, Any] = field(default_factory=dict)


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
