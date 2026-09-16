"""Testes unitários para o parser nativo de documentos DOCX."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from book_translator.core.document import DialogueBlock, Footnote, Heading, Paragraph
from book_translator.errors import ParsingError
from book_translator.parsers.docx import DocxParser


def create_sample_docx(file_path: Path) -> None:
    """Cria um arquivo DOCX válido em disco utilizando apenas zipfile."""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml"
    ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/footnotes.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    Target="docProps/core.xml"/>
</Relationships>"""

    core_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
  xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>The Fortress Chronicles</dc:title>
  <dc:creator>Jane Doe</dc:creator>
</cp:coreProperties>"""

    footnotes_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:footnote w:id="1">
    <w:p><w:r><w:t>Ancient fortress built in the 12th century.</w:t></w:r></w:p>
  </w:footnote>
</w:footnotes>"""

    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Chapter 1: The Fortress</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>The stones were </w:t></w:r>
      <w:r><w:rPr><w:b/></w:rPr><w:t>very old</w:t></w:r>
      <w:r><w:t> and covered in </w:t></w:r>
      <w:r><w:rPr><w:i/></w:rPr><w:t>moss</w:t></w:r>
      <w:r><w:t>.</w:t></w:r>
      <w:r><w:footnoteReference w:id="1"/></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>— Halt and state your business! commanded the sentry.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("docProps/core.xml", core_xml)
        zf.writestr("word/footnotes.xml", footnotes_xml)
        zf.writestr("word/document.xml", document_xml)


def test_docx_parser_success(tmp_path: Path) -> None:
    docx_file = tmp_path / "sample.docx"
    create_sample_docx(docx_file)

    parser = DocxParser()
    assert parser.can_parse(docx_file) is True

    doc = parser.parse(docx_file)
    assert doc.metadata.title == "The Fortress Chronicles"
    assert doc.metadata.author == "Jane Doe"
    assert doc.metadata.source_format == "docx"
    assert len(doc.chapters) == 1

    ch = doc.chapters[0]
    assert ch.title == "Chapter 1: The Fortress"

    # Heading
    assert len(ch.headings) == 1
    assert ch.headings[0].level == 1

    # Paragraph com spans
    assert len(ch.paragraphs) == 1
    p1 = ch.paragraphs[0]
    assert "very old and covered in moss." in p1.normalized_text
    styles = {s.style for s in p1.spans}
    assert "bold" in styles
    assert "italic" in styles

    # Diálogo
    assert len(ch.dialogue_blocks) == 1
    diag = ch.dialogue_blocks[0]
    assert diag.dialogue_marker == "—"
    assert "Halt and state your business!" in diag.normalized_text

    # Footnote
    assert len(ch.footnotes) == 1
    fn = ch.footnotes[0]
    assert fn.marker == "1"
    assert "12th century" in fn.normalized_text

    # Ordem determinística
    seq = ch.get_reading_sequence()
    assert isinstance(seq[0], Heading)
    assert isinstance(seq[1], Paragraph)
    assert isinstance(seq[2], Footnote)
    assert isinstance(seq[3], DialogueBlock)


def test_docx_parser_corrupted_file(tmp_path: Path) -> None:
    corrupted_file = tmp_path / "corrupted.docx"
    corrupted_file.write_bytes(b"PK\x03\x04not_a_valid_zip_content")

    parser = DocxParser()
    with pytest.raises(ParsingError, match="corrompido"):
        parser.parse(corrupted_file)


def test_docx_parser_missing_document_xml(tmp_path: Path) -> None:
    bad_docx = tmp_path / "missing_doc.docx"
    with zipfile.ZipFile(bad_docx, "w") as zf:
        zf.writestr("something_else.txt", "hello")

    parser = DocxParser()
    with pytest.raises(ParsingError, match="ausente"):
        parser.parse(bad_docx)


def test_docx_parser_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.docx"
    empty_file.write_bytes(b"")

    parser = DocxParser()
    with pytest.raises(ParsingError, match="vazio"):
        parser.parse(empty_file)
