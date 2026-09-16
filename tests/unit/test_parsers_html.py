"""Testes unitários para o parser de arquivos HTML."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.errors import ParsingError
from book_translator.parsers.html import HtmlParser


def test_html_parser_valid_and_spans(tmp_path: Path) -> None:
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>The Great Novel</title>
    <meta name="author" content="Arthur Conan">
</head>
<body>
    <h1>Chapter 1: The Arrival</h1>
    <p>The carriage arrived with <strong>great speed</strong> and <em>thunder</em>.</p>
    <p>— Watson, come quickly! shouted Holmes.</p>
    <img src="images/carriage.png" alt="Carriage in the rain" />
    <aside class="footnote" id="fn1">1. A standard Victorian brougham carriage.</aside>
</body>
</html>"""
    html_file = tmp_path / "book.html"
    html_file.write_text(html_content, encoding="utf-8")

    parser = HtmlParser()
    assert parser.can_parse(html_file) is True

    doc = parser.parse(html_file)
    assert doc.metadata.title == "The Great Novel"
    assert doc.metadata.author == "Arthur Conan"
    assert len(doc.chapters) == 1

    ch = doc.chapters[0]
    assert ch.title == "Chapter 1: The Arrival"

    # Heading
    assert len(ch.headings) == 1
    assert ch.headings[0].level == 1

    # Parágrafo com spans
    assert len(ch.paragraphs) == 1
    p1 = ch.paragraphs[0]
    assert "carriage arrived" in p1.normalized_text
    styles = {s.style for s in p1.spans}
    assert "bold" in styles
    assert "italic" in styles

    # Diálogo
    assert len(ch.dialogue_blocks) == 1
    diag = ch.dialogue_blocks[0]
    assert diag.dialogue_marker == "—"
    assert "Watson, come quickly!" in diag.normalized_text

    # Imagem
    assert len(ch.image_placeholders) == 1
    assert ch.image_placeholders[0].original_src == "images/carriage.png"

    # Nota de rodapé
    assert len(ch.footnotes) == 1
    assert "Victorian brougham" in ch.footnotes[0].normalized_text


def test_html_parser_malformed_tolerance(tmp_path: Path) -> None:
    malformed_content = """
    <h1>Unclosed Title
    <p>Paragraph with unclosed <b>bold and <i>italic tags.
    <p>— Open dialogue without closing p tag
    """
    html_file = tmp_path / "malformed.html"
    html_file.write_text(malformed_content, encoding="utf-8")

    parser = HtmlParser()
    doc = parser.parse(html_file)

    assert len(doc.chapters) == 1
    ch = doc.chapters[0]
    assert len(ch.headings) == 1
    assert len(ch.paragraphs) == 1
    assert len(ch.dialogue_blocks) == 1


def test_html_parser_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.html"
    empty_file.write_text("", encoding="utf-8")

    parser = HtmlParser()
    with pytest.raises(ParsingError, match="vazio"):
        parser.parse(empty_file)
