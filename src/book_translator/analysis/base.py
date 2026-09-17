"""Contratos e modelos para a análise global prévia da obra."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from book_translator.analysis.models import AnalyzedEntity, Relationship
from book_translator.core.models import Document


@dataclass
class AnalysisReport:
    """Relatório resultante da varredura analítica preliminar da obra."""

    entities: list[AnalyzedEntity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    recurrent_concepts: list[str] = field(default_factory=list)
    detected_characters: list[dict[str, Any]] = field(default_factory=list)
    detected_locations: list[str] = field(default_factory=list)
    detected_organizations: list[str] = field(default_factory=list)
    frequent_terms: list[tuple[str, int]] = field(default_factory=list)
    predominant_narrator: str = "unknown"
    formality_level: str = "neutral"
    estimated_tone: str = "neutral"
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AnalyzerInterface(Protocol):
    """Protocolo formal para analisadores globais da obra."""

    def analyze(self, document: Document) -> AnalysisReport:
        """Executa a análise textual global antes da tradução."""
        ...
