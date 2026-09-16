"""Módulo de memórias da obra (Characters, TM, Glossary, Style Bible)."""

from __future__ import annotations

from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    MemoryManagerInterface,
    StyleBible,
    TranslationMemoryEntry,
)

__all__ = [
    "CharacterEntry",
    "TranslationMemoryEntry",
    "GlossaryEntry",
    "StyleBible",
    "MemoryManagerInterface",
]
