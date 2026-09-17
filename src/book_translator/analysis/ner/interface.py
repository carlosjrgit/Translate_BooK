"""Protocolo e contratos formais para motores de Reconhecimento de Entidades Nomeadas (NER)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from book_translator.analysis.models import EntityType


@dataclass
class RawEntityMention:
    """Menção literal bruta de entidade encontrada no texto durante a extração de NER."""

    text: str
    entity_type: EntityType
    confidence: float
    start_char: int
    end_char: int
    honorific: str | None = None
    chapter_id: str = ""
    unit_id: str = ""
    snippet: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class NERInterface(Protocol):
    """Protocolo formal para motores de NER plugáveis e substituíveis."""

    @property
    def engine_name(self) -> str:
        """Nome identificador do motor (ex: 'heuristic', 'spacy', 'bert')."""
        ...

    def extract_entities(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[RawEntityMention]:
        """Extrai entidades nomeadas do texto fornecido com nível de confiança."""
        ...
