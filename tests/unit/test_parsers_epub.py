"""Testes unitários para o parser canônico de EPUB (EPUB 2 e EPUB 3)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from book_translator.core.document import (
    DialogueBlock,
    Heading,
    Paragraph,
)
from book_translator.errors import ParsingError
from book_translator.parsers.epub import EpubParser


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_sample_epub2(file_path: Path) -> None:
    """Gera programaticamente um arquivo EPUB 2.0 válido com TOC NCX e múltiplos capítulos."""
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    content_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>EPUB2 Classic Tales</dc:title>
    <dc:creator>Charles Dickens</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="bookid">urn:uuid:12345-epub2</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="ch01.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="ch02.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ncx"/>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>"""

    toc_ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>Chapter 1: The Call</text></navLabel>
      <content src="ch01.xhtml"/>
    </navPoint>
    <navPoint id="np2" playOrder="2">
      <navLabel><text>Chapter 2: The Departure</text></navLabel>
      <content src="ch02.xhtml"/>
    </navPoint>
  </navMap>
</ncx>"""

    ch01_xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 1</title></head>
<body>
  <h1>Chapter 1: The Call</h1>
  <p>The bell rang with <em>urgent persistence</em> through the empty house.</p>
  <p>— Who could be calling at this hour? asked John.</p>
</body>
</html>"""

    ch02_xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 2</title></head>
<body>
  <h1>Chapter 2: The Departure</h1>
  <p>The dawn brought cold rain and misty winds.</p>
</body>
</html>"""

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype deve ser gravado descompactado por especificação EPUB
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", toc_ncx)
        zf.writestr("OEBPS/ch01.xhtml", ch01_xhtml)
        zf.writestr("OEBPS/ch02.xhtml", ch02_xhtml)


def create_sample_epub3(file_path: Path) -> None:
    """Gera programaticamente um arquivo EPUB 3.0 válido com documento Nav, notas e imagens."""
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    package_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>EPUB3 Modern Journey</dc:title>
    <dc:creator>Arthur Conan Doyle</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">urn:uuid:98765-epub3</dc:identifier>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="img1" href="images/castle.png" media-type="image/png"/>
  </manifest>
  <spine>
    <itemref idref="nav"/>
    <itemref idref="ch1"/>
  </spine>
</package>"""

    nav_xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Table of Contents</h1>
    <ol>
      <li><a href="text/ch1.xhtml">Chapter 1: The Castle</a></li>
    </ol>
  </nav>
</body>
</html>"""

    ch1_xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Chapter 1: The Castle</title></head>
<body>
  <h1>Chapter 1: The Castle</h1>
  <p>The carriage halted before the <strong>ancient gates</strong> of the fortress.</p>
  <p>— We have arrived, master, whispered the driver.</p>
  <img src="../images/castle.png" alt="Castle towers under moonlight"/>
  <aside epub:type="footnote" id="fn01">
    <p>1. Built in the late Middle Ages by Duke Robert.</p>
  </aside>
</body>
</html>"""

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("EPUB/package.opf", package_opf)
        zf.writestr("EPUB/nav.xhtml", nav_xhtml)
        zf.writestr("EPUB/text/ch1.xhtml", ch1_xhtml)
        zf.writestr("EPUB/images/castle.png", b"\x89PNG\r\n\x1a\nfakeimage")


