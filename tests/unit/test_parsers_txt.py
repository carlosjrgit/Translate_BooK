"""Testes unitários para o parser de arquivos TXT."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.core.document import DialogueBlock, Heading, Paragraph
from book_translator.errors import ParsingError
from book_translator.parsers.txt import TxtParser


def test_txt_parser_utf8_with_chapters(tmp_path: Path) -> None:
    sample_content = (
        "CHAPTER 1: THE BEGINNING\n\n"
        "The night was cold and silent.\n\n"
        "— Who goes there? asked the guard.\n\n"
        "CHAPTER 2: THE JOURNEY\n\n"
        "Morning came with heavy mist.\n"
    )
    txt_file = tmp_path / "book.txt"
    txt_file.write_text(sample_content, encoding="utf-8")

    parser = TxtParser()
    assert parser.can_parse(txt_file) is True

    doc = parser.parse(txt_file, title="Test Book")
    assert doc.metadata.title == "Test Book"
    assert doc.metadata.source_format == "txt"
    assert len(doc.chapters) == 2

    # Capítulo 1
    ch1 = doc.chapters[0]
    assert "CHAPTER 1" in ch1.title
    assert len(ch1.headings) == 1
    assert ch1.headings[0].level == 1
    assert len(ch1.paragraphs) == 1
    assert ch1.paragraphs[0].normalized_text == "The night was cold and silent."
    assert len(ch1.dialogue_blocks) == 1
    assert ch1.dialogue_blocks[0].dialogue_marker == "—"
    assert "Who goes there?" in ch1.dialogue_blocks[0].normalized_text

    # Verifica ordem sequencial de leitura no capítulo 1
    seq1 = ch1.get_reading_sequence()
    assert len(seq1) == 3
    assert isinstance(seq1[0], Heading)
    assert isinstance(seq1[1], Paragraph)
    assert isinstance(seq1[2], DialogueBlock)


def test_txt_parser_latin1_encoding(tmp_path: Path) -> None:
    sample_content = (
        "CAPÍTULO 1\n\n"
        "História com acentuação: coração, maçã e café.\n\n"
        "- Olá amigo! - disse ele.\n"
    )
    txt_file = tmp_path / "latin1_book.txt"
    txt_file.write_bytes(sample_content.encode("iso-8859-1"))

    parser = TxtParser()
    doc = parser.parse(txt_file)

    assert len(doc.chapters) == 1
    ch = doc.chapters[0]
    assert "coração" in ch.paragraphs[0].normalized_text
    assert len(ch.dialogue_blocks) == 1


def test_txt_parser_utf8_bom(tmp_path: Path) -> None:
    sample_content = "CHAPTER 1\n\nSample text with UTF-8 BOM prefix.\n"
    txt_file = tmp_path / "bom_book.txt"
    txt_file.write_bytes(b"\xef\xbb\xbf" + sample_content.encode("utf-8"))

    parser = TxtParser()
    doc = parser.parse(txt_file)

    assert len(doc.chapters) == 1
    assert "Sample text" in doc.chapters[0].paragraphs[0].normalized_text


def test_txt_parser_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    parser = TxtParser()
    with pytest.raises(ParsingError, match="vazio"):
        parser.parse(empty_file)
