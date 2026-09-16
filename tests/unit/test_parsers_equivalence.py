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


def create_equivalent_epub(file_path: Path) -> None:
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Equivalent Book</dc:title>
    <dc:identifier id="pub-id">urn:uuid:12345</dc:identifier>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
  </spine>
</package>"""

    xhtml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 1: The Encounter</title></head>
  <body>
    <h1>Chapter 1: The Encounter</h1>
    <p>The old castle stood against the windy hill.</p>
    <p>— We must find shelter before nightfall, said the traveler.</p>
  </body>
</html>"""

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", xhtml)


def create_equivalent_pdf(file_path: Path) -> None:
    # PDF sintético com fontes padrão Type1
    lines = [
        "CHAPTER 1: THE ENCOUNTER",
        "",
        "The old castle stood against the windy hill.",
        "",
        "- We must find shelter before nightfall, said the traveler.",
    ]
    stream_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
    for line in lines:
        if line:
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({esc}) Tj")
            stream_lines.append("0 -16 Td")
        else:
            stream_lines.append("0 -10 Td")
    stream_lines.append("ET")
    stream_content = "\n".join(stream_lines)
    c_bytes = stream_content.encode("latin1", errors="replace")

    body: list[bytes] = [
        b"%PDF-1.4",
        b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj",
        b"2 0 obj\n<</Type /Pages /Kids [4 0 R] /Count 1>>\nendobj",
        b"3 0 obj\n<</Type /Font /Subtype /Type1 /BaseFont /Helvetica>>\nendobj",
        b"4 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 5 0 R /Resources <</Font <</F1 3 0 R>>>>>>\nendobj",
        f"5 0 obj\n<</Length {len(c_bytes)}>>\nstream\n{stream_content}\nendstream\nendobj".encode(
            "latin1"
        ),
    ]
    xref_offset = sum(len(b) + 1 for b in body)
    body.append(b"xref\n0 6\n0000000000 65535 f ")
    for i in range(1, 6):
        off = sum(len(b) + 1 for b in body[:i])
        body.append(f"{off:010d} 00000 n ".encode("latin1"))
    trailer = f"trailer\n<</Size 6 /Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF"
    body.append(trailer.encode("latin1"))
    file_path.write_bytes(b"\n".join(body))


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

    # 5. EPUB
    epub_path = tmp_path / "book.epub"
    create_equivalent_epub(epub_path)

    # 6. PDF
    pdf_path = tmp_path / "book.pdf"
    create_equivalent_pdf(pdf_path)

    # Executa o parse via factory para todos os 6 formatos
    doc_txt = parse_document(txt_path)
    doc_md = parse_document(md_path)
    doc_html = parse_document(html_path)
    doc_docx = parse_document(docx_path)
    doc_epub = parse_document(epub_path)
    doc_pdf = parse_document(pdf_path)

    docs = [doc_txt, doc_md, doc_html, doc_docx, doc_epub, doc_pdf]

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

        # 1 Bloco de diálogo com marcador reconhecido
        assert len(ch.dialogue_blocks) == 1
        assert ch.dialogue_blocks[0].dialogue_marker in ("—", "-")
        assert "shelter before nightfall" in ch.dialogue_blocks[0].normalized_text

        # Sequência de leitura idêntica: Heading -> Paragraph -> DialogueBlock
        seq = ch.get_reading_sequence()
        assert len(seq) == 3
        assert isinstance(seq[0], Heading)
        assert isinstance(seq[1], Paragraph)
        assert isinstance(seq[2], DialogueBlock)
