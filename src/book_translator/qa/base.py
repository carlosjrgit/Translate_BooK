"""Contratos e modelos do sistema de validação e controle de qualidade (QA)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

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


@dataclass
class QAFixAuditRecord:
    """Registro de auditoria de correção automática determinística (SAFE FIX) aplicada."""

    id: str
    segment_id: str
    check_type: str
    old_text: str
    new_text: str
    rule_applied: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class QAInterface(Protocol):
    """Protocolo formal para validadores de qualidade de tradução."""

    def evaluate(
        self,
        segment: Segment,
        original_text: str,
        translated_text: str,
        context: Any = None,
    ) -> QAReport:
        """Avalia a fidelidade, precisão e naturalidade da tradução gerada."""
        ...


@dataclass
class SemanticSignalScores:
    """Notas individuais (0.0 a 1.0) para cada sinal semântico avaliado."""

    embedding_similarity: float = 1.0
    subject_consistency: float = 1.0
    polarity_consistency: float = 1.0
    intensity_preservation: float = 1.0
    content_preservation: float = 1.0
    literal_correctness: float = 1.0


@dataclass
class SemanticEvaluationResult:
    """Resultado estruturado e inspecionável da análise semântica."""

    overall_score: float
    signal_scores: SemanticSignalScores
    issues: list[QAIssue] = field(default_factory=list)
    justifications: list[str] = field(default_factory=list)
    passed: bool = True


@dataclass
class BacktranslationEvidence:
    """Evidência auxiliar produzida pelo ciclo de retrotradução EN -> PT-BR -> EN."""

    reconstructed_en: str
    lexical_chrf: float = 1.0
    token_similarity: float = 1.0
    negation_preserved: bool = True
    subject_preserved: bool = True
    divergence_notes: list[str] = field(default_factory=list)
    has_potential_issue: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SemanticEncoderProtocol(Protocol):
    """Protocolo formal para geradores de embeddings multilíngues."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Gera representação vetorial densa para uma lista de textos."""
        ...

    def similarity(self, text_a: str, text_b: str) -> float:
        """Calcula a similaridade por cosseno entre dois textos."""
        ...


@runtime_checkable
class SemanticQAInterface(Protocol):
    """Protocolo formal para validadores semânticos de tradução."""

    def evaluate_semantic(
        self,
        segment: Segment,
        original_text: str,
        translated_text: str,
        context: Any = None,
    ) -> SemanticEvaluationResult:
        """Avalia divergências semânticas profundas combinando múltiplos sinais."""
        ...


@dataclass
class UnifiedQAReport:
    """Relatório consolidado unindo QA Determinístico, Semantic QA e Backtranslation."""

    segment_id: str
    passed: bool
    deterministic_issues: list[QAIssue] = field(default_factory=list)
    semantic_issues: list[QAIssue] = field(default_factory=list)
    backtranslation_evidence: BacktranslationEvidence | None = None
    semantic_result: SemanticEvaluationResult | None = None

    @property
    def issues(self) -> list[QAIssue]:
        return self.deterministic_issues + self.semantic_issues

    @property
    def requires_human_review(self) -> bool:
        return any(i.severity == IssueSeverity.REVIEW_REQUIRED for i in self.issues)

    @property
    def has_safe_fixes(self) -> bool:
        return any(i.severity == IssueSeverity.SAFE_FIX for i in self.issues)


__all__ = [
    "IssueSeverity",
    "QAIssue",
    "QAReport",
    "QAFixAuditRecord",
    "QAInterface",
    "SemanticSignalScores",
    "SemanticEvaluationResult",
    "BacktranslationEvidence",
    "SemanticEncoderProtocol",
    "SemanticQAInterface",
    "UnifiedQAReport",
]