def test_epub2_parser_structure_and_spine_order(tmp_path: Path) -> None:
    epub_path = tmp_path / "book_epub2.epub"
    create_sample_epub2(epub_path)

    parser = EpubParser()
    assert parser.can_parse(epub_path) is True

    doc = parser.parse(epub_path)
    assert doc.metadata.title == "EPUB2 Classic Tales"
    assert doc.metadata.author == "Charles Dickens"
    assert doc.metadata.source_format == "epub"

    # Verifica que TOC NCX NÃO virou capítulo de texto (prevenção de duplicação)
    assert len(doc.chapters) == 2

    # Verifica primeiro capítulo da spine
    ch1 = doc.chapters[0]
    assert "Chapter 1" in ch1.title
    assert ch1.metadata["original_href"] == "OEBPS/ch01.xhtml"
    assert len(ch1.headings) == 1
    assert ch1.headings[0].level == 1
    assert len(ch1.paragraphs) == 1
    assert "urgent persistence" in ch1.paragraphs[0].normalized_text
    assert len(ch1.paragraphs[0].spans) == 1
    assert ch1.paragraphs[0].spans[0].style == "italic"
    assert len(ch1.dialogue_blocks) == 1
    assert ch1.dialogue_blocks[0].dialogue_marker == "—"
    assert "Who could be calling" in ch1.dialogue_blocks[0].normalized_text

    # Verifica segundo capítulo da spine
    ch2 = doc.chapters[1]
    assert "Chapter 2" in ch2.title
    assert ch2.metadata["original_href"] == "OEBPS/ch02.xhtml"
    assert len(ch2.paragraphs) == 1
    assert "dawn brought cold rain" in ch2.paragraphs[0].normalized_text

    # Ordem determinística global
    linear_units = doc.get_linear_reading_order()
    assert len(linear_units) == 5
    assert isinstance(linear_units[0], Heading)
    assert isinstance(linear_units[1], Paragraph)
    assert isinstance(linear_units[2], DialogueBlock)
    assert isinstance(linear_units[3], Heading)
    assert isinstance(linear_units[4], Paragraph)


def test_epub3_parser_nav_deduplication_and_footnotes(tmp_path: Path) -> None:
    epub_path = tmp_path / "book_epub3.epub"
    create_sample_epub3(epub_path)

    parser = EpubParser()
    doc = parser.parse(epub_path)

    assert doc.metadata.title == "EPUB3 Modern Journey"
    assert doc.metadata.author == "Arthur Conan Doyle"

    # Nav (TOC) estava na spine mas NÃO foi duplicado como capítulo de leitura
    assert len(doc.chapters) == 1

    ch = doc.chapters[0]
    assert ch.metadata["original_href"] == "EPUB/text/ch1.xhtml"
    assert "The Castle" in ch.title

    # Paragraph com span negrito
    assert len(ch.paragraphs) == 1
    assert "ancient gates" in ch.paragraphs[0].normalized_text
    assert ch.paragraphs[0].spans[0].style == "bold"

    # Diálogo
    assert len(ch.dialogue_blocks) == 1
    assert "We have arrived, master" in ch.dialogue_blocks[0].normalized_text

    # Imagem com caminho resolvido dentro do EPUB
    assert len(ch.image_placeholders) == 1
    assert ch.image_placeholders[0].relative_path == "EPUB/images/castle.png"

    # Nota de rodapé identificada por epub:type="footnote"
    assert len(ch.footnotes) == 1
    assert "Duke Robert" in ch.footnotes[0].normalized_text


def test_epub_parser_immutability(tmp_path: Path) -> None:
    """Garante que o parser de EPUB não modifica o arquivo original em nenhum byte ou timestamp."""
    epub_path = tmp_path / "immutable.epub"
    create_sample_epub2(epub_path)

    stat_before = epub_path.stat()
    hash_before = compute_sha256(epub_path)

    parser = EpubParser()
    doc = parser.parse(epub_path)
    assert doc is not None

    stat_after = epub_path.stat()
    hash_after = compute_sha256(epub_path)

    assert stat_before.st_mtime == stat_after.st_mtime
    assert stat_before.st_size == stat_after.st_size
    assert hash_before == hash_after


def test_epub_corrupted_errors(tmp_path: Path) -> None:
    # 1. Arquivo não é ZIP
    fake_epub = tmp_path / "fake.epub"
    fake_epub.write_bytes(b"NOT A ZIP FILE")
    parser = EpubParser()
    with pytest.raises(ParsingError, match="corrompido"):
        parser.parse(fake_epub)

    # 2. ZIP sem container.xml
    no_container = tmp_path / "no_container.epub"
    with zipfile.ZipFile(no_container, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    with pytest.raises(ParsingError, match="container.xml"):
        parser.parse(no_container)
