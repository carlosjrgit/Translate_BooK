"""Modelos de dados canônicos para as memórias da obra e trilha de auditoria."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class MemoryRevision:
    """Registro atômico de alteração para fins de auditoria e versionamento."""

    revision_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    changed_by: str = "system"
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRevision:
        return cls(
            revision_id=data.get("revision_id", str(uuid.uuid4())[:8]),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            changed_by=data.get("changed_by", "system"),
            field_name=data.get("field_name", ""),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            reason=data.get("reason", ""),
        )


@dataclass
class CharacterEntry:
    """Entrada rica da Character Memory."""

    id: str  # ex: "char_0001"
    name: str = ""
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)
    gender: str = "neutral"  # 'feminine', 'masculine', 'neutral', 'unknown'
    relations: list[str] = field(default_factory=list)
    treatment: str = ""
    speech_style: str = ""
    linguistic_traits: list[str] = field(default_factory=list)
    evidences: list[str] = field(default_factory=list)
    confidence: float = 1.0
    first_appearance: str = ""
    occurrences: int = 0
    notes: str = ""
    history: list[MemoryRevision] = field(default_factory=list)
    project_id: Any = ""

    def __post_init__(self) -> None:
        if not self.name and self.canonical_name:
            self.name = self.canonical_name
        elif not self.canonical_name and self.name:
            self.canonical_name = self.name

    def add_revision(
        self,
        field_name: str,
        old_val: Any,
        new_val: Any,
        author: str = "user",
        reason: str = "",
    ) -> MemoryRevision:
        rev = MemoryRevision(
            changed_by=author,
            field_name=field_name,
            old_value=old_val,
            new_value=new_val,
            reason=reason,
        )
        self.history.append(rev)
        return rev


@dataclass
class GlossaryEntry:
    """Entrada do Glossário conceitual da obra."""

    source_term: str
    target_term: str
    entry_type: str = "concept"  # 'concept', 'organization', 'place', 'term'
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
    history: list[MemoryRevision] = field(default_factory=list)
    id: Any = ""
    project_id: Any = ""

    def add_revision(
        self,
        field_name: str,
        old_val: Any,
        new_val: Any,
        author: str = "user",
        reason: str = "",
    ) -> MemoryRevision:
        rev = MemoryRevision(
            changed_by=author,
            field_name=field_name,
            old_value=old_val,
            new_value=new_val,
            reason=reason,
        )
        self.history.append(rev)
        return rev


@dataclass
class TranslationMemoryEntry:
    """Entrada da Translation Memory (TM) com auditoria e controle de travamento."""

    source_term: str
    target_term: str
    context: str = ""
    origin: str = "user"  # 'user', 'madlad', 'review', 'glossary', 'analysis'
    status: str = "active"  # 'active', 'pending', 'approved', 'rejected', 'deprecated'
    locked: bool = True
    confidence: float = 1.0
    entry_type: str = "phrase"  # 'phrase', 'sentence', 'organization', etc.
    first_chapter: str = ""
    occurrences: int = 1
    history: list[MemoryRevision] = field(default_factory=list)
    id: Any = ""
    project_id: Any = ""

    @property
    def source(self) -> str:
        """Alias de conveniência para source_term."""
        return self.source_term

    @property
    def target(self) -> str:
        """Alias de conveniência para target_term."""
        return self.target_term

    def add_revision(
        self,
        field_name: str,
        old_val: Any,
        new_val: Any,
        author: str = "user",
        reason: str = "",
    ) -> MemoryRevision:
        rev = MemoryRevision(
            changed_by=author,
            field_name=field_name,
            old_value=old_val,
            new_value=new_val,
            reason=reason,
        )
        self.history.append(rev)
        return rev


@dataclass
class StyleBible:
    """Manual de estilo e diretrizes editoriais da obra."""

    narrator: str = "terceira pessoa"
    register: str = "literário contemporâneo"
    dialogue_style: str = "natural em PT-BR"
    profanity_handling: str = "preservar intensidade do original"
    predominant_treatment: str = "você"
    punctuation_standard: str = "editorial brasileiro"
    project_id: Any = ""
    tone: str = "literário"
    formality_level: str = "formal"
    custom_rules: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictReport:
    """Relatório detalhado de conflito ou colisão de tradução/aliases."""

    memory_type: str  # 'character', 'glossary', 'translation_memory', 'cross_memory'
    term_or_name: str
    existing_value: Any
    conflicting_value: Any
    reason: str
    severity: str = "error"  # 'error', 'warning'
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LockedVerificationResult:
    """Resultado da verificação de conformidade de termos travados (locked)."""

    is_compliant: bool
    total_checked: int
    violations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Alias de conveniência indicando se a validação passou sem violações."""
        return self.is_compliant

    @property
    def missing_terms(self) -> list[dict[str, Any]]:
        """Alias de conveniência para a lista de violações encontradas."""
        return self.violations

    @property
    def errors(self) -> list[dict[str, Any]]:
        """Alias de conveniência para erros de conformidade."""
        return self.violations
