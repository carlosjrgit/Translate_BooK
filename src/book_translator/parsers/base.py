"""Contrato base para analisadores de formatos de entrada (parsers)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from book_translator.core.models import Document


@runtime_checkable
class ParserInterface(Protocol):
    """Protocolo formal para conversores de formato bruto em Document canônico."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        """Extensões suportadas pelo parser (ex: ('.epub',))."""
        ...

    def can_parse(self, file_path: Path | str) -> bool:
        """Verifica se o arquivo fornecido pode ser processado por este parser."""
        ...

    def parse(self, file_path: Path | str) -> Document:
        """Executa a extração e converte para a representação canônica Document."""
        ...
