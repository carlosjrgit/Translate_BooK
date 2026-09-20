"""Módulo de OCR opcional e substituível para processamento de PDFs escaneados."""

from book_translator.ocr.base import (
    OcrDocumentResult,
    OcrEngineInterface,
    OcrPageResult,
)
from book_translator.ocr.cache import OcrCache
from book_translator.ocr.engine import (
    MockOcrEngine,
    OcrService,
    TesseractOcrEngine,
)

__all__ = [
    "OcrDocumentResult",
    "OcrEngineInterface",
    "OcrPageResult",
    "OcrCache",
    "OcrService",
    "MockOcrEngine",
    "TesseractOcrEngine",
]
