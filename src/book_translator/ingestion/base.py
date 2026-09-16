"""Contratos e modelos do pipeline de ingestão e inspeção prévia de documentos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class IngestionInspection:
    """Resultado da inspeção preliminar do arquivo de entrada."""

    file_path: Path
    detected_format: str
    file_size_bytes: int
    has_text_layer: bool = True
    requires_ocr: bool = False
    estimated_pages_or_chapters: int = 0


@runtime_checkable
class IngestionInspectorInterface(Protocol):
    """Protocolo de inspeção e triagem de arquivos de entrada."""

    def inspect(self, file_path: Path | str) -> IngestionInspection:
        """Inspeciona o arquivo para determinar formato e necessidade de OCR."""
        ...
