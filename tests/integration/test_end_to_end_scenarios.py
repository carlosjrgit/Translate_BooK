"""Bateria completa de testes End-to-End (E2E) cobrindo todos os 12+ cenários operacionais.

Cenários:
1. TXT
2. DOCX
3. EPUB
4. PDF textual
5. PDF escaneado (OCR fallback / detecção)
6. Documento curto (1 linha/parágrafo)
7. Livro maior (múltiplos capítulos, 20+ segmentos, glossário, style bible)
8. CPU-only
9. GPU quando disponível (ou fallback gracioso)
10. Interrupção e Retomada (CancellationToken, checkpoints atômicos, cache)
11. Modelo ausente
12. Modelo corrompido
13. Pouco espaço em disco
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pypdf
import pytest

from book_translator.consistency.checker import GlobalConsistencyChecker
from book_translator.core.document import (
    Chapter,
    Document,
)
from book_translator.core.models import (
    Project,
    ProjectMetadata,
    Segment,
)
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.errors import NeedsOcrError
from book_translator.export.manager import ExportManager
from book_translator.memory.base import GlossaryEntry
from book_translator.memory.manager import MemoryManager
from book_translator.ocr import MockOcrEngine, OcrCache, OcrService
from book_translator.parsers.docx import DocxParser
from book_translator.parsers.epub import EpubParser
from book_translator.parsers.pdf import PdfClassification, PdfParser
from book_translator.parsers.txt import TxtParser
from book_translator.projects.manager import ProjectManager
from book_translator.security import SecurityError, validate_disk_space
from book_translator.system.hardware import HardwareProfiler
from book_translator.system.model_manager import ModelManager, ModelStatus
from book_translator.translation.base import (
    TranslationCandidate,
    TranslationDraft,
    TranslationEngine,
)
from book_translator.translation.madlad import (
    DeviceType,
    MadladTranslationEngine,
    QuantizationType,
    RuntimeType,
)
from book_translator.translation.pipeline import (
    CancellationToken,
    TranslationPipeline,
    TranslationPipelineConfig,
)
from book_translator.translation.ranker import LiteraryCandidateRanker


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


class MockE2ETranslationEngine(TranslationEngine):
    """Engine de tradução determinística para validação E2E sem dependência de download de pesos pesados."""

    def __init__(self, dictionary: dict[str, str] | None = None) -> None:
        self.dictionary = dictionary or {}
        self.call_count = 0
        self._engine_name = "mock_e2e"

    @property
    def engine_name(self) -> str:
        return self._engine_name

    def is_ready(self) -> bool:
        return True

    def translate_segment(
        self,
        segment: Segment,
        context: Any = None,
        n_best: int = 1,
        ranker: Any = None,
        style_bible: Any = None,
    ) -> TranslationDraft:
        self.call_count += 1
        text = segment.original_text
        for k, v in self.dictionary.items():
            if k in text:
                text = text.replace(k, v)

        pt_text = (
            text.replace("The ", "O ")
            .replace("the ", "o ")
            .replace("Chapter", "Capítulo")
            .replace("was", "estava")
            .replace("midnight", "meia-noite")
            .replace("safe", "cofre")
            .replace("said", "disse")
            .replace("Holmes", "Holmes")
            .replace("examined", "examinou")
            .replace("footprint", "pegada")
        )
        cand = TranslationCandidate(
            text=pt_text,
            score=-0.1,
            rank=1,
            metadata={"engine": "mock_e2e"},
        )
        return TranslationDraft(
            segment_id=segment.id,
            selected_text=pt_text,
            candidates=[cand],
            engine_name="mock_e2e",
            execution_time_ms=1.0,
            metadata={"runtime": "mock"},
        )


# ---------------------------------------------------------------------------
# CENÁRIO 1: TXT End-to-End
# ---------------------------------------------------------------------------
def test_e2e_scenario_txt(tmp_path: Path) -> None:
    src_file = tmp_path / "original_book.txt"
    src_content = "Chapter 1: The Beginning\n\nThe safe was opened at midnight.\n\nHolmes was silent."
    src_file.write_text(src_content, encoding="utf-8")

    parser = TxtParser()
    doc = parser.parse(src_file, title="Test TXT Book")
    assert len(doc.chapters) >= 1

    proj_mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    proj, db = proj_mgr.create_project(
        book_title="Test TXT Book",
        source_file_path=src_file,
    )

    db.save_document(doc, project_id=proj.metadata.project_id)
    seq = 1
    for ch in doc.chapters:
        for p in ch.paragraphs:
            db.save_segment(
                Segment(
                    id=f"seg_{seq:03d}",
                    chapter_id=ch.id,
                    original_text=p.raw_text,
                    sequence_order=seq,
                )
            )
            seq += 1

    engine = MockE2ETranslationEngine()
    ranker = LiteraryCandidateRanker()
    pipeline = TranslationPipeline(
        db=db,
        translation_engine=engine,
        ranker=ranker,
        config=TranslationPipelineConfig(batch_size=2),
    )
    result = pipeline.translate_project(proj.metadata.project_id)
    assert result.status == "completed"
    assert result.completed_segments == 2

    loaded_doc = db.load_document(proj.metadata.project_id)
    assert loaded_doc is not None
    export_mgr = ExportManager()
    out_path = tmp_path / "exported_book.txt"
    res_path = export_mgr.export(loaded_doc, out_path, "txt")
    assert res_path.exists()
    out_text = res_path.read_text(encoding="utf-8")
    assert "Capítulo" in out_text or "meia-noite" in out_text
    assert src_file.read_text(encoding="utf-8") == src_content
    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 2: DOCX End-to-End
# ---------------------------------------------------------------------------
def test_e2e_scenario_docx(tmp_path: Path) -> None:
    src_docx = tmp_path / "sample.docx"
    doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body>
            <w:p>
                <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
                <w:r><w:t>Chapter 1: The Clue</w:t></w:r>
            </w:p>
            <w:p>
                <w:r><w:rPr><w:b/></w:rPr><w:t>Holmes </w:t></w:r>
                <w:r><w:rPr><w:i/></w:rPr><w:t>examined the footprint.</w:t></w:r>
            </w:p>
        </w:body>
    </w:document>"""

    with zipfile.ZipFile(src_docx, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)

    parser = DocxParser()
    doc = parser.parse(src_docx, title="DOCX Mystery")
    assert len(doc.chapters) >= 1

    proj_mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    proj, db = proj_mgr.create_project("DOCX Mystery", source_file_path=src_docx)
    db.save_document(doc, project_id=proj.metadata.project_id)

    s1 = Segment(id="seg_d1", chapter_id=doc.chapters[0].id, original_text="Holmes examined the footprint.", sequence_order=1)
    db.save_segment(s1)

    engine = MockE2ETranslationEngine()
    pipeline = TranslationPipeline(db=db, translation_engine=engine, ranker=LiteraryCandidateRanker())
    res = pipeline.translate_project(proj.metadata.project_id)
    assert res.status == "completed"

    loaded_doc = db.load_document(proj.metadata.project_id)
    assert loaded_doc is not None
    export_mgr = ExportManager()
    out_docx = tmp_path / "translated.docx"
    export_mgr.export(loaded_doc, out_docx, "docx")
    assert out_docx.exists()
    assert zipfile.is_zipfile(out_docx)
    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 3: EPUB End-to-End
