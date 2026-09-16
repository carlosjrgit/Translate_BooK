"""Contratos e modelos para auditoria global de consistência da obra (Consistency Pass)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from book_translator.core.models import Document
from book_translator.memory.base import MemoryManagerInterface
from book_translator.qa.base import IssueSeverity


@dataclass
class ConsistencyConflict:
    """Conflito de consistência detectado entre capítulos da obra."""

    term_or_entity: str
    variants: dict[str, list[str]] = field(default_factory=dict)
    severity: IssueSeverity = IssueSeverity.SUGGESTED_FIX
    message: str = ""
    suggested_standardization: str = ""


@dataclass
class ConsistencyReport:
    """Relatório resultante da auditoria de consistência global da obra."""

    total_segments_audited: int
    conflicts: list[ConsistencyConflict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0


@runtime_checkable
class ConsistencyCheckerInterface(Protocol):
    """Protocolo formal para o auditor global de consistência."""

    def audit(
        self,
        document: Document,
        memory_manager: MemoryManagerInterface,
    ) -> ConsistencyReport:
        """Examina toda a obra traduzida buscando divergências terminológicas e nominais."""
        ...
