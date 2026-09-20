"""Módulo de validação e garantia de qualidade (QA determinístico, semântico e retrotradução)."""

from __future__ import annotations

from book_translator.qa.backtranslation import BacktranslationVerifier
from book_translator.qa.base import (
    BacktranslationEvidence,
    IssueSeverity,
    QAFixAuditRecord,
    QAInterface,
    QAIssue,
    QAReport,
    SemanticEncoderProtocol,
    SemanticEvaluationResult,
    SemanticQAInterface,
    SemanticSignalScores,
    UnifiedQAReport,
)
from book_translator.qa.deterministic import DeterministicQAEngine
from book_translator.qa.orchestrator import UnifiedQAOrchestrator
from book_translator.qa.semantic import (
    MockSemanticEncoder,
    SemanticQAEngine,
    SentenceTransformerSemanticEncoder,
)

__all__ = [
    "IssueSeverity",
    "QAIssue",
    "QAReport",
    "QAInterface",
    "QAFixAuditRecord",
    "DeterministicQAEngine",
    "SemanticSignalScores",
    "SemanticEvaluationResult",
    "BacktranslationEvidence",
    "SemanticEncoderProtocol",
    "SemanticQAInterface",
    "UnifiedQAReport",
    "MockSemanticEncoder",
    "SentenceTransformerSemanticEncoder",
    "SemanticQAEngine",
    "BacktranslationVerifier",
    "UnifiedQAOrchestrator",
]
