"""Contratos e modelos para auditoria global de consistência da obra (Consistency Pass)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from book_translator.core.models import Document
from book_translator.memory.base import MemoryManagerInterface
from book_translator.qa.base import IssueSeverity


@dataclass
class OccurrenceLocation:
    """Ocorrência específica de uma variante ou termo em um segmento da obra."""

    chapter_id: str
    segment_id: str
    source_snippet: str = ""
    translated_snippet: str = ""
    order_index: int = 0
    character_id: str | None = None
    speaker: str | None = None
    listener: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OccurrenceLocation:
        return cls(
            chapter_id=data.get("chapter_id", ""),
            segment_id=data.get("segment_id", ""),
            source_snippet=data.get("source_snippet", ""),
            translated_snippet=data.get("translated_snippet", ""),
            order_index=int(data.get("order_index", 0)),
            character_id=data.get("character_id"),
            speaker=data.get("speaker"),
            listener=data.get("listener"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ConsistencyConflict:
    """Conflito de consistência global detectado entre capítulos da obra."""

    term_or_entity: str
    category: str = "terminology"  # 'character', 'alias', 'name', 'pronoun', 'treatment',
    # 'location', 'organization', 'terminology', 'title',
    # 'chronology', 'style', 'dialogue', 'glossary',
    # 'translation_memory', 'style_bible'
    variants: dict[str, list[OccurrenceLocation]] = field(default_factory=dict)
    severity: IssueSeverity = IssueSeverity.SUGGESTED_FIX
    message: str = ""
    suggested_standardization: str = ""
    id: str = field(default_factory=lambda: f"conflict_{uuid.uuid4().hex[:8]}")
    is_potential_intentional_variation: bool = False
    evidence: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_safe_fix(self) -> bool:
        return self.severity == IssueSeverity.SAFE_FIX

    @property
    def requires_review(self) -> bool:
        return self.severity == IssueSeverity.REVIEW_REQUIRED

    @property
    def total_occurrences(self) -> int:
        return sum(len(locs) for locs in self.variants.values())

    @property
    def variant_counts(self) -> dict[str, int]:
        return {v: len(locs) for v, locs in self.variants.items()}

    def get_chapters_involved(self) -> list[str]:
        chapters: set[str] = set()
        for locs in self.variants.values():
            for loc in locs:
                if isinstance(loc, OccurrenceLocation):
                    chapters.add(loc.chapter_id)
                elif isinstance(loc, dict) and "chapter_id" in loc:
                    chapters.add(loc["chapter_id"])
        return sorted(chapters)

    def to_dict(self) -> dict[str, Any]:
        serialized_variants: dict[str, Any] = {}
        for var, locs in self.variants.items():
            serialized_variants[var] = [
                loc.to_dict() if isinstance(loc, OccurrenceLocation) else loc for loc in locs
            ]
        return {
            "id": self.id,
            "term_or_entity": self.term_or_entity,
            "category": self.category,
            "severity": self.severity.value
            if isinstance(self.severity, IssueSeverity)
            else str(self.severity),
            "message": self.message,
            "suggested_standardization": self.suggested_standardization,
            "is_potential_intentional_variation": self.is_potential_intentional_variation,
            "evidence": self.evidence,
            "variants": serialized_variants,
            "details": self.details,
            "chapters_involved": self.get_chapters_involved(),
        }


@dataclass
class ConsistencyFixAuditRecord:
    """Registro de auditoria para correções de consistência aplicadas, permitindo reversão exata."""

    fix_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    conflict_id: str = ""
    category: str = ""
    chapter_id: str = ""
    segment_id: str = ""
    original_target_text: str = ""
    modified_target_text: str = ""
    applied_rule: str = ""
    reversible: bool = True
    undone: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GlobalConsistencyReport:
    """Relatório resultante da auditoria de consistência global da obra."""

    total_segments_audited: int = 0
    total_chapters_audited: int = 0
    conflicts: list[ConsistencyConflict] = field(default_factory=list)
    audit_trail: list[ConsistencyFixAuditRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    @property
    def safe_fixes(self) -> list[ConsistencyConflict]:
        return [c for c in self.conflicts if c.severity == IssueSeverity.SAFE_FIX]

    @property
    def suggested_fixes(self) -> list[ConsistencyConflict]:
        return [c for c in self.conflicts if c.severity == IssueSeverity.SUGGESTED_FIX]

    @property
    def review_required(self) -> list[ConsistencyConflict]:
        return [c for c in self.conflicts if c.severity == IssueSeverity.REVIEW_REQUIRED]

    def get_conflicts_by_chapter(self, chapter_id: str) -> list[ConsistencyConflict]:
        """Retorna conflitos que afetam determinado capítulo."""
        res: list[ConsistencyConflict] = []
        for c in self.conflicts:
            if chapter_id in c.get_chapters_involved():
                res.append(c)
        return res

    def get_conflicts_by_segment(self, segment_id: str) -> list[ConsistencyConflict]:
        """Retorna conflitos que têm ocorrência em determinado segmento."""
        res: list[ConsistencyConflict] = []
        for c in self.conflicts:
            for locs in c.variants.values():
                for loc in locs:
                    seg = loc.segment_id if isinstance(loc, OccurrenceLocation) else loc.get("segment_id")
                    if seg == segment_id:
                        res.append(c)
                        break
        return res

    def get_conflicts_by_category(self, category: str) -> list[ConsistencyConflict]:
        """Retorna conflitos filtrados pela categoria especificada."""
        return [c for c in self.conflicts if c.category.lower() == category.lower()]

    def get_conflicts_by_severity(
        self, severity: IssueSeverity | str
    ) -> list[ConsistencyConflict]:
        """Retorna conflitos filtrados pela severidade de ação."""
        sev_val = severity.value if isinstance(severity, IssueSeverity) else str(severity)
        return [
            c
            for c in self.conflicts
            if (c.severity.value if isinstance(c.severity, IssueSeverity) else str(c.severity))
            == sev_val
        ]

    def get_navigation_tree(self) -> dict[str, Any]:
        """Gera uma árvore navegável da auditoria: Capítulo -> Segmento -> Conflitos."""
        tree: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for conflict in self.conflicts:
            for variant_text, locs in conflict.variants.items():
                for loc in locs:
                    ch_id = (
                        loc.chapter_id
                        if isinstance(loc, OccurrenceLocation)
                        else loc.get("chapter_id", "unknown")
                    )
                    seg_id = (
                        loc.segment_id
                        if isinstance(loc, OccurrenceLocation)
                        else loc.get("segment_id", "unknown")
                    )
                    if ch_id not in tree:
                        tree[ch_id] = {}
                    if seg_id not in tree[ch_id]:
                        tree[ch_id][seg_id] = []

                    tree[ch_id][seg_id].append(
                        {
                            "conflict_id": conflict.id,
                            "category": conflict.category,
                            "severity": conflict.severity.value
                            if isinstance(conflict.severity, IssueSeverity)
                            else str(conflict.severity),
                            "term_or_entity": conflict.term_or_entity,
                            "variant_in_segment": variant_text,
                            "suggested_standardization": conflict.suggested_standardization,
                            "message": conflict.message,
                            "is_potential_intentional_variation": conflict.is_potential_intentional_variation,
                        }
                    )
        return tree

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_segments_audited": self.total_segments_audited,
            "total_chapters_audited": self.total_chapters_audited,
            "total_conflicts": len(self.conflicts),
            "safe_fixes_count": len(self.safe_fixes),
            "suggested_fixes_count": len(self.suggested_fixes),
            "review_required_count": len(self.review_required),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "audit_trail": [a.to_dict() for a in self.audit_trail],
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Gera um relatório legível e navegável em formato Markdown."""
        lines: list[str] = []
        lines.append("# Relatório Global de Consistência da Obra (Consistency Pass)")
        lines.append("")
        lines.append(f"- **Segmentos auditados:** {self.total_segments_audited}")
        lines.append(f"- **Capítulos auditados:** {self.total_chapters_audited}")
        lines.append(f"- **Total de conflitos detectados:** {len(self.conflicts)}")
        lines.append(
            f"- **Classificação:** {len(self.safe_fixes)} SAFE FIX | "
            f"{len(self.suggested_fixes)} SUGGESTED FIX | "
            f"{len(self.review_required)} REVIEW REQUIRED"
        )
        lines.append("")

        if not self.conflicts:
            lines.append("Nenhum conflito de consistência detectado. A obra está perfeitamente alinhada!")
            return "\n".join(lines)

        lines.append("## Conflitos por Categoria")
        categories = sorted(set(c.category for c in self.conflicts))
        for cat in categories:
            cat_conflicts = self.get_conflicts_by_category(cat)
            lines.append(f"### {cat.upper()} ({len(cat_conflicts)})")
            for c in cat_conflicts:
                sev_icon = (
                    "🟢 SAFE FIX"
                    if c.is_safe_fix
                    else ("🟡 SUGGESTED FIX" if c.severity == IssueSeverity.SUGGESTED_FIX else "🔴 REVIEW REQUIRED")
                )
                intentional_flag = (
                    " *(Variação potencialmente intencional)*"
                    if c.is_potential_intentional_variation
                    else ""
                )
                lines.append(f"- **{c.term_or_entity}** [{sev_icon}]{intentional_flag}")
                lines.append(f"  - *Mensagem:* {c.message}")
                if c.suggested_standardization:
                    lines.append(f"  - *Padronização sugerida:* `{c.suggested_standardization}`")
                lines.append(f"  - *Capítulos:* {', '.join(c.get_chapters_involved())}")
                lines.append("  - *Variantes encontradas:*")
                for var, locs in c.variants.items():
                    sample_seg = locs[0].segment_id if locs and isinstance(locs[0], OccurrenceLocation) else "N/A"
                    lines.append(f"    - `{var}`: {len(locs)} ocorrência(s) (ex: seg `{sample_seg}`)")
            lines.append("")

        lines.append("## Navegação por Capítulo")
        tree = self.get_navigation_tree()
        for ch_id in sorted(tree.keys()):
            segs = tree[ch_id]
            lines.append(f"### Capítulo: `{ch_id}` ({sum(len(v) for v in segs.values())} anomalias)")
            for seg_id, issues in segs.items():
                lines.append(f"- **Segmento `{seg_id}`** ({len(issues)} conflitos):")
                for iss in issues:
                    lines.append(
                        f"  - [{iss['severity'].upper()}] **{iss['term_or_entity']}** "
                        f"(variante: *\"{iss['variant_in_segment']}\"*) -> {iss['message']}"
                    )
            lines.append("")

        if self.audit_trail:
            lines.append("## Trilha de Correções Automáticas Realizadas")
            for a in self.audit_trail:
                status = "REVERTIDO" if a.undone else "ATIVO"
                lines.append(
                    f"- [`{a.fix_id}`] [{status}] Seg `{a.segment_id}`: "
                    f"\"{a.original_target_text}\" -> \"{a.modified_target_text}\" ({a.applied_rule})"
                )

        return "\n".join(lines)


