"""Testes unitários para o módulo opcional de OCR (Prompt 23)."""

from pathlib import Path

import pypdf
import pytest

from book_translator.core.models import Chapter, Document, Paragraph, SourceLocation
from book_translator.errors import NeedsOcrError
from book_translator.ocr import (
    MockOcrEngine,
    OcrCache,
    OcrPageResult,
    OcrService,
)
from book_translator.parsers.pdf import PdfParser
from book_translator.preprocessing.segmenter import InitialSegmenter


@pytest.fixture
def sample_pdf_files(tmp_path: Path) -> dict[str, Path]:
    """Cria arquivos PDF de teste (um puramente textual e um simulando escaneado)."""
    # 1. PDF Textual Válido
    textual_pdf = tmp_path / "valid_text.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    # Adiciona anotação de texto para simular camada textual
    writer.add_metadata({
        "/Title": "Livro Textual Válido",
        "/Author": "Escritor Famoso",
    })
    with textual_pdf.open("wb") as f:
        writer.write(f)

    # 2. PDF Escaneado (sem texto extraível)
    scanned_pdf = tmp_path / "scanned_book.pdf"
    s_writer = pypdf.PdfWriter()
    s_writer.add_blank_page(width=595, height=842)
    s_writer.add_blank_page(width=595, height=842)
    with scanned_pdf.open("wb") as f:
        s_writer.write(f)

    return {"textual": textual_pdf, "scanned": scanned_pdf}


def test_mock_ocr_engine():
    """Valida o funcionamento determinístico do motor de OCR mock."""
    custom_texts = {
        1: "Página um escaneada com sucesso.",
        2: "Página dois com texto histórico.",
    }
    custom_conf = {1: 0.95, 2: 0.65}
    engine = MockOcrEngine(custom_page_texts=custom_texts, custom_confidences=custom_conf)

    assert engine.is_available() is True
    res1 = engine.process_page("dummy.pdf", 1)
    assert res1.page_number == 1
    assert res1.text == "Página um escaneada com sucesso."
    assert res1.confidence == 0.95
    assert res1.is_ocr is True
    assert res1.needs_review is False

    res2 = engine.process_page("dummy.pdf", 2)
    assert res2.confidence == 0.65
    assert res2.needs_review is True  # Confiança < 0.70 sinaliza necessidade de revisão


def test_ocr_cache_and_review(tmp_path: Path):
    """Testa armazenamento em cache, detecção de HIT e revisão de páginas."""
    cache = OcrCache(cache_dir=tmp_path / "ocr_cache")
    dummy_file = tmp_path / "file.pdf"
    dummy_file.write_bytes(b"PDF fake content 12345")
    file_hash = cache.calculate_file_hash(dummy_file)

    # Cache MISS
    miss = cache.get(file_hash, 1, "mock")
    assert miss is None

    # Gravação no cache
    initial_res = OcrPageResult(
        page_number=1,
        text="Text with typpo from OCR",
        confidence=0.80,
        engine_name="mock",
    )
    cache.put(file_hash, 1, "mock", initial_res)

    # Cache HIT
    hit = cache.get(file_hash, 1, "mock")
    assert hit is not None
    assert hit.text == "Text with typpo from OCR"
    assert hit.confidence == 0.80

    # Revisão Humana
    reviewed = cache.update_review(
        file_hash=file_hash,
        page_number=1,
        engine_name="mock",
        reviewed_text="Text with typo fixed manually",
        reviewer="revisor_editorial",
    )
    assert reviewed.text == "Text with typo fixed manually"
    assert reviewed.confidence == 1.0
    assert reviewed.metadata["reviewed_by"] == "revisor_editorial"
    assert reviewed.metadata["original_ocr_text"] == "Text with typpo from OCR"


def test_scanned_pdf_without_ocr_raises_error(sample_pdf_files: dict[str, Path]):
    """PDF escaneado sem motor de OCR configurado deve lançar NeedsOcrError."""
    parser = PdfParser(ocr_service=None)
    scanned_path = sample_pdf_files["scanned"]

    with pytest.raises(NeedsOcrError) as exc_info:
        parser.parse(scanned_path)

    assert "Requer OCR para processamento" in str(exc_info.value)


def test_scanned_pdf_with_ocr_produces_internal_representation(sample_pdf_files: dict[str, Path], tmp_path: Path):
    """PDF escaneado com OCR configurado gera Documento, preserva páginas e marca metadados."""
    ocr_texts = {
        1: "CAPÍTULO 1\nEste é o texto reconstruído da página 1 via OCR.",
        2: "Continuação da narrativa na página 2 com detalhes adicionais.",
    }
    engine = MockOcrEngine(custom_page_texts=ocr_texts, default_confidence=0.91)
    cache = OcrCache(cache_dir=tmp_path / "cache_test")
    ocr_service = OcrService(engine=engine, cache=cache)

    parser = PdfParser(ocr_service=ocr_service)
    scanned_path = sample_pdf_files["scanned"]

    doc = parser.parse(scanned_path, title="Livro Escaneado Reconstruído")

    assert isinstance(doc, Document)
    assert doc.metadata.extra.get("is_ocr") is True
    assert doc.metadata.extra.get("ocr_mean_confidence") == 0.91
    assert len(doc.chapters) >= 1

    # Verificar que os parágrafos carregam as referências à página original e flag is_ocr
    paras = [p for ch in doc.chapters for p in ch.paragraphs]
    assert len(paras) >= 2

    p1 = paras[0]
    assert p1.source_location is not None
    assert p1.source_location.page_number == 1
    assert p1.metadata.get("is_ocr") is True
    assert p1.metadata.get("ocr_confidence") == 0.91

    p2 = paras[1]
    assert p2.source_location.page_number == 2
    assert p2.metadata.get("is_ocr") is True


def test_segmenter_preserves_ocr_flags(tmp_path: Path):
    """Garante que a etapa de segmentação preserve as tags de cautela de OCR para o pipeline downstream."""
    ch = Chapter(id="chap_ocr", title="Capítulo OCR", order=1)
    ch.paragraphs = [
        Paragraph(
            id="p_ocr_1",
            chapter_id="chap_ocr",
            raw_text="Texto digitalizado por scanner óptico com possíveis ruídos.",
            reading_order=1,
            source_location=SourceLocation(file_path="scan.pdf", page_number=4),
            metadata={"is_ocr": True, "ocr_confidence": 0.72, "ocr_engine": "mock"},
        ),
        Paragraph(
            id="p_normal_2",
            chapter_id="chap_ocr",
            raw_text="Texto normal extraído de camada digital pura.",
            reading_order=2,
            source_location=SourceLocation(file_path="scan.pdf", page_number=5),
            metadata={"is_ocr": False},
        ),
    ]

    segmenter = InitialSegmenter()
    segments = segmenter.segment_chapter(ch)

    assert len(segments) == 2

    # Segmento 1 proveniente de OCR
    seg1 = segments[0]
    assert seg1.metadata.get("is_ocr") is True
    assert seg1.metadata.get("ocr_confidence") == 0.72
    assert seg1.metadata.get("ocr_engine") == "mock"
    assert seg1.metadata["source_locations"][0]["page_number"] == 4

    # Segmento 2 textual puro
    seg2 = segments[1]
    assert seg2.metadata.get("is_ocr") in (False, None)
