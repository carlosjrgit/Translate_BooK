"""Módulo de validação e garantia de qualidade (QA determinístico e semântico)."""

from __future__ import annotations

from book_translator.qa.base import (
    IssueSeverity,
    QAInterface,
    QAIssue,
    QAReport,
)

__all__ = ["IssueSeverity", "QAIssue", "QAReport", "QAInterface"]
