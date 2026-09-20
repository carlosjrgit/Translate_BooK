"""Testes unitários para exportação TXT, DOCX e EPUB (Prompt 22)."""

import zipfile
from pathlib import Path

import pytest

from book_translator.core.models import (
    Chapter,
    Document,
    DocumentMetadata,
    Footnote,
    Segment,
    SegmentStatus,
)
from book_translator.export import (
    DocxExporter,
    EpubExporter,
    ExportManager,
    OutputOverwriteError,
    TxtExporter,
    generate_safe_output_path,
    validate_safe_output_path,
)


@pytest.fixture
def sample_document(tmp_path: Path) -> Document:
    original_file = tmp_path / "original_book.epub"
    original_file.write_text("dummy original content", encoding="utf-8")

    meta = DocumentMetadata(
        title="Dom Casmurro",
        author="Machado de Assis",
        language="en",
        source_file_path=str(original_file),
        extra={"publisher": "Editora Antigravity"},
    )

    ch1 = Chapter(id="chap_01", title="Capítulo 1: Do Título", order=1)
    ch1.segments = [
        Segment(
            id="seg_01_01",
            chapter_id="chap_01",
            original_text="One evening, in the suburban train, I met an acquaintance.",
            translated_text="Uma noite destas, vindo da cidade para o Engenho Novo, encontrei num trem da Central um rapaz aqui do bairro.",
            sequence_order=1,
            status=SegmentStatus.TRANSLATED,
        ),
        Segment(
            id="seg_01_02",
            chapter_id="chap_01",
            original_text='— "Did you read the **important** news?" he asked with *emphasis*.',
            translated_text='— "Você leu a notícia **importante**?" perguntou ele com *ênfase*.',
            sequence_order=2,
            status=SegmentStatus.TRANSLATED,
        ),
        Segment(
            id="seg_01_03",
            chapter_id="chap_01",
            original_text="See full documentation at [Antigravity](https://example.com/info).",
            translated_text="Veja a documentação completa em [Antigravity](https://example.com/info).",
            sequence_order=3,
            status=SegmentStatus.TRANSLATED,
        ),
    ]
    ch1.footnotes = [
        Footnote(
            id="fn_01",
            chapter_id="chap_01",
            marker="1",
            raw_text="Nota histórica sobre a Estrada de Ferro Central do Brasil.",
            normalized_text="Nota histórica sobre a Estrada de Ferro Central do Brasil.",
        )
    ]

    ch2 = Chapter(id="chap_02", title="Capítulo 2: Do Livro", order=2)
    ch2.segments = [
        Segment(
            id="seg_02_01",
            chapter_id="chap_02",
            original_text="Life is an opera, and a grand opera.",
            translated_text="A vida é uma ópera e uma grande ópera.",
            sequence_order=1,
            status=SegmentStatus.TRANSLATED,
        )
    ]

    doc = Document(
        id="doc_test_01",
        metadata=meta,
        chapters=[ch1, ch2],
    )
    return doc


def test_naming_and_overwrite_protection(sample_document: Document, tmp_path: Path):
    """Garante que nunca sobrescreva o arquivo original e previna colisões."""
    original_path = Path(sample_document.metadata.source_file_path)

    with pytest.raises(OutputOverwriteError):
        validate_safe_output_path(original_path, original_path)

    # Gera caminho seguro a partir do documento
    safe_path = generate_safe_output_path(sample_document, tmp_path, "txt")
    assert safe_path != original_path
    assert "Dom_Casmurro" in safe_path.name
    assert "PT-BR" in safe_path.name
    assert safe_path.suffix == ".txt"

    # Simular colisão criando o arquivo prévio
    safe_path.write_text("existing", encoding="utf-8")
    safe_path_2 = generate_safe_output_path(sample_document, tmp_path, "txt")
    assert safe_path_2 != safe_path
    assert "_PT-BR_" in safe_path_2.name


