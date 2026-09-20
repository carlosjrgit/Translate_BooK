"""Módulo de auditoria de consistência global entre capítulos (Consistency Pass)."""

from __future__ import annotations

from book_translator.consistency.base import (
    ConsistencyCheckerInterface,
    ConsistencyConflict,
    ConsistencyFixAuditRecord,
    ConsistencyReport,
    GlobalConsistencyReport,
    OccurrenceLocation,
)
from book_translator.consistency.checker import GlobalConsistencyChecker

__all__ = [
    "OccurrenceLocation",
    "ConsistencyConflict",
    "ConsistencyFixAuditRecord",
    "ConsistencyReport",
    "GlobalConsistencyReport",
    "ConsistencyCheckerInterface",
    "GlobalConsistencyChecker",
]