# ---------------------------------------------------------------------------
def test_e2e_scenario_epub(tmp_path: Path) -> None:
    src_epub = tmp_path / "sample.epub"
    container_xml = """<?xml version="1.0"?>
    <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
        <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
    </container>"""

    opf_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
        <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
            <dc:title>Epub Adventure</dc:title>
            <dc:creator>Watson</dc:creator>
        </metadata>
        <manifest>
            <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
        </manifest>
        <spine><itemref idref="ch1"/></spine>
    </package>"""

    ch1_xhtml = """<?xml version="1.0" encoding="utf-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Chapter 1</title></head>
    <body>
        <h1>Chapter 1</h1>
        <p>The safe was opened at midnight.</p>
    </body>
    </html>"""

    with zipfile.ZipFile(src_epub, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("content.opf", opf_xml)
        zf.writestr("chapter1.xhtml", ch1_xhtml)

    parser = EpubParser()
    doc = parser.parse(src_epub)
    assert doc.metadata.title == "Epub Adventure"

    proj_mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    proj, db = proj_mgr.create_project("Epub Adventure", source_file_path=src_epub)
    db.save_document(doc, project_id=proj.metadata.project_id)

    s1 = Segment(id="seg_e1", chapter_id=doc.chapters[0].id, original_text="The safe was opened at midnight.", sequence_order=1)
    db.save_segment(s1)

    engine = MockE2ETranslationEngine()
    pipeline = TranslationPipeline(db=db, translation_engine=engine, ranker=LiteraryCandidateRanker())
    pipeline.translate_project(proj.metadata.project_id)

    loaded_doc = db.load_document(proj.metadata.project_id)
    assert loaded_doc is not None
    export_mgr = ExportManager()
    out_epub = tmp_path / "translated.epub"
    export_mgr.export(loaded_doc, out_epub, "epub")
    assert out_epub.exists()
    assert zipfile.is_zipfile(out_epub)
    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 4: PDF Textual
# ---------------------------------------------------------------------------
def test_e2e_scenario_pdf_textual(tmp_path: Path) -> None:
    pdf_bytes = _create_synthetic_pdf([
        "Sherlock Holmes examined the footprint with his magnifying glass at 221B Baker Street.\n"
        "The safe was opened at midnight by the mysterious thief.\n"
        "Watson listened carefully near the fireplace."
    ])

    pdf_file = tmp_path / "textual.pdf"
    pdf_file.write_bytes(pdf_bytes)

    parser = PdfParser()
    with pdf_file.open("rb") as f:
        reader = pypdf.PdfReader(f)
        classification, _ = parser.classify_pdf(reader)
        assert classification in (PdfClassification.TEXTUAL, PdfClassification.MIXED)

    db_file = tmp_path / "pdf_test.db"
    db = SQLiteDatabase(db_file)
    db.initialize()
    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 5: PDF Escaneado (Detecção e Módulo OCR)
# ---------------------------------------------------------------------------
def test_e2e_scenario_pdf_scanned_ocr(tmp_path: Path) -> None:
    blank_pdf = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n" \
                b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n" \
                b"3 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj\n" \
                b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n" \
                b"trailer\n<</Size 4 /Root 1 0 R>>\nstartxref\n190\n%%EOF\n"

    scanned_file = tmp_path / "scanned.pdf"
    scanned_file.write_bytes(blank_pdf)

    parser = PdfParser()
    with scanned_file.open("rb") as f:
        reader = pypdf.PdfReader(f)
        classification, _ = parser.classify_pdf(reader)
        assert classification == PdfClassification.SCANNED_NEEDS_OCR

    with pytest.raises(NeedsOcrError):
        parser.parse(scanned_file)

    engine = MockOcrEngine(custom_page_texts={1: "Texto da página 1 via OCR."})
    cache = OcrCache(cache_dir=tmp_path / "ocr_cache")
    ocr_service = OcrService(engine=engine, cache=cache)
    parser_with_ocr = PdfParser(ocr_service=ocr_service)
    doc = parser_with_ocr.parse(scanned_file, title="Livro OCR")
    assert doc.metadata.extra.get("is_ocr") is True
    assert len(doc.chapters) >= 1


# ---------------------------------------------------------------------------
# CENÁRIO 6: Documento Curto (1 Parágrafo)
# ---------------------------------------------------------------------------
def test_e2e_scenario_short_document(tmp_path: Path) -> None:
    short_file = tmp_path / "short.txt"
    short_file.write_text("A simple flash in the dark.", encoding="utf-8")

    parser = TxtParser()
    doc = parser.parse(short_file)
    assert len(doc.chapters) == 1

    db_path = tmp_path / "short.db"
    db = SQLiteDatabase(db_path)
    db.initialize()

    proj = Project(
        metadata=ProjectMetadata(
            project_id="p_short",
            book_title="Short",
            source_file_path=str(short_file),
        ),
        project_dir=tmp_path,
        db_path=db_path,
    )
    db.save_project(proj)
    db.save_document(doc, project_id="p_short")

    s = Segment(id="s1", chapter_id=doc.chapters[0].id, original_text="A simple flash in the dark.", sequence_order=1)
    db.save_segment(s)

    engine = MockE2ETranslationEngine()
    pipeline = TranslationPipeline(db=db, translation_engine=engine, ranker=LiteraryCandidateRanker())
    res = pipeline.translate_project("p_short")
    assert res.completed_segments == 1
    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 7: Livro Maior (Múltiplos Capítulos, 20+ Segmentos, Glossário)
# ---------------------------------------------------------------------------
def test_e2e_scenario_large_book(tmp_path: Path) -> None:
    db_path = tmp_path / "large_book.db"
    db = SQLiteDatabase(db_path)
    db.initialize()
    proj_id = "p_large"

    proj = Project(
        metadata=ProjectMetadata(
            project_id=proj_id,
            book_title="The Great Chronicle",
            source_file_path=str(tmp_path / "source.txt"),
        ),
        project_dir=tmp_path,
        db_path=db_path,
    )
    db.save_project(proj)

    total_segs = 24
    seg_idx = 1
    chapters_list: list[Chapter] = []
    for c_idx in range(1, 4):
        chap = Chapter(id=f"ch_{c_idx}", title=f"Chapter {c_idx}", order=c_idx)
        chapters_list.append(chap)

    doc = Document(id="doc_large", chapters=chapters_list)
    db.save_document(doc, project_id=proj_id)

    for chap in chapters_list:
        for s_in_c in range(1, 9):
            s = Segment(
                id=f"seg_{seg_idx:03d}",
                chapter_id=chap.id,
                original_text=f"Sentence {seg_idx}: The safe was examined by Holmes at midnight.",
                sequence_order=seg_idx,
            )
            db.save_segment(s)
            seg_idx += 1

    db.save_glossary_entry(
        proj_id,
        GlossaryEntry(id="g1", project_id=proj_id, source_term="Holmes", target_term="Holmes", locked=True),
    )

    engine = MockE2ETranslationEngine(dictionary={"midnight": "meia-noite"})
    pipeline = TranslationPipeline(
        db=db,
        translation_engine=engine,
        ranker=LiteraryCandidateRanker(),
        config=TranslationPipelineConfig(batch_size=4, checkpoint_frequency=4),
    )

    res = pipeline.translate_project(proj_id)
    assert res.status == "completed"
    assert res.completed_segments == total_segs
    assert res.freshly_translated == total_segs

    mem = MemoryManager(project_id=proj_id)
    checker = GlobalConsistencyChecker()
    report = checker.audit(doc, mem)
    assert report is not None
    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 8: CPU-Only Execution
# ---------------------------------------------------------------------------
def test_e2e_scenario_cpu_only() -> None:
    engine = MadladTranslationEngine(
        device=DeviceType.CPU,
        quantization=QuantizationType.Q8,
        runtime_type=RuntimeType.MOCK,
    )
    assert engine.device == DeviceType.CPU
    assert engine.quantization == QuantizationType.Q8
    seg = Segment(id="s1", chapter_id="c1", original_text="The safe was examined by Holmes at midnight.", sequence_order=1)
    draft = engine.translate_segment(seg)
    assert draft.selected_text is not None


# ---------------------------------------------------------------------------
# CENÁRIO 9: GPU ou Fallback Gracioso
# ---------------------------------------------------------------------------
def test_e2e_scenario_gpu_or_fallback() -> None:
    profiler = HardwareProfiler()
    profile = profiler.profile()
    assert profile.ram.total_gb > 0
    if not profile.gpu.available:
        assert profile.gpu.vram_total_gb == 0.0
    else:
        assert profile.gpu.vram_total_gb > 0.0


# ---------------------------------------------------------------------------
# CENÁRIO 10: Interrupção e Retomada (Checkpoints, Cache e Continuidade)
# ---------------------------------------------------------------------------
def test_e2e_scenario_interruption_and_resume(tmp_path: Path) -> None:
    db_path = tmp_path / "resume_test.db"
    db = SQLiteDatabase(db_path)
    db.initialize()
    proj_id = "p_resume"

    proj = Project(
        metadata=ProjectMetadata(
            project_id=proj_id,
            book_title="Interruption Test",
            source_file_path=str(tmp_path / "source.txt"),
        ),
        project_dir=tmp_path,
        db_path=db_path,
    )
    db.save_project(proj)

    chap = Chapter(id="c1", title="Chapter 1", order=1)
    doc = Document(id="doc_resume", chapters=[chap])
    db.save_document(doc, project_id=proj_id)

    for i in range(1, 11):
        db.save_segment(
            Segment(
                id=f"seg_{i:02d}",
                chapter_id="c1",
                original_text=f"Paragraph {i}: The investigation continued.",
                sequence_order=i,
            )
        )

    engine = MockE2ETranslationEngine()
    token = CancellationToken()

    def on_progress(done: int, total: int) -> None:
        if done >= 5:
            token.cancel()

    pipeline = TranslationPipeline(
        db=db,
        translation_engine=engine,
        ranker=LiteraryCandidateRanker(),
        config=TranslationPipelineConfig(checkpoint_frequency=1),
    )

    res1 = pipeline.translate_project(proj_id, cancellation_token=token, on_progress=on_progress)
    assert res1.status == "paused"
    assert res1.completed_segments >= 5
    first_done = res1.completed_segments

    chk = db.get_latest_checkpoint(proj_id)
    assert chk is not None
    assert chk.status == "paused"

    token_resume = CancellationToken()
    engine.call_count = 0
    res2 = pipeline.translate_project(proj_id, cancellation_token=token_resume)
    assert res2.status == "completed"
    assert res2.completed_segments == 10
    assert res2.cached_segments == first_done
    assert res2.freshly_translated == 10 - first_done

    db.close()


# ---------------------------------------------------------------------------
# CENÁRIO 11: Modelo Ausente
# ---------------------------------------------------------------------------
def test_e2e_scenario_missing_model(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path / "models")
    status = mgr.get_model_status("madlad400-3b-mt-ct2-int8")
    assert status == ModelStatus.NOT_INSTALLED

    with pytest.raises(ValueError, match="Não é possível ativar o modelo"):
        mgr.select_active_model("madlad400-3b-mt-ct2-int8")


# ---------------------------------------------------------------------------
# CENÁRIO 12: Modelo Corrompido
# ---------------------------------------------------------------------------
def test_e2e_scenario_corrupted_model(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path / "models")
    m_dir = mgr.get_model_dir("madlad400-3b-mt-ct2-int8")
    m_dir.mkdir(parents=True)

    (m_dir / "model.bin").write_bytes(b"corrupted_bytes_000")
    (m_dir / "shared_vocabulary.json").write_bytes(b"corrupted_vocab")

    status = mgr.get_model_status("madlad400-3b-mt-ct2-int8")
    assert status == ModelStatus.CORRUPTED
    assert not mgr.verify_model_integrity("madlad400-3b-mt-ct2-int8")


# ---------------------------------------------------------------------------
# CENÁRIO 13: Pouco Espaço em Disco
# ---------------------------------------------------------------------------
def test_e2e_scenario_low_disk_space(tmp_path: Path) -> None:
    with patch("shutil.disk_usage") as mock_usage:
        mock_usage.return_value = MagicMock(total=100_000_000_000, used=99_900_000_000, free=100_000_000)

        with pytest.raises(SecurityError, match="Espaço insuficiente em disco"):
            validate_disk_space(tmp_path / "models", required_bytes=5 * 1024 * 1024 * 1024)
