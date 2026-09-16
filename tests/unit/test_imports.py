"""Testes de integridade de importação dos módulos da arquitetura."""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "book_translator",
    "book_translator.cli",
    "book_translator.config",
    "book_translator.errors",
    "book_translator.logging",
    "book_translator.core",
    "book_translator.core.models",
    "book_translator.core.contracts",
    "book_translator.ingestion",
    "book_translator.ingestion.base",
    "book_translator.parsers",
    "book_translator.parsers.base",
    "book_translator.analysis",
    "book_translator.analysis.base",
    "book_translator.memory",
    "book_translator.memory.base",
    "book_translator.context",
    "book_translator.context.base",
    "book_translator.translation",
    "book_translator.translation.base",
    "book_translator.qa",
    "book_translator.qa.base",
    "book_translator.consistency",
    "book_translator.consistency.base",
    "book_translator.database",
    "book_translator.database.base",
    "book_translator.export",
    "book_translator.export.base",
    "book_translator.ui",
    "book_translator.ui.base",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_submodules_import_cleanly(module_name: str) -> None:
    """Garante que todos os submódulos da arquitetura importam sem exceções."""
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_package_version_defined() -> None:
    """Verifica se a versão do pacote está definida e segue SemVer."""
    import book_translator

    assert hasattr(book_translator, "__version__")
    assert isinstance(book_translator.__version__, str)
    parts = book_translator.__version__.split(".")
    assert len(parts) >= 3
