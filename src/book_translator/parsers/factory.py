"""Fábrica e despachante unificado de parsers para formatos de entrada."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from book_translator.core.document import Document
from book_translator.errors import IngestionError
from book_translator.ingestion.inspector import IngestionInspector
from book_translator.logging import get_logger
from book_translator.parsers.base import ParserInterface
from book_translator.parsers.docx import DocxParser
from book_translator.parsers.epub import EpubParser
from book_translator.parsers.html import HtmlParser
from book_translator.parsers.markdown import MarkdownParser
from book_translator.parsers.pdf import PdfParser
from book_translator.parsers.txt import TxtParser

logger = get_logger("parsers.factory")


def get_parser_for_format(fmt: str) -> ParserInterface:
    """Retorna a instância de parser correspondente ao identificador de formato."""
    norm_fmt = fmt.strip().lower()
    if norm_fmt in ("txt", "text"):
        return TxtParser()
    if norm_fmt in ("markdown", "md"):
        return MarkdownParser()
    if norm_fmt in ("html", "htm", "xhtml"):
        return HtmlParser()
    if norm_fmt == "docx":
        return DocxParser()
    if norm_fmt == "epub":
        return EpubParser()
    if norm_fmt == "pdf":
        return PdfParser()

    raise IngestionError(f"Não há parser registrado para o formato '{fmt}'.")


def get_parser_for_file(file_path: Path | str) -> ParserInterface:
    """Detecta o formato do arquivo fornecido e retorna o parser adequado."""
    inspector = IngestionInspector()
    detected_fmt = inspector.detect_format(file_path)
    logger.debug(f"Formato detectado '{detected_fmt}' para '{file_path}'")
    return get_parser_for_format(detected_fmt)


def create_parser(
    file_path: Path | str,
    ocr_service: Any | None = None,
) -> ParserInterface:
    """Fábrica de parser que detecta formato e injeta serviço de OCR se aplicável."""
    inspector = IngestionInspector()
    detected_fmt = inspector.detect_format(file_path)
    if detected_fmt == "pdf":
        return PdfParser(ocr_service=ocr_service)
    return get_parser_for_format(detected_fmt)


def parse_document(file_path: Path | str, title: str | None = None) -> Document:
    """Ponto de entrada de alto nível: detecta formato e gera o Document canônico."""
    parser = get_parser_for_file(file_path)
    return parser.parse(file_path, title=title)

