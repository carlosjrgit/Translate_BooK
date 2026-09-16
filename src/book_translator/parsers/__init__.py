"""Módulo de parsers e extração estruturada de documentos."""

from __future__ import annotations

from book_translator.parsers.base import BaseParser, ParserInterface
from book_translator.parsers.docx import DocxParser
from book_translator.parsers.epub import EpubParser
from book_translator.parsers.factory import (
    get_parser_for_file,
    get_parser_for_format,
    parse_document,
)
from book_translator.parsers.html import HtmlParser
from book_translator.parsers.markdown import MarkdownParser
from book_translator.parsers.normalization import detect_encoding, normalize_unicode
from book_translator.parsers.pdf import PdfClassification, PdfParser, PdfParserConfig
from book_translator.parsers.txt import TxtParser

__all__ = [
    "ParserInterface",
    "BaseParser",
    "TxtParser",
    "MarkdownParser",
    "HtmlParser",
    "DocxParser",
    "EpubParser",
    "PdfParser",
    "PdfParserConfig",
    "PdfClassification",
    "get_parser_for_file",
    "get_parser_for_format",
    "parse_document",
    "detect_encoding",
    "normalize_unicode",
]