def test_txt_export(sample_document: Document, tmp_path: Path):
    """Testa exportação em TXT com preservação de estrutura e notas."""
    exporter = TxtExporter()
    out_file = tmp_path / "output.txt"
    res = exporter.export(sample_document, out_file)

    assert res.exists()
    content = res.read_text(encoding="utf-8")

    assert "DOM CASMURRO" in content
    assert "Machado de Assis" in content
    assert "Capítulo 1: Do Título" in content
    assert "Uma noite destas, vindo da cidade" in content
    assert "[Notas do Capítulo]" in content
    assert "Nota histórica sobre a Estrada de Ferro" in content
    assert "Capítulo 2: Do Livro" in content


def test_docx_export(sample_document: Document, tmp_path: Path):
    """Testa exportação nativa em DOCX (OpenXML)."""
    exporter = DocxExporter()
    out_file = tmp_path / "output.docx"
    res = exporter.export(sample_document, out_file)

    assert res.exists()
    assert zipfile.is_zipfile(res)

    with zipfile.ZipFile(res, "r") as zf:
        file_list = zf.namelist()
        assert "[Content_Types].xml" in file_list
        assert "word/document.xml" in file_list
        assert "word/footnotes.xml" in file_list
        assert "word/_rels/document.xml.rels" in file_list

        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "Capítulo 1: Do Título" in doc_xml
        assert "Capítulo 2: Do Livro" in doc_xml
        assert "notícia " in doc_xml
        # Negrito ou itálico inserido
        assert "<w:b/>" in doc_xml or "<w:b " in doc_xml
        assert "<w:i/>" in doc_xml or "<w:i " in doc_xml

        fn_xml = zf.read("word/footnotes.xml").decode("utf-8")
        assert "Nota histórica sobre a Estrada de Ferro" in fn_xml


def test_epub_export(sample_document: Document, tmp_path: Path):
    """Testa exportação em EPUB 3 com ordem de capítulos e padrão do pacote."""
    exporter = EpubExporter()
    out_file = tmp_path / "output.epub"
    res = exporter.export(sample_document, out_file)

    assert res.exists()
    assert zipfile.is_zipfile(res)

    with zipfile.ZipFile(res, "r") as zf:
        namelist = zf.namelist()
        # O primeiro arquivo deve ser mimetype
        assert namelist[0] == "mimetype"
        assert zf.read("mimetype").decode("utf-8").strip() == "application/epub+zip"

        # Verificar estrutura padrão do EPUB 3
        assert "META-INF/container.xml" in namelist
        assert "OEBPS/content.opf" in namelist
        assert "OEBPS/nav.xhtml" in namelist
        assert "OEBPS/toc.ncx" in namelist
        assert "OEBPS/styles.css" in namelist

        # Capítulos e notas
        assert "OEBPS/chapter_001.xhtml" in namelist
        assert "OEBPS/chapter_002.xhtml" in namelist

        chap1_content = zf.read("OEBPS/chapter_001.xhtml").decode("utf-8")
        assert "Capítulo 1: Do Título" in chap1_content
        assert "<strong>importante</strong>" in chap1_content
        assert "<em>ênfase</em>" in chap1_content
        assert '<a href="https://example.com/info">Antigravity</a>' in chap1_content
        assert 'epub:type="footnote"' in chap1_content

        chap2_content = zf.read("OEBPS/chapter_002.xhtml").decode("utf-8")
        assert "Capítulo 2: Do Livro" in chap2_content


def test_export_manager_all_formats(sample_document: Document, tmp_path: Path):
    """Testa o ExportManager exportando todos os formatos com nomes seguros."""
    manager = ExportManager()
    assert set(manager.supported_formats) == {"txt", "docx", "epub"}

    export_dir = tmp_path / "exports"
    results = manager.export_all(sample_document, export_dir, formats=["txt", "docx", "epub"])

    assert "txt" in results and results["txt"].exists()
    assert "docx" in results and results["docx"].exists()
    assert "epub" in results and results["epub"].exists()

    # Original nunca é sobrescrito
    original_path = Path(sample_document.metadata.source_file_path)
    assert original_path.exists()
    assert original_path.read_text(encoding="utf-8") == "dummy original content"
