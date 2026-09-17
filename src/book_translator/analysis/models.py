"""Modelos de dados para entidades, ocorrências, inferências e relações."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """Classificação taxonômica da entidade."""

    CHARACTER = "character"
    LOCATION = "location"
    ORGANIZATION = "organization"
    TITLE = "title"
    HONORIFIC = "honorific"
    RECURRENT_TERM = "recurrent_term"
    CONCEPT = "concept"


@dataclass
class EntityOccurrence:
    """Registro factual de uma ocorrência literal de entidade no texto."""

    chapter_id: str
    unit_id: str
    text: str
    line_number: int | None = None
    char_offset: int | None = None
    surrounding_snippet: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityInference:
    """Inferência analítica associada a uma entidade com comprovação e confiança."""

    inference_type: str  # 'alias_resolution', 'gender', 'relationship', 'role'
    value: str
    confidence: float  # 0.0 a 1.0
    evidence: str  # Trecho exato de texto comprobatório
    source_unit_id: str = ""
    source_chapter_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyzedEntity:
    """Entidade global identificada na obra com histórico de ocorrências e inferências."""

    id: str
    canonical_name: str
    entity_type: EntityType
    aliases: list[str] = field(default_factory=list)
    occurrences: list[EntityOccurrence] = field(default_factory=list)
    inferences: list[EntityInference] = field(default_factory=list)
    honorifics: list[str] = field(default_factory=list)
    gender: str = "unknown"  # 'feminine', 'masculine', 'neutral', 'unknown'
    is_ambiguous: bool = False
    candidate_entity_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def occurrences_count(self) -> int:
        return len(self.occurrences)

    @property
    def first_appearance_chapter(self) -> str:
        return self.occurrences[0].chapter_id if self.occurrences else ""


@dataclass
class Relationship:
    """Relação inferida entre duas entidades com evidência e confiança."""

    source_entity_id: str
    target_entity_id: str
    source_name: str
    target_name: str
    relation_type: str  # 'parent_of', 'child_of', 'sibling_of', 'spouse_of', 'ally_of', etc.
    confidence: float
    evidence: str
    source_unit_id: str = ""
    source_chapter_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
