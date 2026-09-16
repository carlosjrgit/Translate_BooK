"""Teste de equivalência estrutural entre formatos (TXT, Markdown, HTML, DOCX)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from book_translator.core.document import DialogueBlock, Heading, Paragraph
from book_translator.parsers.factory import parse_document


def create_equivalent_docx(file_path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>"""

    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Chapter 1: The Encounter</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>The old castle stood against the windy hill.</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>— We must find shelter before nightfall, said the traveler.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)


def test_parsers_structural_equivalence(tmp_path: Path) -> None:
    """Valida se documentos com conteúdo equivalente produzem a mesma estrutura canônica."""
    # 1. TXT
    txt_path = tmp_path / "book.txt"
    txt_path.write_text(
        "CHAPTER 1: THE ENCOUNTER\n\n"
        "The old castle stood against the windy hill.\n\n"
        "— We must find shelter before nightfall, said the traveler.\n",
        encoding="utf-8",
    )

    # 2. Markdown
    md_path = tmp_path / "book.md"
    md_path.write_text(
        "# Chapter 1: The Encounter\n\n"
        "The old castle stood against the windy hill.\n\n"
        "— We must find shelter before nightfall, said the traveler.\n",
        encoding="utf-8",
    )

    # 3. HTML
    html_path = tmp_path / "book.html"
    html_path.write_text(
        "<html><body>\n"
        "<h1>Chapter 1: The Encounter</h1>\n"
        "<p>The old castle stood against the windy hill.</p>\n"
        "<p>— We must find shelter before nightfall, said the traveler.</p>\n"
        "</body></html>",
        encoding="utf-8",
    )

    # 4. DOCX
    docx_path = tmp_path / "book.docx"
    create_equivalent_docx(docx_path)

    # Executa o parse via factory
    doc_txt = parse_document(txt_path)
    doc_md = parse_document(md_path)
    doc_html = parse_document(html_path)
    doc_docx = parse_document(docx_path)

    docs = [doc_txt, doc_md, doc_html, doc_docx]

    for doc in docs:
        assert len(doc.chapters) == 1
        ch = doc.chapters[0]

        # 1 Heading de nível 1
        assert len(ch.headings) == 1
        assert ch.headings[0].level == 1
        assert "encounter" in ch.headings[0].normalized_text.lower()

        # 1 Parágrafo narrativo
        assert len(ch.paragraphs) == 1
        assert "castle stood against" in ch.paragraphs[0].normalized_text

        # 1 Bloco de diálogo com travessão
        assert len(ch.dialogue_blocks) == 1
        assert ch.dialogue_blocks[0].dialogue_marker == "—"
        assert "shelter before nightfall" in ch.dialogue_blocks[0].normalized_text

        # Sequência de leitura idêntica: Heading -> Paragraph -> DialogueBlock
        seq = ch.get_reading_sequence()
        assert len(seq) == 3
        assert isinstance(seq[0], Heading)
        assert isinstance(seq[1], Paragraph)
        assert isinstance(seq[2], DialogueBlock)
