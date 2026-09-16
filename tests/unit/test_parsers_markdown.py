"""Testes unitários para o parser de arquivos Markdown."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.core.document import DialogueBlock, Heading, Paragraph
from book_translator.errors import ParsingError
from book_translator.parsers.markdown import MarkdownParser


def test_markdown_parser_formatting_spans_and_dialogue(tmp_path: Path) -> None:
    content = (
        "# Chapter 1: The Dark Forest\n\n"
        "The wind blew through the **ancient** trees and *whispered* secrets.\n\n"
        "— Do not go into the woods, warned the elder.\n\n"
        "Here is a note reference.[^1]\n\n"
        "[^1]: The ancient forest was planted three centuries ago.\n\n"
        "## Subheading: The Path\n\n"
        "* Item one in list\n"
        "* Item two in list\n"
    )
    md_file = tmp_path / "story.md"
    md_file.write_text(content, encoding="utf-8")

    parser = MarkdownParser()
    assert parser.can_parse(md_file) is True

    doc = parser.parse(md_file)
    assert len(doc.chapters) == 1
    ch = doc.chapters[0]
    assert ch.title == "Chapter 1: The Dark Forest"

    # Headings
    assert len(ch.headings) == 2
    assert ch.headings[0].level == 1
    assert ch.headings[1].level == 2
    assert ch.headings[1].normalized_text == "Subheading: The Path"

    # Paragraph com spans
    assert len(ch.paragraphs) >= 2
    p1 = ch.paragraphs[0]
    assert "ancient" in p1.normalized_text
    # Spans detectados (bold e italic)
    styles = {s.style for s in p1.spans}
    assert "bold" in styles
    assert "italic" in styles

    # Diálogo
    assert len(ch.dialogue_blocks) == 1
    diag = ch.dialogue_blocks[0]
    assert diag.dialogue_marker == "—"
    assert "Do not go into the woods" in diag.normalized_text

    # Footnote
    assert len(ch.footnotes) == 1
    fn = ch.footnotes[0]
    assert fn.marker == "1"
    assert "three centuries ago" in fn.normalized_text

    # Ordem determinística
    seq = ch.get_reading_sequence()
    assert isinstance(seq[0], Heading)
    assert isinstance(seq[1], Paragraph)
    assert isinstance(seq[2], DialogueBlock)


def test_markdown_parser_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("", encoding="utf-8")

    parser = MarkdownParser()
    with pytest.raises(ParsingError, match="vazio"):
        parser.parse(empty_file)
