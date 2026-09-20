"""Contratos, modelos e interfaces para o módulo opcional de OCR."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class OcrPageResult:
    """Resultado do processamento de OCR para uma página individual."""

    page_number: int  # 1-indexed
    text: str
    confidence: float | None = None  # 0.0 a 1.0 (ou None se a engine não fornecer)
    is_ocr: bool = True
    char_count: int = 0
    words_count: int = 0
    engine_name: str = ""
    needs_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.char_count and self.text:
            self.char_count = len(self.text)
        if not self.words_count and self.text:
            self.words_count = len(self.text.split())
        # Sinaliza necessidade de revisão quando confiança for baixa (< 0.70)
        if self.confidence is not None and self.confidence < 0.70:
            self.needs_review = True


@dataclass
class OcrDocumentResult:
    """Resultado consolidado de OCR para um documento ou conjunto de páginas."""

    file_path: str
    pages: list[OcrPageResult]
    total_pages_ocr: int = 0
    mean_confidence: float | None = None
    cached_pages_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.total_pages_ocr:
            self.total_pages_ocr = len(self.pages)
        if self.mean_confidence is None:
            scores = [p.confidence for p in self.pages if p.confidence is not None]
            if scores:
                self.mean_confidence = round(sum(scores) / len(scores), 4)


@runtime_checkable
class OcrEngineInterface(Protocol):
    """Protocolo formal para motores de OCR plugáveis e substituíveis."""

    @property
    def name(self) -> str:
        """Identificador único da engine de OCR (ex: 'mock', 'tesseract', 'easyocr')."""
        ...

    def is_available(self) -> bool:
        """Verifica se as dependências e binários necessários estão instalados no sistema."""
        ...

    def process_page(
        self,
        pdf_path: Path | str,
        page_number: int,
        language: str = "eng",
    ) -> OcrPageResult:
        """Processa uma única página (1-indexed) de um arquivo PDF."""
        ...

    def process_document(
        self,
        pdf_path: Path | str,
        page_numbers: list[int] | None = None,
        language: str = "eng",
    ) -> list[OcrPageResult]:
        """Processa páginas selecionadas ou todas as páginas de um PDF."""
        ...
