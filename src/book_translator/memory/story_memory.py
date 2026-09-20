"""Memória narrativa e contextual da obra (Story / Context Memory).

Registra de forma estruturada:
- Resumos por capítulo/seção;
- Estado evolutivo de personagens;
- Relações ativas entre personagens;
- Eventos relevantes do enredo;
- Cronologia (ordem narrativa vs. ordem cronológica no universo);
- Fatos persistentes (lore, regras do mundo, atributos imutáveis);
- Referências cruzadas (foreshadowing, callbacks).

Projetado especificamente para seleção cirúrgica de contexto e validações
determinísticas de QA para modelos não-conversacionais como MADLAD-400.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from book_translator.errors import LockedTermError
from book_translator.logging import get_logger

logger = get_logger("memory.story_memory")


@dataclass
class ChapterSummary:
    """Resumo estruturado de um capítulo ou seção."""

    id: str
    unit_id: str
    summary_text: str
    unit_type: str = "chapter"  # 'chapter' ou 'section'
    title: str = ""
    key_events: list[str] = field(default_factory=list)
    characters_present: list[str] = field(default_factory=list)
    order_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return self.summary_text

    @property
    def key_developments(self) -> list[str]:
        return self.key_events

    @property
    def open_questions(self) -> list[str]:
        return list(self.metadata.get("open_questions", []))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "summary_text": self.summary_text,
            "unit_type": self.unit_type,
            "title": self.title,
            "key_events": self.key_events,
            "characters_present": self.characters_present,
            "order_index": self.order_index,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChapterSummary:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            unit_id=data.get("unit_id", ""),
            summary_text=data.get("summary_text", ""),
            unit_type=data.get("unit_type", "chapter"),
            title=data.get("title", ""),
            key_events=list(data.get("key_events", [])),
            characters_present=list(data.get("characters_present", [])),
            order_index=int(data.get("order_index", 0)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class StoryRelationship:
    """Relação interpessoal ativa entre personagens com rastreabilidade de evidência e inferência."""

    id: str
    source_character_id: str
    target_character_id: str
    relation_type: str
    description: str = ""
    chapter_id: str = ""
    evidence: str = ""
    confidence: float = 1.0
    is_inferred: bool = False
    source_type: str = "explicit"  # 'explicit' ou 'inferred'
    metadata: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_character_id": self.source_character_id,
            "target_character_id": self.target_character_id,
            "relation_type": self.relation_type,
            "description": self.description,
            "chapter_id": self.chapter_id,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "is_inferred": self.is_inferred,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryRelationship:
        is_inf = bool(data.get("is_inferred", False))
        source_type = data.get("source_type", "inference" if is_inf else "explicit")
        if source_type in ("inferred", "inference"):
            source_type = "inference"
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            source_character_id=data.get("source_character_id", ""),
            target_character_id=data.get("target_character_id", ""),
            relation_type=data.get("relation_type", ""),
            description=data.get("description", ""),
            chapter_id=data.get("chapter_id", ""),
            evidence=data.get("evidence", ""),
            confidence=float(data.get("confidence", 1.0)),
            is_inferred=is_inf,
            source_type=source_type,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CharacterState:
    """Estado circunstancial e evolutivo de um personagem em um ponto da narrativa."""

    id: str
    character_id: str
    chapter_id: str
    alive_status: str = "alive"  # 'alive', 'deceased', 'missing', 'injured', 'unknown'
    location: str = ""
    emotional_state: str = ""
    role_or_title: str = ""
    known_facts: list[str] = field(default_factory=list)
    order_index: int = 0
    evidence: str = ""
    confidence: float = 1.0
    is_inferred: bool = False
    source_type: str = "explicit"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> str:
        return self.alive_status

    @property
    def physical_condition(self) -> str:
        return str(self.metadata.get("physical_condition", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "chapter_id": self.chapter_id,
            "alive_status": self.alive_status,
            "location": self.location,
            "emotional_state": self.emotional_state,
            "role_or_title": self.role_or_title,
            "known_facts": self.known_facts,
            "order_index": self.order_index,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "is_inferred": self.is_inferred,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterState:
        is_inf = bool(data.get("is_inferred", False))
        source_type = data.get("source_type", "inference" if is_inf else "explicit")
        if source_type in ("inferred", "inference"):
            source_type = "inference"
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            character_id=data.get("character_id", ""),
            chapter_id=data.get("chapter_id", ""),
            alive_status=data.get("alive_status", data.get("state", "alive")),
            location=data.get("location", ""),
            emotional_state=data.get("emotional_state", ""),
            role_or_title=data.get("role_or_title", ""),
            known_facts=list(data.get("known_facts", [])),
            order_index=int(data.get("order_index", 0)),
            evidence=data.get("evidence", ""),
            confidence=float(data.get("confidence", 1.0)),
            is_inferred=is_inf,
            source_type=source_type,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class StoryEvent:
    """Evento relevante da trama na cronologia da obra."""

    id: str
    chapter_id: str
    description: str
    unit_id: str = ""
    characters_involved: list[str] = field(default_factory=list)
    significance: str = "major"  # 'major', 'turning_point', 'minor', 'background'
    narrative_order: int = 0  # Posição na ordem de leitura
    chronological_order: int = 0  # Posição na linha do tempo in-universe
    evidence: str = ""
    confidence: float = 1.0
    is_inferred: bool = False
    source_type: str = "explicit"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return str(self.metadata.get("title", self.description[:30]))

    @property
    def order_index(self) -> int:
        return self.narrative_order

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chapter_id": self.chapter_id,
            "description": self.description,
            "unit_id": self.unit_id,
            "characters_involved": self.characters_involved,
            "significance": self.significance,
            "narrative_order": self.narrative_order,
            "chronological_order": self.chronological_order,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "is_inferred": self.is_inferred,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryEvent:
        is_inf = bool(data.get("is_inferred", False))
        source_type = data.get("source_type", "inference" if is_inf else "explicit")
        if source_type in ("inferred", "inference"):
            source_type = "inference"
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            chapter_id=data.get("chapter_id", ""),
            description=data.get("description", ""),
            unit_id=data.get("unit_id", ""),
            characters_involved=list(data.get("characters_involved", [])),
            significance=data.get("significance", "major"),
            narrative_order=int(data.get("narrative_order", data.get("order_index", 0))),
            chronological_order=int(data.get("chronological_order", data.get("order_index", 0))),
            evidence=data.get("evidence", ""),
            confidence=float(data.get("confidence", 1.0)),
            is_inferred=is_inf,
            source_type=source_type,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PersistentFact:
    """Fato imutável ou verdade duradoura sobre o universo ou personagens da obra."""

    id: str
    statement: str
    category: str = (
        "world_rule"  # 'lore', 'world_rule', 'character_attribute', 'setting', 'plot_fact'
    )
    subject_entity_ids: list[str] = field(default_factory=list)
    evidence: str = ""
    confidence: float = 1.0
    locked: bool = False
    is_inferred: bool = False
    source_type: str = "explicit"
    occurrences: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fact(self) -> str:
        return self.statement

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "category": self.category,
            "subject_entity_ids": self.subject_entity_ids,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "locked": self.locked,
            "is_inferred": self.is_inferred,
            "source_type": self.source_type,
            "occurrences": self.occurrences,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersistentFact:
        is_inf = bool(data.get("is_inferred", False))
        source_type = data.get("source_type", "inference" if is_inf else "explicit")
        if source_type in ("inferred", "inference"):
            source_type = "inference"
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            statement=data.get("statement", data.get("fact", "")),
            category=data.get("category", "world_rule"),
            subject_entity_ids=list(data.get("subject_entity_ids", [])),
            evidence=data.get("evidence", ""),
            confidence=float(data.get("confidence", 1.0)),
            locked=bool(data.get("locked", False)),
            is_inferred=is_inf,
            source_type=source_type,
            occurrences=list(data.get("occurrences", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class StoryCrossReference:
    """Vínculo explícito entre trechos distantes do documento."""

    id: str
    source_unit_id: str
    target_unit_id: str
    description: str
    ref_type: str = "callback"  # 'foreshadowing', 'callback', 'parallel', 'revelation', 'citation'
    evidence: str = ""
    confidence: float = 1.0
    is_inferred: bool = False
    source_type: str = "explicit"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_unit_id": self.source_unit_id,
            "target_unit_id": self.target_unit_id,
            "description": self.description,
            "ref_type": self.ref_type,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "is_inferred": self.is_inferred,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryCrossReference:
        is_inf = bool(data.get("is_inferred", False))
        source_type = data.get("source_type", "inference" if is_inf else "explicit")
        if source_type in ("inferred", "inference"):
            source_type = "inference"
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            source_unit_id=data.get("source_unit_id", data.get("source_chapter", "")),
            target_unit_id=data.get("target_unit_id", data.get("target_chapter", "")),
            description=data.get("description", ""),
            ref_type=data.get("ref_type", "callback"),
            evidence=data.get("evidence", ""),
            confidence=float(data.get("confidence", 1.0)),
            is_inferred=is_inf,
            source_type=source_type,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class QAStoryAnomaly:
    """Registro de inconsistência narrativa para auditoria de QA."""

    anomaly_type: str
    severity: str  # 'error', 'warning', 'info'
    message: str
    chapter_id: str = ""
    character_id: str = ""
    snippet: str = ""
    evidence: str = ""
    conflicting_with: str = ""
    order_index: int = 0
    entity_id: str = ""

    def __post_init__(self) -> None:
        if self.entity_id and not self.character_id:
            self.character_id = self.entity_id
        elif self.character_id and not self.entity_id:
            self.entity_id = self.character_id

    @property
    def description(self) -> str:
        return self.message


@dataclass
class StoryContextSnapshot:
    """Recorte cirúrgico e compacto de contexto preparado para um segmento de tradução."""

    chapter_id: str
    unit_id: str
    chapter_summary: str = ""
    active_character_states: list[CharacterState] = field(default_factory=list)
    active_relationships: list[Any] = field(default_factory=list)
    recent_events: list[StoryEvent] = field(default_factory=list)
    relevant_facts: list[PersistentFact] = field(default_factory=list)
    cross_references: list[StoryCrossReference] = field(default_factory=list)
    inferred_items_count: int = 0
    explicit_items_count: int = 0

    @property
    def active_facts(self) -> list[PersistentFact]:
        return self.relevant_facts

    @property
    def active_events(self) -> list[StoryEvent]:
        return self.recent_events

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "unit_id": self.unit_id,
            "chapter_summary": self.chapter_summary,
            "active_character_states": [s.to_dict() for s in self.active_character_states],
            "active_relationships": [
                r.to_dict() if hasattr(r, "to_dict") else r for r in self.active_relationships
            ],
            "recent_events": [e.to_dict() for e in self.recent_events],
            "relevant_facts": [f.to_dict() for f in self.relevant_facts],
            "cross_references": [r.to_dict() for r in self.cross_references],
            "inferred_items_count": self.inferred_items_count,
            "explicit_items_count": self.explicit_items_count,
        }


class StoryMemory:
    """Gerenciador central da memória narrativa e contextual da obra."""

    def __init__(self, project_id: str = "") -> None:
        self.project_id: str = project_id
        self._summaries: dict[str, ChapterSummary] = {}  # unit_id -> ChapterSummary
        self._character_states: dict[
            str, list[CharacterState]
        ] = {}  # char_id -> list[CharacterState]
        self._relationships: list[StoryRelationship] = []
        self._events: dict[str, StoryEvent] = {}  # event_id -> StoryEvent
        self._facts: dict[str, PersistentFact] = {}  # fact_id -> PersistentFact
        self._cross_references: dict[str, StoryCrossReference] = {}  # ref_id -> CrossReference

    # -------------------------------------------------------------------------
    # Resumos de Capítulos e Seções
    # -------------------------------------------------------------------------

    def record_summary(
        self,
        unit_id: str = "",
        summary_text: str = "",
        title: str = "",
        unit_type: str = "chapter",
        key_events: list[str] | None = None,
        characters_present: list[str] | None = None,
        order_index: int = 0,
        metadata: dict[str, Any] | None = None,
        chapter_id: str = "",
        summary: str = "",
        section_id: str = "",
        key_developments: list[str] | None = None,
        open_questions: list[str] | None = None,
    ) -> ChapterSummary:
        """Registra ou atualiza o resumo de um capítulo ou seção."""
        uid = unit_id or section_id or chapter_id
        summary_id = f"sum_{uid}"
        stext = summary_text or summary
        events = list(key_events or key_developments or [])
        meta = dict(metadata or {})
        if open_questions:
            meta["open_questions"] = list(open_questions)
        if section_id:
            meta["section_id"] = section_id
        if chapter_id:
            meta["chapter_id"] = chapter_id

        summary_obj = ChapterSummary(
            id=summary_id,
            unit_id=uid,
            summary_text=stext,
            unit_type=unit_type,
            title=title,
            key_events=events,
            characters_present=list(characters_present or []),
            order_index=order_index,
            metadata=meta,
        )
        self._summaries[uid] = summary_obj
        if chapter_id and chapter_id != uid:
            self._summaries[chapter_id] = summary_obj
        return summary_obj

    def get_summary(self, unit_id: str) -> ChapterSummary | None:
        """Recupera o resumo de uma unidade específica."""
        return self._summaries.get(unit_id)

    def get_chapter_summary(self, chapter_id: str) -> ChapterSummary | None:
        """Recupera o resumo de um capítulo específico."""
        res = self.get_summary(chapter_id) or self._summaries.get(f"sum_{chapter_id}")
        if res:
            return res
        for s in self._summaries.values():
            if s.metadata.get("chapter_id") == chapter_id or s.unit_id == chapter_id:
                return s
        return None

    def get_all_summaries(self, unit_type: str | None = None) -> list[ChapterSummary]:
        """Retorna todos os resumos ordenados por índice de leitura."""
        sums = list(self._summaries.values())
        if unit_type:
            sums = [s for s in sums if s.unit_type == unit_type]
        return sorted(sums, key=lambda s: s.order_index)

    # -------------------------------------------------------------------------
    # Estado Evolutivo de Personagens
    # -------------------------------------------------------------------------

    def record_character_state(
        self,
        character_id: str,
        chapter_id: str,
        alive_status: str = "alive",
        location: str = "",
        emotional_state: str = "",
        role_or_title: str = "",
        known_facts: list[str] | None = None,
        order_index: int = 0,
        evidence: str = "",
        confidence: float = 1.0,
        is_inferred: bool = False,
        source_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        state: str = "",
        physical_condition: str = "",
    ) -> CharacterState:
        """Registra o estado de um personagem em determinado capítulo."""
        state_id = f"state_{character_id}_{chapter_id}"
        actual_source_type = source_type or ("inference" if is_inferred else "explicit")
        if actual_source_type in ("inferred", "inference"):
            actual_source_type = "inference"
            is_inferred = True

        final_status = alive_status
        if state:
            final_status = "deceased" if state.lower() == "dead" else state

        meta = dict(metadata or {})
        if physical_condition:
            meta["physical_condition"] = physical_condition

        st = CharacterState(
            id=state_id,
            character_id=character_id,
            chapter_id=chapter_id,
            alive_status=final_status,
            location=location,
            emotional_state=emotional_state,
            role_or_title=role_or_title,
            known_facts=list(known_facts or []),
            order_index=order_index,
            evidence=evidence,
            confidence=confidence,
            is_inferred=is_inferred,
            source_type=actual_source_type,
            metadata=meta,
        )
        if character_id not in self._character_states:
            self._character_states[character_id] = []
        state_id = f"state_{character_id}_{chapter_id}_{order_index}_{len(self._character_states[character_id])}"
        st.id = state_id
        existing = [
            s
            for s in self._character_states[character_id]
            if s.chapter_id == chapter_id
            and s.order_index == order_index
            and s.location == location
            and s.alive_status == final_status
        ]
        if existing:
            self._character_states[character_id].remove(existing[0])
        self._character_states[character_id].append(st)
        self._character_states[character_id].sort(key=lambda s: s.order_index)
        return st

    def get_character_state(self, character_id: str, chapter_id: str) -> CharacterState | None:
        """Retorna o estado do personagem em um capítulo exato."""
        states = self._character_states.get(character_id, [])
        for s in states:
            if s.chapter_id == chapter_id:
                return s
        return None

    def get_character_states(
        self,
        character_id: str | None = None,
        chapter_id: str | None = None,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[CharacterState]:
        """Retorna lista de estados de personagens com suporte a filtros de inferência."""
        if character_id:
            states = list(self._character_states.get(character_id, []))
        else:
            states = [st for sublist in self._character_states.values() for st in sublist]

        if chapter_id:
            states = [s for s in states if s.chapter_id == chapter_id]
        if explicit_only:
            states = [s for s in states if not s.is_inferred]
        elif inferred_only:
            states = [s for s in states if s.is_inferred]
        return sorted(states, key=lambda s: s.order_index)

    def get_latest_character_state(
        self, character_id: str, up_to_order_index: int | None = None
    ) -> CharacterState | None:
        """Retorna o estado mais recente do personagem até um determinado ponto da narrativa."""
        states = self._character_states.get(character_id, [])
        if not states:
            return None
        if up_to_order_index is None:
            return states[-1]
        valid_states = [s for s in states if s.order_index <= up_to_order_index]
        return valid_states[-1] if valid_states else None

    def get_character_states_for_scene(
        self, character_ids: list[str], chapter_id: str, order_index: int = 0
    ) -> list[CharacterState]:
        """Recupera o estado atual dos personagens presentes em uma cena específica."""
        active: list[CharacterState] = []
        for cid in character_ids:
            st = self.get_character_state(cid, chapter_id) or self.get_latest_character_state(
                cid, up_to_order_index=order_index
            )
            if st:
                active.append(st)
        return active

    # -------------------------------------------------------------------------
    # Relações Ativas
    # -------------------------------------------------------------------------

    def record_relationship(
        self,
        source_character_id: str = "",
        target_character_id: str = "",
        relation_type: str = "",
        description: str = "",
        chapter_id: str = "",
        evidence: str = "",
        confidence: float = 1.0,
        is_inferred: bool = False,
        source_type: str | None = None,
        relationship_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_char: str = "",
        target_char: str = "",
        rel_type: str = "",
    ) -> StoryRelationship:
        """Registra uma relação interpessoal ativa entre personagens com evidência e rastreabilidade."""
        actual_source = source_character_id or source_char
        actual_target = target_character_id or target_char
        actual_rel_type = relation_type or rel_type
        actual_source_type = source_type or ("inference" if is_inferred else "explicit")
        if actual_source_type in ("inferred", "inference"):
            actual_source_type = "inference"
            is_inferred = True

        rid = relationship_id or f"rel_{actual_source}_{actual_target}_{actual_rel_type}"
        rel = StoryRelationship(
            id=rid,
            source_character_id=actual_source,
            target_character_id=actual_target,
            relation_type=actual_rel_type,
            description=description,
            chapter_id=chapter_id,
            evidence=evidence,
            confidence=confidence,
            is_inferred=is_inferred,
            source_type=actual_source_type,
            metadata=dict(metadata or {}),
        )
        for i, existing in enumerate(self._relationships):
            if (
                existing.source_character_id == actual_source
                and existing.target_character_id == actual_target
                and existing.relation_type == actual_rel_type
                and existing.chapter_id == chapter_id
            ):
                self._relationships[i] = rel
                return rel

        self._relationships.append(rel)
        return rel

    def get_relationships(
        self,
        character_id: str | None = None,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[StoryRelationship]:
        """Retorna todas as relações registradas com suporte a filtros."""
        rels = list(self._relationships)
        if character_id:
            rels = [
                r
                for r in rels
                if r.source_character_id == character_id or r.target_character_id == character_id
            ]
        if explicit_only:
            rels = [r for r in rels if not r.is_inferred]
        elif inferred_only:
            rels = [r for r in rels if r.is_inferred]
        return rels

    def get_character_relationships(
        self,
        character_id: str,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[StoryRelationship]:
        """Alias para recuperar relações de um personagem."""
        return self.get_relationships(
            character_id=character_id,
            explicit_only=explicit_only,
            inferred_only=inferred_only,
        )

    def get_active_relationships_between(self, character_ids: list[str]) -> list[StoryRelationship]:
        """Recupera as relações ativas restritas aos personagens presentes na cena."""
        if not character_ids or len(character_ids) < 2:
            return []
        cset = set(character_ids)
        return [
            r
            for r in self._relationships
            if r.source_character_id in cset and r.target_character_id in cset
        ]

    # -------------------------------------------------------------------------
    # Eventos Relevantes e Cronologia
    # -------------------------------------------------------------------------

    def record_event(
        self,
        description: str = "",
        chapter_id: str = "",
        characters_involved: list[str] | None = None,
        unit_id: str = "",
        significance: str = "major",
        narrative_order: int = 0,
        chronological_order: int = 0,
        evidence: str = "",
        confidence: float = 1.0,
        is_inferred: bool = False,
        source_type: str | None = None,
        event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        order_index: int = 0,
        title: str = "",
        impact: str = "",
        characters: list[str] | None = None,
    ) -> StoryEvent:
        """Registra um evento relevante na trama com distinção narrativa vs cronológica."""
        eid = event_id or f"evt_{uuid.uuid4().hex[:8]}"
        actual_source_type = source_type or ("inference" if is_inferred else "explicit")
        if actual_source_type in ("inferred", "inference"):
            actual_source_type = "inference"
            is_inferred = True

        n_order = narrative_order or order_index
        c_order = chronological_order or n_order
        chars = list(characters_involved or characters or [])
        meta = dict(metadata or {})
        if title:
            meta["title"] = title
        if impact:
            meta["impact"] = impact
            significance = impact

        evt = StoryEvent(
            id=eid,
            chapter_id=chapter_id,
            description=description,
            unit_id=unit_id,
            characters_involved=chars,
            significance=significance,
            narrative_order=n_order,
            chronological_order=c_order,
            evidence=evidence,
            confidence=confidence,
            is_inferred=is_inferred,
            source_type=actual_source_type,
            metadata=meta,
        )
        self._events[eid] = evt
        return evt

    def get_events(
        self,
        chapter_id: str | None = None,
        chronological: bool = False,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[StoryEvent]:
        """Retorna eventos filtrados e ordenados por ordem narrativa ou cronológica."""
        evts = list(self._events.values())
        if chapter_id:
            evts = [e for e in evts if e.chapter_id == chapter_id]
        if explicit_only:
            evts = [e for e in evts if not e.is_inferred]
        elif inferred_only:
            evts = [e for e in evts if e.is_inferred]

        if chronological:
            return sorted(evts, key=lambda e: (e.chronological_order, e.narrative_order))
        return sorted(evts, key=lambda e: (e.narrative_order, e.chronological_order))

    def get_chronology(self, chapter_id: str | None = None) -> list[StoryEvent]:
        """Retorna cronologia de eventos ordenados no tempo in-universe."""
        return self.get_events(chapter_id=chapter_id, chronological=True)

    # -------------------------------------------------------------------------
    # Fatos Persistentes (Lore, Regras e Verdades Fixas)
    # -------------------------------------------------------------------------

    def record_fact(
        self,
        statement: str = "",
        category: str = "world_rule",
        subject_entity_ids: list[str] | None = None,
        evidence: str = "",
        confidence: float = 1.0,
        locked: bool = False,
        is_inferred: bool = False,
        source_type: str | None = None,
        fact_id: str | None = None,
        occurrences: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
        entity_id: str = "",
        fact: str = "",
        chapter_id: str = "",
        scope: str = "",
    ) -> PersistentFact:
        """Registra um fato persistente da obra com suporte a travamento (locked) e inferência."""
        stmt = statement or fact
        fid = fact_id or f"fact_{uuid.uuid4().hex[:8]}"
        existing = self._facts.get(fid)
        if existing and existing.locked and not force:
            raise LockedTermError(
                f"Fato persistente '{fid}' está travado (locked=True). "
                f"Declaração: '{existing.statement}'. Use force=True para alterar."
            )

        actual_source_type = source_type or ("inference" if is_inferred else "explicit")
        if actual_source_type in ("inferred", "inference"):
            actual_source_type = "inference"
            is_inferred = True

        entities = list(subject_entity_ids or [])
        if entity_id and entity_id not in entities:
            entities.append(entity_id)

        occs = list(occurrences or [])
        if chapter_id and chapter_id not in occs:
            occs.append(chapter_id)

        meta = dict(metadata or {})
        if scope:
            meta["scope"] = scope

        fact_obj = PersistentFact(
            id=fid,
            statement=stmt,
            category=scope or category,
            subject_entity_ids=entities,
            evidence=evidence,
            confidence=confidence,
            locked=locked or (existing.locked if existing else False),
            is_inferred=is_inferred
            or (existing.is_inferred if existing and not is_inferred else is_inferred),
            source_type=actual_source_type,
            occurrences=occs,
            metadata=meta,
        )
        self._facts[fid] = fact_obj
        return fact_obj

    def get_facts(
        self,
        category: str | None = None,
        entity_id: str | None = None,
        locked_only: bool = False,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[PersistentFact]:
        """Retorna fatos persistentes filtrados."""
        facts = list(self._facts.values())
        if category:
            facts = [f for f in facts if f.category == category]
        if entity_id:
            facts = [f for f in facts if entity_id in f.subject_entity_ids]
        if locked_only:
            facts = [f for f in facts if f.locked]
        if explicit_only:
            facts = [f for f in facts if not f.is_inferred]
        elif inferred_only:
            facts = [f for f in facts if f.is_inferred]
        return facts

    def get_persistent_facts(
        self,
        entity_id: str | None = None,
        category: str | None = None,
        locked_only: bool = False,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[PersistentFact]:
        """Alias para recuperação de fatos persistentes."""
        return self.get_facts(
            category=category,
            entity_id=entity_id,
            locked_only=locked_only,
            explicit_only=explicit_only,
            inferred_only=inferred_only,
        )

    def lock_fact(self, fact_id: str, locked: bool = True) -> None:
        """Trava ou destrava um fato persistente."""
        if fact_id in self._facts:
            self._facts[fact_id].locked = locked

    # -------------------------------------------------------------------------
    # Referências Cruzadas
    # -------------------------------------------------------------------------

    def record_cross_reference(
        self,
        source_unit_id: str = "",
        target_unit_id: str = "",
        description: str = "",
        ref_type: str = "callback",
        evidence: str = "",
        confidence: float = 1.0,
        is_inferred: bool = False,
        source_type: str | None = None,
        ref_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_chapter: str = "",
        target_chapter: str = "",
    ) -> StoryCrossReference:
        """Registra uma referência cruzada entre duas unidades da obra."""
        s_unit = source_unit_id or source_chapter
        t_unit = target_unit_id or target_chapter
        rid = ref_id or f"ref_{s_unit}_{t_unit}"
        actual_source_type = source_type or ("inference" if is_inferred else "explicit")
        if actual_source_type in ("inferred", "inference"):
            actual_source_type = "inference"
            is_inferred = True

        cross_ref = StoryCrossReference(
            id=rid,
            source_unit_id=s_unit,
            target_unit_id=t_unit,
            description=description,
            ref_type=ref_type,
            evidence=evidence,
            confidence=confidence,
            is_inferred=is_inferred,
            source_type=actual_source_type,
            metadata=dict(metadata or {}),
        )
        self._cross_references[rid] = cross_ref
        return cross_ref

    def get_cross_references(
        self,
        unit_id: str | None = None,
        chapter_id: str | None = None,
        explicit_only: bool = False,
        inferred_only: bool = False,
    ) -> list[StoryCrossReference]:
        """Recupera referências cruzadas vinculadas a uma unidade ou capítulo."""
        check_id = unit_id or chapter_id
        refs = list(self._cross_references.values())
        if check_id:
            refs = [r for r in refs if r.source_unit_id == check_id or r.target_unit_id == check_id]
        if explicit_only:
            refs = [r for r in refs if not r.is_inferred]
        elif inferred_only:
            refs = [r for r in refs if r.is_inferred]
        return refs

    # -------------------------------------------------------------------------
    # Recuperação Seletiva de Contexto (Scene Context Snapshot)
    # -------------------------------------------------------------------------

    def get_scene_context_snapshot(
        self,
        chapter_id: str,
        unit_id: str,
        character_ids: list[str] | None = None,
        max_facts: int = 5,
        max_events: int = 3,
    ) -> StoryContextSnapshot:
        """Produz um recorte cirúrgico e compacto de contexto para um segmento específico.

        MADLAD não é um LLM conversacional: não enviamos capítulos inteiros nem dumps
        massivos de lore. Entregamos estritamente:
        1. Resumo do capítulo atual (se houver);
        2. Estado atual dos personagens presentes na cena;
        3. Relações interpessoais ativas exclusivamente entre os presentes;
        4. Últimos eventos relevantes antecedentes mais imediatos;
        5. Fatos persistentes associados aos personagens ou ao mundo (priorizando fatos explícitos);
        6. Referências cruzadas vinculadas à unidade atual.
        """
        active_cids = list(character_ids or [])

        # 1. Resumo do capítulo
        ch_sum = self.get_summary(chapter_id)
        summary_text = ch_sum.summary_text if ch_sum else ""

        # 2. Estados dos personagens presentes
        char_states: list[CharacterState] = []
        for cid in active_cids:
            st = self.get_character_state(cid, chapter_id) or self.get_latest_character_state(cid)
            if st:
                char_states.append(st)

        # 3. Relações ativas entre os presentes
        rels = self.get_active_relationships_between(active_cids)

        # 4. Eventos recentes antecedentes
        all_evts = self.get_events(chronological=False)
        recent = [e for e in all_evts if e.chapter_id == chapter_id or e.unit_id == unit_id]
        if not recent:
            recent = all_evts[-max_events:] if all_evts else []
        else:
            recent = recent[-max_events:]

        # 5. Fatos persistentes relevantes (prioriza explícitos e travados)
        facts: list[PersistentFact] = []
        # Primeiro, fatos explícitos das entidades presentes
        for cid in active_cids:
            char_facts = self.get_facts(entity_id=cid, explicit_only=True)
            for f in char_facts:
                if f not in facts:
                    facts.append(f)
                if len(facts) >= max_facts:
                    break
            if len(facts) >= max_facts:
                break

        # Se houver espaço, fatos de regra geral explícitos
        if len(facts) < max_facts:
            general_facts = self.get_facts(category="world_rule", explicit_only=True)
            for gf in general_facts:
                if gf not in facts:
                    facts.append(gf)
                if len(facts) >= max_facts:
                    break

        # Se ainda houver espaço, aceita inferências relevantes
        if len(facts) < max_facts:
            for cid in active_cids:
                inferred_facts = self.get_facts(entity_id=cid, inferred_only=True)
                for f in inferred_facts:
                    if f not in facts:
                        facts.append(f)
                    if len(facts) >= max_facts:
                        break
                if len(facts) >= max_facts:
                    break

        # 6. Referências cruzadas da unidade
        cross_refs = self.get_cross_references(unit_id)

        # Contagem de explícitos vs inferências no snapshot
        all_items: list[Any] = char_states + rels + recent + facts + cross_refs
        inferred_count = sum(1 for item in all_items if getattr(item, "is_inferred", False))
        explicit_count = len(all_items) - inferred_count

        return StoryContextSnapshot(
            chapter_id=chapter_id,
            unit_id=unit_id,
            chapter_summary=summary_text,
            active_character_states=char_states,
            active_relationships=rels,
            recent_events=recent,
            relevant_facts=facts,
            cross_references=cross_refs,
            inferred_items_count=inferred_count,
            explicit_items_count=explicit_count,
        )

    # -------------------------------------------------------------------------
    # Validações de Consistência e QA de Continuidade Narrativa
    # -------------------------------------------------------------------------

    def validate_character_continuity(
        self,
        character_id: str,
        chapter_id: str,
        text: str,
        order_index: int = 0,
    ) -> list[QAStoryAnomaly]:
        """Valida se as ações de um personagem são compatíveis com seu estado prévio.

        Exemplo: se o personagem foi registrado como 'deceased' ou 'missing' em capítulos
        anteriores e agora é retratado falando ativamente sem contexto de flashback.
        """
        anomalies: list[QAStoryAnomaly] = []
        prior_state = self.get_latest_character_state(character_id, up_to_order_index=order_index)

        if prior_state and prior_state.alive_status == "deceased":
            action_indicators = ["disse", "falou", "respondeu", "caminhou", "olhou", "pensou"]
            has_action = any(re.search(rf"\b{w}\b", text, re.IGNORECASE) for w in action_indicators)
            if has_action:
                anomalies.append(
                    QAStoryAnomaly(
                        anomaly_type="character_continuity",
                        severity="warning",
                        message=(
                            f"Personagem '{character_id}' está registrado como 'deceased' "
                            f"(falecido) no capítulo {prior_state.chapter_id}, mas realiza ações "
                            f"ativas no capítulo {chapter_id}. Verificar se é um flashback."
                        ),
                        chapter_id=chapter_id,
                        character_id=character_id,
                        snippet=text[:100],
                    )
                )

        return anomalies

    def validate_facts_compliance(self, text: str) -> list[QAStoryAnomaly]:
        """Verifica se o texto não entra em contradição evidente com fatos persistentes."""
        anomalies: list[QAStoryAnomaly] = []
        target_facts = self.get_facts(locked_only=True) or self.get_facts()
        text_lower = text.lower()

        for fact in target_facts:
            statement_lower = fact.statement.lower()
            # 1. Detecta restrições e proibições
            is_negative_constraint = any(
                w in statement_lower
                for w in [
                    "não pode",
                    "não deve",
                    "proibido",
                    "nunca",
                    "cannot",
                    "never",
                    "impossível",
                    "não",
                ]
            )
            if is_negative_constraint:
                words = [
                    w
                    for w in re.findall(r"\b\w{4,}\b", statement_lower)
                    if w
                    not in [
                        "não",
                        "pode",
                        "deve",
                        "proibido",
                        "nunca",
                        "cannot",
                        "never",
                        "impossível",
                        "regra",
                        "universo",
                        "fora",
                        "para",
                        "sobre",
                    ]
                ]
                for kw in words:
                    if kw in text_lower:
                        # Se o termo ocorre sem negação por perto
                        pattern = rf"\b(não|nunca|jamais|proibido|impossível de)\s+(\w+\s+)?{kw}\b"
                        if not re.search(pattern, text_lower):
                            anomalies.append(
                                QAStoryAnomaly(
                                    anomaly_type="fact_contradiction",
                                    severity="error",
                                    message=(
                                        f"Possível violação de fato persistente: '{fact.statement}'. "
                                        f"Termo restrito '{kw}' detectado de forma afirmativa no texto."
                                    ),
                                    snippet=text[:120],
                                    evidence=fact.evidence,
                                    conflicting_with=fact.statement,
                                    entity_id=fact.subject_entity_ids[0]
                                    if fact.subject_entity_ids
                                    else "",
                                )
                            )
                            break

        return anomalies

    def detect_timeline_inconsistencies(self) -> list[QAStoryAnomaly]:
        """Detecta reversões abruptas na cronologia dos eventos registrados."""
        anomalies: list[QAStoryAnomaly] = []
        events_list = self.get_events(chronological=False)
        if len(events_list) < 2:
            return anomalies

        for i in range(1, len(events_list)):
            prev_evt = events_list[i - 1]
            curr_evt = events_list[i]
            if (
                curr_evt.narrative_order > prev_evt.narrative_order
                and curr_evt.chronological_order < prev_evt.chronological_order
                and curr_evt.significance == "major"
            ):
                anomalies.append(
                    QAStoryAnomaly(
                        anomaly_type="timeline_jump",
                        severity="info",
                        message=(
                            f"Salto cronológico detectado: evento '{curr_evt.id}' (ordem {curr_evt.chronological_order}) "
                            f"ocorre após '{prev_evt.id}' (ordem {prev_evt.chronological_order}) na narrativa. "
                            f"Possível analepse/flashback."
                        ),
                        chapter_id=curr_evt.chapter_id,
                    )
                )

        return anomalies

    def detect_contradictions(self) -> list[QAStoryAnomaly]:
        """Varredura abrangente para detectar contradições narrativas e contextuais.

        Verifica:
        1. Estados de personagens conflitantes (falecido vs ativo, múltiplos locais simultâneos);
        2. Fatos persistentes opostos ou inconciliáveis;
        3. Relações interpessoais mutuamente exclusivas ativas no mesmo capítulo;
        4. Inversões e anomalias na cronologia de eventos.
        """
        anomalies: list[QAStoryAnomaly] = []

        # 1. Estados de personagens
        for char_id, states in self._character_states.items():
            if len(states) < 2:
                continue
            for i in range(len(states) - 1):
                s1 = states[i]
                s2 = states[i + 1]
                if s1.alive_status == "deceased" and s2.alive_status == "alive":
                    if not s2.metadata.get("flashback", False) and not s2.metadata.get(
                        "resurrected", False
                    ):
                        anomalies.append(
                            QAStoryAnomaly(
                                anomaly_type="character_state_contradiction",
                                severity="error",
                                message=(
                                    f"Contradição de estado do personagem '{char_id}': marcado como "
                                    f"'deceased' no capítulo {s1.chapter_id} e posteriormente como "
                                    f"'alive' no capítulo {s2.chapter_id} sem flag de flashback ou ressurreição."
                                ),
                                chapter_id=s2.chapter_id,
                                character_id=char_id,
                            )
                        )
                # Locais simultâneos em mesmo capítulo/ordem
                if s1.chapter_id == s2.chapter_id and s1.order_index == s2.order_index:
                    if s1.location and s2.location and s1.location.lower() != s2.location.lower():
                        anomalies.append(
                            QAStoryAnomaly(
                                anomaly_type="character_location_contradiction",
                                severity="warning",
                                message=(
                                    f"Personagem '{char_id}' registrado em locais diferentes no capítulo "
                                    f"{s1.chapter_id}: '{s1.location}' vs '{s2.location}'."
                                ),
                                chapter_id=s1.chapter_id,
                                character_id=char_id,
                            )
                        )

        # 2. Fatos persistentes contraditórios
        facts_list = list(self._facts.values())
        neg_words = ["não", "nunca", "cannot", "never", "impossível", "proibido"]
        for i in range(len(facts_list)):
            for j in range(i + 1, len(facts_list)):
                f1 = facts_list[i]
                f2 = facts_list[j]
                common_entities = set(f1.subject_entity_ids).intersection(
                    set(f2.subject_entity_ids)
                )
                if common_entities or (f1.category == f2.category and f1.category != "plot_fact"):
                    s1 = f1.statement.lower()
                    s2 = f2.statement.lower()
                    f1_neg = any(w in s1 for w in neg_words)
                    f2_neg = any(w in s2 for w in neg_words)
                    if f1_neg != f2_neg:
                        tokens1 = set(re.findall(r"\b\w{4,}\b", s1)) - set(neg_words)
                        tokens2 = set(re.findall(r"\b\w{4,}\b", s2)) - set(neg_words)
                        overlap = tokens1.intersection(tokens2)
                        if len(overlap) >= 1:
                            anomalies.append(
                                QAStoryAnomaly(
                                    anomaly_type="fact_contradiction",
                                    severity="error" if (f1.locked or f2.locked) else "warning",
                                    message=(
                                        f"Contradição entre fatos persistentes: "
                                        f"Fato 1 ('{f1.statement}') vs Fato 2 ('{f2.statement}'). "
                                        f"Termos em conflito de polaridade: {', '.join(sorted(overlap))}."
                                    ),
                                )
                            )

        # 3. Relações interpessoais mutuamente exclusivas
        exclusive_pairs = [
            (
                {"ally", "amigo", "aliado", "aliados"},
                {"enemy", "inimigo", "inimigos", "inimigos mortais", "arqui-inimigo", "rival"},
            ),
            (
                {"married", "casado", "casados", "cônjuge", "esposo", "esposa"},
                {"stranger", "estranho", "desconhecido"},
            ),
            (
                {"married", "casado", "casados", "cônjuge", "esposo", "esposa"},
                {
                    "enemy",
                    "inimigo",
                    "inimigos",
                    "inimigos mortais",
                    "arqui-inimigo",
                    "rival",
                    "ódio",
                },
            ),
        ]
        rels = self.get_relationships()
        for i in range(len(rels)):
            for j in range(i + 1, len(rels)):
                r1 = rels[i]
                r2 = rels[j]
                same_pair = (
                    r1.source_character_id == r2.source_character_id
                    and r1.target_character_id == r2.target_character_id
                ) or (
                    r1.source_character_id == r2.target_character_id
                    and r1.target_character_id == r2.source_character_id
                )
                if same_pair and r1.chapter_id == r2.chapter_id:
                    t1 = r1.relation_type.lower()
                    t2 = r2.relation_type.lower()
                    for group_a, group_b in exclusive_pairs:
                        if (any(a in t1 for a in group_a) and any(b in t2 for b in group_b)) or (
                            any(b in t1 for b in group_b) and any(a in t2 for a in group_a)
                        ):
                            anomalies.append(
                                QAStoryAnomaly(
                                    anomaly_type="relationship_contradiction",
                                    severity="warning",
                                    message=(
                                        f"Relação contraditória simultânea entre '{r1.source_character_id}' "
                                        f"e '{r1.target_character_id}' no capítulo {r1.chapter_id}: "
                                        f"'{r1.relation_type}' vs '{r2.relation_type}'."
                                    ),
                                    chapter_id=r1.chapter_id,
                                    character_id=r1.source_character_id,
                                )
                            )

        # 4. Inconsistências na linha do tempo
        anomalies.extend(self.detect_timeline_inconsistencies())

        return anomalies
