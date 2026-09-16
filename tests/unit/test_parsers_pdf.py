"""Testes unitários para o parser de PDF, detecção de PDF escaneado e heurísticas."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from book_translator.errors import NeedsOcrError, ParsingError
from book_translator.ingestion.inspector import IngestionInspector
from book_translator.parsers.pdf import PdfClassification, PdfParser, PdfParserConfig


def _create_synthetic_pdf(pages_text: list[str]) -> bytes:
    """Gera bytes de um PDF válido sem dependências externas adicionais."""
    num_pages = len(pages_text)
    page_objs_start = 4
    content_start = page_objs_start + num_pages

    body: list[bytes] = [b"%PDF-1.4"]
    offsets: dict[int, int] = {}

    def add_obj(obj_id: int, content: str) -> None:
        offsets[obj_id] = sum(len(b) + 1 for b in body)
        body.append(f"{obj_id} 0 obj\n{content}\nendobj".encode("latin1", errors="replace"))

    kids = " ".join(f"{page_objs_start + i} 0 R" for i in range(num_pages))
    add_obj(1, "<</Type /Catalog /Pages 2 0 R>>")
    add_obj(2, f"<</Type /Pages /Kids [{kids}] /Count {num_pages}>>")
    add_obj(3, "<</Type /Font /Subtype /Type1 /BaseFont /Helvetica>>")

    for i, text in enumerate(pages_text):
        p_id = page_objs_start + i
        c_id = content_start + i
        add_obj(
            p_id,
            f"<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {c_id} 0 R /Resources <</Font <</F1 3 0 R>>>>>>",
        )

        stream_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
        for line in text.splitlines():
            if line:
                esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                stream_lines.append(f"({esc}) Tj")
                stream_lines.append("0 -16 Td")
        stream_lines.append("ET")
        stream_content = "\n".join(stream_lines)
        c_bytes = stream_content.encode("latin1", errors="replace")
        add_obj(c_id, f"<</Length {len(c_bytes)}>>\nstream\n{stream_content}\nendstream")

    xref_offset = sum(len(b) + 1 for b in body)
    total_objs = content_start + num_pages
    body.append(f"xref\n0 {total_objs}".encode("latin1"))
    body.append(b"0000000000 65535 f ")
    for i in range(1, total_objs):
        off = offsets.get(i, 0)
        body.append(f"{off:010d} 00000 n ".encode("latin1"))
    body.append(
        f"trailer\n<</Size {total_objs} /Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF".encode(
            "latin1"
        )
    )
    return b"\n".join(body)


def test_textual_pdf_extraction_and_structure(tmp_path: Path) -> None:
    """Verifica a extração estruturada de PDF textual, páginas e ordem de leitura."""
    p1 = (
        "CHAPTER 1\n\n"
        "It was the best of times in our automated translation project.\n"
        "- Welcome to the journey, said the narrator."
    )
    p2 = (
        "CHAPTER 2\n\n"
        "The second phase of the journey brought new challenges.\n"
        "Every paragraph was meticulously analyzed."
    )

    pdf_bytes = _create_synthetic_pdf([p1, p2])
    pdf_file = tmp_path / "valid_book.pdf"
    pdf_file.write_bytes(pdf_bytes)

    parser = PdfParser()
    doc = parser.parse(pdf_file, title="Valid Book")

    assert doc.metadata.source_format == "pdf"
    assert doc.metadata.extra["pdf_classification"] == PdfClassification.TEXTUAL.value
    assert len(doc.chapters) == 2

    ch1 = doc.chapters[0]
    assert "CHAPTER 1" in ch1.title
    assert len(ch1.headings) == 1
    assert ch1.headings[0].source_location.page_number == 1
    assert len(ch1.dialogue_blocks) == 1
    assert ch1.dialogue_blocks[0].dialogue_marker == "-"
    assert ch1.dialogue_blocks[0].source_location.page_number == 1

    ch2 = doc.chapters[1]
    assert "CHAPTER 2" in ch2.title
    assert len(ch2.paragraphs) >= 1
    assert ch2.paragraphs[0].source_location.page_number == 2

    # Verifica ordem linear de leitura contínua e estritamente crescente
    reading_order = [u.reading_order for u in doc.get_linear_reading_order()]
    assert reading_order == sorted(reading_order)
    assert len(reading_order) >= 4


def test_scanned_pdf_detection_and_rejection(tmp_path: Path) -> None:
    """Verifica que PDFs sem camada textual utilizável são classificados como SCANNED e rejeitados.
    """
    # 3 páginas em branco simulando PDF escaneado sem texto
    pdf_bytes = _create_synthetic_pdf(["", "", ""])
    pdf_file = tmp_path / "scanned_doc.pdf"
    pdf_file.write_bytes(pdf_bytes)

    # 1. Teste de inspeção
    inspector = IngestionInspector()
    inspection = inspector.inspect(pdf_file)
    assert inspection.detected_format == "pdf"
    assert inspection.pdf_classification == "SCANNED_NEEDS_OCR"
    assert inspection.has_text_layer is False
    assert inspection.requires_ocr is True
    assert inspection.estimated_pages_or_chapters == 3

    # 2. Teste do parser garantindo que não gera tradução sobre documento sem texto
    parser = PdfParser()
    with pytest.raises(NeedsOcrError) as exc_info:
        parser.parse(pdf_file)

    assert "SCANNED_NEEDS_OCR" in str(exc_info.value)
    assert "Requer OCR" in str(exc_info.value)


def test_mixed_pdf_classification(tmp_path: Path) -> None:
    """Verifica a classificação de PDF misto com páginas textuais e escaneadas."""
    p1 = (
        "This is a legitimate page full of textual content designed for processing.\n"
        "It has plenty of characters to qualify as a valid textual layer."
    )
    p2 = ""  # Página vazia (escaneada)
    p3 = ""  # Página vazia (escaneada)

    pdf_bytes = _create_synthetic_pdf([p1, p2, p3])
    pdf_file = tmp_path / "mixed_doc.pdf"
    pdf_file.write_bytes(pdf_bytes)

    inspector = IngestionInspector()
    inspection = inspector.inspect(pdf_file)
    assert inspection.detected_format == "pdf"
    assert inspection.pdf_classification == "MIXED"
    assert inspection.has_text_layer is True
    assert inspection.requires_ocr is True

    parser = PdfParser()
    doc = parser.parse(pdf_file)
    assert doc.metadata.extra["pdf_classification"] == "MIXED"
    assert len(doc.chapters) >= 1


def test_dehyphenation_heuristic(tmp_path: Path) -> None:
    """Verifica a heurística de desifenização no final de linha."""
    p_text = (
        "This is an extraor-\n"
        "dinary inter-\n"
        "national translation platform with robust parsing."
    )
    pdf_bytes = _create_synthetic_pdf([p_text])
    pdf_file = tmp_path / "hyphen_test.pdf"
    pdf_file.write_bytes(pdf_bytes)

    # 1. Com desifenização ativada (padrão)
    parser_enabled = PdfParser(config=PdfParserConfig(fix_hyphenation=True))
    doc_enabled = parser_enabled.parse(pdf_file)
    p_content = doc_enabled.chapters[0].paragraphs[0].normalized_text
    assert "extraordinary" in p_content
    assert "international" in p_content

    # 2. Com desifenização desativada
    parser_disabled = PdfParser(config=PdfParserConfig(fix_hyphenation=False))
    doc_disabled = parser_disabled.parse(pdf_file)
    p_content_disabled = doc_disabled.chapters[0].paragraphs[0].normalized_text
    assert "extraor- dinary" in p_content_disabled or "extraor-" in p_content_disabled


def test_headers_footers_and_page_numbers_heuristics(tmp_path: Path) -> None:
    """Verifica a remoção de cabeçalhos repetidos e números de página isolados."""
    pages = [
        "TRANSLATE BOOK SYSTEM\n\nPage content on chapter one here.\n\n1",
        "TRANSLATE BOOK SYSTEM\n\nPage content on chapter two here.\n\n2",
        "TRANSLATE BOOK SYSTEM\n\nPage content on chapter three here.\n\n3",
    ]
    pdf_bytes = _create_synthetic_pdf(pages)
    pdf_file = tmp_path / "headers_footers_test.pdf"
    pdf_file.write_bytes(pdf_bytes)

    # 1. Com heurísticas ativadas (padrão)
    parser = PdfParser(
        config=PdfParserConfig(remove_headers_footers=True, remove_page_numbers=True)
    )
    doc = parser.parse(pdf_file)

    all_texts = [
        u.normalized_text
        for c in doc.chapters
        for u in c.paragraphs + c.headings + c.dialogue_blocks
    ]
    # Cabeçalho recorrente e números de página não devem poluir os parágrafos de narrativa
    for text in all_texts:
        assert "TRANSLATE BOOK SYSTEM" not in text
        assert text not in ("1", "2", "3")

    # 2. Com heurísticas desativadas
    parser_disabled = PdfParser(
        config=PdfParserConfig(remove_headers_footers=False, remove_page_numbers=False)
    )
    doc_raw = parser_disabled.parse(pdf_file)
    all_raw_texts = [
        u.normalized_text for c in doc_raw.chapters for u in c.paragraphs + c.headings
    ]
    assert any("TRANSLATE BOOK SYSTEM" in t for t in all_raw_texts)


def test_pdf_immutability(tmp_path: Path) -> None:
    """Garante que o arquivo PDF original em disco jamais é alterado durante o parse."""
    pdf_bytes = _create_synthetic_pdf(["Line A\n\nLine B with sufficient content length for test."])
    pdf_file = tmp_path / "original_immutable.pdf"
    pdf_file.write_bytes(pdf_bytes)

    mtime_before = pdf_file.stat().st_mtime_ns
    size_before = pdf_file.stat().st_size
    sha256_before = hashlib.sha256(pdf_bytes).hexdigest()

    parser = PdfParser()
    doc = parser.parse(pdf_file)

    assert doc is not None
    mtime_after = pdf_file.stat().st_mtime_ns
    size_after = pdf_file.stat().st_size
    sha256_after = hashlib.sha256(pdf_file.read_bytes()).hexdigest()

    assert mtime_after == mtime_before
    assert size_after == size_before
    assert sha256_after == sha256_before


def test_corrupted_pdf_handling(tmp_path: Path) -> None:
    """Verifica que PDFs truncados ou inválidos disparam ParsingError amigável."""
    corrupted_file = tmp_path / "corrupted.pdf"
    corrupted_file.write_bytes(b"%PDF-1.4\n1 0 obj <</Type ... incomplete truncated data")

    parser = PdfParser()
    with pytest.raises(ParsingError) as exc_info:
        parser.parse(corrupted_file)

    assert "corrompido" in str(exc_info.value).lower() or "stream inválido" in str(
        exc_info.value
    ).lower()
