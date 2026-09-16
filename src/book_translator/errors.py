"""Hierarquia de exceções canônicas do BookTranslator."""

from __future__ import annotations


class BookTranslatorError(Exception):
    """Exceção base para todos os erros do sistema BookTranslator."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (detalhes: {self.details})"
        return self.message


class ConfigurationError(BookTranslatorError):
    """Lançado quando há problema nas configurações do sistema ou do projeto."""


class IngestionError(BookTranslatorError):
    """Lançado durante inspeção ou ingestão de arquivos fonte."""


class ParsingError(BookTranslatorError):
    """Lançado quando um parser falha ao processar o formato do documento."""


class NeedsOcrError(ParsingError):
    """Lançado quando o documento (ex: PDF escaneado) não possui texto
    utilizável e necessita de OCR.
    """


class AnalysisError(BookTranslatorError):
    """Lançado durante a fase de análise global da obra."""


class MemoryError(BookTranslatorError):
    """Lançado em operações de memórias (Character, Translation Memory, Glossary)."""


class TranslationEngineError(BookTranslatorError):
    """Lançado quando o motor de tradução ou seu adaptador falha."""


class QAError(BookTranslatorError):
    """Lançado durante a validação de qualidade (QA determinístico ou semântico)."""


class ConsistencyError(BookTranslatorError):
    """Lançado durante auditoria de consistência global."""


class ExportError(BookTranslatorError):
    """Lançado durante a reconstrução ou exportação do arquivo final."""


class DatabaseError(BookTranslatorError):
    """Lançado em operações de persistência e banco de dados do projeto."""
