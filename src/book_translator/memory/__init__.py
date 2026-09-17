"""Módulo de memórias da obra (Characters, TM, Glossary, Style Bible)."""

from __future__ import annotations

from book_translator.memory.base import (
    CharacterEntry,
    ConflictReport,
    GlossaryEntry,
    LockedVerificationResult,
    MemoryManagerInterface,
    MemoryRevision,
    StyleBible,
    TranslationMemoryEntry,
)
from book_translator.memory.character_memory import CharacterMemory
from book_translator.memory.glossary import Glossary
from book_translator.memory.manager import MemoryManager
from book_translator.memory.translation_memory import TranslationMemory

__all__ = [
    "CharacterEntry",
    "TranslationMemoryEntry",
    "GlossaryEntry",
    "StyleBible",
    "MemoryRevision",
    "ConflictReport",
    "LockedVerificationResult",
    "CharacterMemory",
    "Glossary",
    "TranslationMemory",
    "MemoryManager",
    "MemoryManagerInterface",
]
