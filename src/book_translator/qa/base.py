"""Contratos e modelos do sistema de validação e controle de qualidade (QA)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from book_translator.core.models import Segment


class IssueSeverity(str, Enum):
    """Categorização do nível de ação exigido para anomalias detectadas."""

    SAFE_FIX = "safe_fix"  # Correção determinística e segura automática
    SUGGESTED_FIX = "suggested_fix"  # Correção provável com alta confiança
    REVIEW_REQUIRED = "review_required"  # Decisão editorial ambígua para revisão humana


@dataclass
class QAIssue:
    """Anomalia pontual identificada na tradução."""

    check_type: str  # ex: 'number_mismatch', 'date_mismatch', 'omission', 'polarity'
    severity: IssueSeverity
    description: str
    original_snippet: str = ""
    translated_snippet: str = ""
    suggested_fix: str | None = None


@dataclass
class QAReport:
    """Relatório consolidado de controle de qualidade para um segmento."""

    segment_id: str
    passed: bool
    issues: list[QAIssue] = field(default_factory=list)

    @property
    def requires_human_review(self) -> bool:
        return any(i.severity == IssueSeverity.REVIEW_REQUIRED for i in self.issues)

    @property
    def has_safe_fixes(self) -> bool:
        return any(i.severity == IssueSeverity.SAFE_FIX for i in self.issues)


@runtime_checkable
class QAInterface(Protocol):
    """Protocolo formal para validadores de qualidade de tradução."""

    def evaluate(
        self,
        segment: Segment,
        original_text: str,
        translated_text: str,
    ) -> QAReport:
        """Avalia a fidelidade, precisão e naturalidade da tradução gerada."""
        ...