# Alias para retrocompatibilidade
ConsistencyReport = GlobalConsistencyReport


@runtime_checkable
class ConsistencyCheckerInterface(Protocol):
    """Protocolo formal para o auditor global de consistência."""

    def audit(
        self,
        document: Document,
        memory_manager: MemoryManagerInterface,
    ) -> GlobalConsistencyReport:
        """Examina toda a obra traduzida buscando divergências nas 15 dimensões."""
        ...

    def apply_safe_fixes(
        self,
        document: Document,
        report: GlobalConsistencyReport,
    ) -> list[ConsistencyFixAuditRecord]:
        """Aplica apenas correções categorizadas como SAFE FIX de forma auditável e reversível."""
        ...

    def rollback_fix(
        self,
        document: Document,
        audit_record_or_fix_id: ConsistencyFixAuditRecord | str,
    ) -> bool:
        """Reverte cirurgicamente uma correção automática aplicada anteriormente."""
        ...

    def rollback_all_fixes(
        self,
        document: Document,
        report: GlobalConsistencyReport,
    ) -> int:
        """Reverte todas as correções automáticas aplicadas em um relatório."""
        ...


__all__ = [
    "OccurrenceLocation",
    "ConsistencyConflict",
    "ConsistencyFixAuditRecord",
    "GlobalConsistencyReport",
    "ConsistencyReport",
    "ConsistencyCheckerInterface",
]
