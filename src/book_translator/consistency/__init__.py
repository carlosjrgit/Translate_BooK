"""Módulo de auditoria de consistência global entre capítulos."""

from __future__ import annotations

from book_translator.consistency.base import (
    ConsistencyCheckerInterface,
    ConsistencyConflict,
    ConsistencyReport,
)

__all__ = [
    "ConsistencyConflict",
    "ConsistencyReport",
    "ConsistencyCheckerInterface",
]
