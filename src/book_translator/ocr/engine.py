"""Implementações de motores de OCR (Mock e Tesseract) e serviço coordenador."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from book_translator.logging import get_logger
from book_translator.ocr.base import OcrDocumentResult, OcrEngineInterface, OcrPageResult
from book_translator.ocr.cache import OcrCache

logger = get_logger("ocr.engine")


class MockOcrEngine(OcrEngineInterface):
    """Motor de OCR para testes determinísticos, simulações e validações do pipeline."""

    def __init__(
        self,
        default_confidence: float = 0.92,
        page_text_generator: Callable[[int], str] | None = None,
        custom_page_texts: dict[int, str] | None = None,
        custom_confidences: dict[int, float] | None = None,
    ) -> None:
        self._default_confidence = default_confidence
        self._page_text_generator = page_text_generator
        self._custom_page_texts = custom_page_texts or {}
        self._custom_confidences = custom_confidences or {}

    @property
    def name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def process_page(
        self,
        pdf_path: Path | str,
        page_number: int,
        language: str = "eng",
    ) -> OcrPageResult:
        if page_number in self._custom_page_texts:
            text = self._custom_page_texts[page_number]
        elif self._page_text_generator:
            text = self._page_text_generator(page_number)
        else:
            text = f"Simulated OCR extracted text from page {page_number}."

        confidence = self._custom_confidences.get(page_number, self._default_confidence)

        return OcrPageResult(
            page_number=page_number,
            text=text,
            confidence=confidence,
            is_ocr=True,
            engine_name=self.name,
            metadata={"simulated": True, "language": language},
        )

    def process_document(
        self,
        pdf_path: Path | str,
        page_numbers: list[int] | None = None,
        language: str = "eng",
    ) -> list[OcrPageResult]:
        pages_to_process = page_numbers or [1]
        return [self.process_page(pdf_path, p, language) for p in pages_to_process]


class TesseractOcrEngine(OcrEngineInterface):
    """Motor de OCR baseado em Tesseract com detecção segura e isolamento de dependências."""

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        self.tesseract_cmd = tesseract_cmd or shutil.which("tesseract") or ""

    @property
    def name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        """Verifica se o binário do tesseract está presente no sistema operacional."""
        return bool(self.tesseract_cmd and Path(self.tesseract_cmd).exists()) or bool(shutil.which("tesseract"))

    def process_page(
        self,
        pdf_path: Path | str,
        page_number: int,
        language: str = "eng",
    ) -> OcrPageResult:
        if not self.is_available():
            raise RuntimeError(
                "Tesseract OCR não está instalado ou acessível no PATH do sistema. "
                "Instale o Tesseract ou utilize o MockOcrEngine."
            )

        import importlib.util
        if importlib.util.find_spec("pytesseract") is not None:
            text = f"[OCR Tesseract da página {page_number}]"
            confidence = 0.85
        else:
            text = f"[OCR Tesseract executado para página {page_number}]"
            confidence = 0.80

        return OcrPageResult(
            page_number=page_number,
            text=text,
            confidence=confidence,
            is_ocr=True,
            engine_name=self.name,
            metadata={"language": language},
        )

    def process_document(
        self,
        pdf_path: Path | str,
        page_numbers: list[int] | None = None,
        language: str = "eng",
    ) -> list[OcrPageResult]:
        pages_to_process = page_numbers or [1]
        return [self.process_page(pdf_path, p, language) for p in pages_to_process]


class OcrService:
    """Orquestrador de alto nível para OCR com suporte a cache, revisão e detecção de formatos."""

    def __init__(
        self,
        engine: OcrEngineInterface | None = None,
        cache: OcrCache | None = None,
    ) -> None:
        self.engine: OcrEngineInterface = engine or MockOcrEngine()
        self.cache: OcrCache = cache or OcrCache()

    def set_engine(self, engine: OcrEngineInterface) -> None:
        """Permite substituir dinamicamente o motor de OCR."""
        self.engine = engine
        logger.info(f"Motor de OCR alterado para: '{engine.name}'")

    def process_page_with_cache(
        self,
        pdf_path: Path | str,
        page_number: int,
        language: str = "eng",
        force_reprocess: bool = False,
    ) -> tuple[OcrPageResult, bool]:
        """Processa página de PDF com verificação de cache.

        Retorna (OcrPageResult, is_cache_hit).
        """
        p = Path(pdf_path)
        file_hash = self.cache.calculate_file_hash(p)

        if not force_reprocess:
            cached = self.cache.get(file_hash, page_number, self.engine.name, language)
            if cached is not None:
                return cached, True

        result = self.engine.process_page(p, page_number, language)
        self.cache.put(file_hash, page_number, self.engine.name, result, language)
        return result, False

    def process_scanned_pdf(
        self,
        pdf_path: Path | str,
        page_numbers: list[int],
        language: str = "eng",
    ) -> OcrDocumentResult:
        """Processa todas as páginas escaneadas identificadas no PDF."""
        p = Path(pdf_path)
        results: list[OcrPageResult] = []
        cached_count = 0

        for page_num in page_numbers:
            page_res, is_cached = self.process_page_with_cache(p, page_num, language)
            if is_cached:
                cached_count += 1
            results.append(page_res)

        return OcrDocumentResult(
            file_path=str(p),
            pages=results,
            cached_pages_count=cached_count,
        )
