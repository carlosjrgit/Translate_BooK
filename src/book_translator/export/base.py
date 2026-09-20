"""Contratos e modelos para exportação e reconstrução do documento traduzido."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from book_translator.core.models import Document


@dataclass
class ExportOptions:
    """Opções de customização para reconstrução do documento."""

    preserve_formatting: bool = True
    include_translator_preface: bool = False
    include_metadata: bool = True
    include_footnotes: bool = True
    target_encoding: str = "utf-8"
    custom_title: str | None = None
    custom_author: str | None = None
    extra_options: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ExporterInterface(Protocol):
    """Protocolo formal para exportadores de documentos em PT-BR."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        """Formatos aceitos por este exportador (ex: ('epub', 'docx', 'txt'))."""
        ...

    def can_export(self, format_name: str) -> bool:
        """Verifica se o formato solicitado é suportado."""
        ...

    def export(
        self,
        document: Document,
        output_path: Path | str,
        options: ExportOptions | None = None,
    ) -> Path:
        """Gera o arquivo reconstruído sem jamais sobrescrever o arquivo original."""
        ...
