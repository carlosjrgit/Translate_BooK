"""Contratos e modelos canônicos para recuperação seletiva de contexto (Context Retrieval)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from book_translator.context.models import (
    ContextBudgetConfig,
    ContextItemScore,
    ContextMetrics,
    SemanticSnippet,
)
from book_translator.core.models import Segment
from book_translator.memory.base import (
    CharacterEntry,
    GlossaryEntry,
    PersistentFact,
    StoryRelationship,
    TranslationMemoryEntry,
)


@dataclass
class TranslationContext:
    """Contexto útil empacotado para alimentar a tradução de um segmento específico."""

    segment_id: str
    preceding_text: list[str] = field(default_factory=list)
    succeeding_text: list[str] = field(default_factory=list)
    chapter_summary: str = ""
    active_characters: list[CharacterEntry] = field(default_factory=list)
    relevant_glossary: list[GlossaryEntry] = field(default_factory=list)
    established_translations: list[TranslationMemoryEntry] = field(default_factory=list)
    relevant_relationships: list[StoryRelationship] = field(default_factory=list)
    story_facts: list[PersistentFact] = field(default_factory=list)
    semantic_snippets: list[SemanticSnippet] = field(default_factory=list)
    scores: list[ContextItemScore] = field(default_factory=list)
    strategy_used: str = "balanced"
    reproducibility_hash: str = ""
    future_leakage_prevented: bool = True
    metrics: ContextMetrics | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reproducibility_hash:
            self.reproducibility_hash = self.calculate_reproducibility_hash()

    def get_score(self, item_id: str) -> float | None:
        """Retorna o score de relevância atribuído a um item do contexto."""
        for s in self.scores:
            if s.item_id.lower() == item_id.lower():
                return s.score
        return None

    def get_justification(self, item_id: str) -> str | None:
        """Retorna a justificativa de inclusão de um item no contexto."""
        for s in self.scores:
            if s.item_id.lower() == item_id.lower():
                return s.justification
        return None

    def get_all_justifications(self) -> list[tuple[str, str, float, str]]:
        """Retorna lista de tuplas (categoria, item_id, score, justificativa)."""
        return [(s.category, s.item_id, s.score, s.justification) for s in self.scores]

    def calculate_reproducibility_hash(self) -> str:
        """Calcula um hash criptográfico estável e determinístico que garante rastreabilidade total."""
        canonical_dict = {
            "segment_id": self.segment_id,
            "preceding_text": self.preceding_text,
            "succeeding_text": self.succeeding_text,
            "chapter_summary": self.chapter_summary,
            "active_characters": sorted([c.id for c in self.active_characters]),
            "relevant_glossary": sorted([g.source_term.lower() for g in self.relevant_glossary]),
            "established_translations": sorted(
                [t.source_term.lower() for t in self.established_translations]
            ),
            "relevant_relationships": sorted([r.id for r in self.relevant_relationships]),
            "story_facts": sorted([f.id for f in self.story_facts]),
            "semantic_snippets": sorted([s.segment_id for s in self.semantic_snippets]),
            "scores": sorted([(s.category, s.item_id, round(s.score, 4)) for s in self.scores]),
            "strategy_used": self.strategy_used,
            "future_leakage_prevented": self.future_leakage_prevented,
        }
        serialized = json.dumps(canonical_dict, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def compact_summary(self) -> str:
        """Retorna representação textual enxuta e cirúrgica para motores de tradução como MADLAD-400."""
        lines: list[str] = []
        if self.chapter_summary:
            lines.append(f"[Capítulo: {self.chapter_summary}]")
        if self.active_characters:
            names = [c.name for c in self.active_characters if c.name]
            if names:
                lines.append(f"[Personagens: {', '.join(names)}]")
        if self.relevant_glossary:
            terms = [f"{g.source_term} -> {g.target_term}" for g in self.relevant_glossary]
            lines.append(f"[Glossário: {', '.join(terms)}]")
        if self.story_facts:
            facts = [f.statement for f in self.story_facts if f.statement]
            if facts:
                lines.append(f"[Fatos: {'; '.join(facts[:2])}]")
        if self.preceding_text:
            lines.append(f"[Anterior: {' '.join(self.preceding_text[-1:])}]")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialização completa para armazenamento e transmissão."""
        return {
            "segment_id": self.segment_id,
            "preceding_text": self.preceding_text,
            "succeeding_text": self.succeeding_text,
            "chapter_summary": self.chapter_summary,
            "active_characters": [c.__dict__ for c in self.active_characters],
            "relevant_glossary": [g.__dict__ for g in self.relevant_glossary],
            "established_translations": [t.__dict__ for t in self.established_translations],
            "relevant_relationships": [
                r.to_dict() if hasattr(r, "to_dict") else r.__dict__
                for r in self.relevant_relationships
            ],
            "story_facts": [
                f.to_dict() if hasattr(f, "to_dict") else f.__dict__ for f in self.story_facts
            ],
            "semantic_snippets": [s.to_dict() for s in self.semantic_snippets],
            "scores": [s.to_dict() for s in self.scores],
            "strategy_used": self.strategy_used,
            "reproducibility_hash": self.reproducibility_hash,
            "future_leakage_prevented": self.future_leakage_prevented,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "extra_metadata": self.extra_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranslationContext:
        """Desserialização segura com preservação de retrocompatibilidade."""
        chars = [
            CharacterEntry.from_dict(c)
            if isinstance(c, dict) and hasattr(CharacterEntry, "from_dict")
            else c
            for c in data.get("active_characters", [])
        ]
        gloss = [
            GlossaryEntry.from_dict(g)
            if isinstance(g, dict) and hasattr(GlossaryEntry, "from_dict")
            else g
            for g in data.get("relevant_glossary", [])
        ]
        tm = [
            TranslationMemoryEntry.from_dict(t)
            if isinstance(t, dict) and hasattr(TranslationMemoryEntry, "from_dict")
            else t
            for t in data.get("established_translations", [])
        ]
        rels = [
            StoryRelationship.from_dict(r)
            if isinstance(r, dict) and hasattr(StoryRelationship, "from_dict")
            else r
            for r in data.get("relevant_relationships", [])
        ]
        facts = [
            PersistentFact.from_dict(f)
            if isinstance(f, dict) and hasattr(PersistentFact, "from_dict")
            else f
            for f in data.get("story_facts", [])
        ]
        snippets = [
            SemanticSnippet.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("semantic_snippets", [])
        ]
        scores = [
            ContextItemScore.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("scores", [])
        ]
        metrics_data = data.get("metrics")
        metrics_obj = ContextMetrics(**metrics_data) if isinstance(metrics_data, dict) else None

        return cls(
            segment_id=str(data.get("segment_id", "")),
            preceding_text=list(data.get("preceding_text", [])),
            succeeding_text=list(data.get("succeeding_text", [])),
            chapter_summary=str(data.get("chapter_summary", "")),
            active_characters=chars,
            relevant_glossary=gloss,
            established_translations=tm,
            relevant_relationships=rels,
            story_facts=facts,
            semantic_snippets=snippets,
            scores=scores,
            strategy_used=str(data.get("strategy_used", "balanced")),
            reproducibility_hash=str(data.get("reproducibility_hash", "")),
            future_leakage_prevented=bool(data.get("future_leakage_prevented", True)),
            metrics=metrics_obj,
            extra_metadata=dict(data.get("extra_metadata", {})),
        )


@runtime_checkable
class ContextRetrievalStrategy(Protocol):
    """Protocolo formal para estratégias substituíveis de recuperação de contexto."""

    name: str

    def retrieve(
        self,
        segment: Segment,
        all_segments: list[Segment],
        memory: Any,
        config: ContextBudgetConfig,
    ) -> TranslationContext:
        """Executa a recuperação seletiva de contexto para o segmento."""
        ...


@runtime_checkable
class ContextRetrievalInterface(Protocol):
    """Protocolo formal para o motor unificado de recuperação de contexto."""

    def retrieve_context(
        self,
        segment: Segment,
        all_segments: list[Segment] | None = None,
        config: ContextBudgetConfig | None = None,
    ) -> TranslationContext:
        """Determina e compõe o contexto relevante para traduzir o segmento."""
        ...
