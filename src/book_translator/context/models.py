"""Modelos de dados para o mecanismo seletivo de recuperação de contexto."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContextItemScore:
    """Pontuação numérica acompanhada de justificativa para cada elemento contextual."""

    category: str  # 'preceding', 'succeeding', 'summary', 'character', 'relationship', 'glossary', 'tm', 'semantic', 'fact', 'pronoun'
    item_id: str
    score: float  # 0.0 a 1.0
    justification: str
    is_future: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextItemScore:
        return cls(
            category=str(data.get("category", "")),
            item_id=str(data.get("item_id", "")),
            score=float(data.get("score", 0.0)),
            justification=str(data.get("justification", "")),
            is_future=bool(data.get("is_future", False)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class SemanticSnippet:
    """Trecho textual anterior com relação semântica relevante ao segmento atual."""

    segment_id: str
    source_text: str
    translated_text: str = ""
    similarity_score: float = 0.0
    justification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticSnippet:
        return cls(
            segment_id=str(data.get("segment_id", "")),
            source_text=str(data.get("source_text", "")),
            translated_text=str(data.get("translated_text", "")),
            similarity_score=float(data.get("similarity_score", 0.0)),
            justification=str(data.get("justification", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ContextBudgetConfig:
    """Configurações de limites e janelas para o mecanismo de recuperação."""

    max_tokens: int = 800
    window_before: int = 2
    window_after: int = 1
    allow_future_leakage: bool = False
    min_similarity_threshold: float = 0.15
    max_semantic_snippets: int = 3
    max_glossary_terms: int = 10
    max_tm_matches: int = 5
    max_characters: int = 6
    max_facts: int = 5
    mode: str = "standard"  # 'standard', 'global_review', 'minimal', 'story_heavy'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextBudgetConfig:
        return cls(
            max_tokens=int(data.get("max_tokens", 800)),
            window_before=int(data.get("window_before", 2)),
            window_after=int(data.get("window_after", 1)),
            allow_future_leakage=bool(data.get("allow_future_leakage", False)),
            min_similarity_threshold=float(data.get("min_similarity_threshold", 0.15)),
            max_semantic_snippets=int(data.get("max_semantic_snippets", 3)),
            max_glossary_terms=int(data.get("max_glossary_terms", 10)),
            max_tm_matches=int(data.get("max_tm_matches", 5)),
            max_characters=int(data.get("max_characters", 6)),
            max_facts=int(data.get("max_facts", 5)),
            mode=str(data.get("mode", "standard")),
        )


@dataclass
class ContextMetrics:
    """Métricas consolidadas de qualidade e cobertura do contexto recuperado."""

    overall_relevance_score: float = 0.0
    total_tokens_estimated: int = 0
    budget_utilization_pct: float = 0.0
    items_count_by_category: dict[str, int] = field(default_factory=dict)
    future_items_blocked_count: int = 0
    reproducibility_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
