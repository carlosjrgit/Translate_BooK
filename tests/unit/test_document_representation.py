"""Testes da representação intermediária canônica do documento e sua persistência."""

from __future__ import annotations

from pathlib import Path

from book_translator.core.document import (
    Chapter,
    DialogueBlock,
    Document,
    DocumentMetadata,
    Footnote,
    FormattingSpan,
    Heading,
    ImagePlaceholder,
    Paragraph,
    Reference,
    Section,
    SourceLocation,
)
from book_translator.core.models import Project, ProjectMetadata, Segment, SegmentStatus
from book_translator.database.sqlite import SQLiteDatabase


def build_sample_document() -> Document:
    """Cria um documento sintético completo com todos os elementos estruturais."""
    loc_h1 = SourceLocation(file_path="sample.epub", page_number=1, line_number=5)
    h1 = Heading(
        id="ch_0001_h_0001",
        chapter_id="ch_0001",
        level=1,
        raw_text="Chapter 1: The Dark Forest",
        normalized_text="Chapter 1: The Dark Forest",
        reading_order=1,
        spans=[FormattingSpan(start=11, end=26, style="bold")],
        source_location=loc_h1,
    )

    loc_p1 = SourceLocation(file_path="sample.epub", page_number=1, line_number=10)
    p1 = Paragraph(
        id="ch_0001_p_00001",
        chapter_id="ch_0001",
        reading_order=2,
        raw_text="The trees stood tall and *ominous* in the night.",
        normalized_text="The trees stood tall and ominous in the night.",
        spans=[FormattingSpan(start=25, end=32, style="italic")],
        source_location=loc_p1,
    )

    loc_diag = SourceLocation(file_path="sample.epub", page_number=1, line_number=15)
    diag = DialogueBlock(
        id="ch_0001_diag_0001",
        chapter_id="ch_0001",
        reading_order=3,
        raw_text="— We cannot stop here, said Jack.",
        normalized_text="We cannot stop here, said Jack.",
        dialogue_marker="—",
        speaker_hint="Jack Henderson",
        source_location=loc_diag,
    )

    fn = Footnote(
        id="ch_0001_fn_0001",
        chapter_id="ch_0001",
        marker="1",
        raw_text="1. An ancient forest in the north.",
        normalized_text="An ancient forest in the north.",
        reading_order=4,
        referencing_unit_id="ch_0001_p_00001",
    )

    img = ImagePlaceholder(
        id="ch_0001_img_0001",
        chapter_id="ch_0001",
        reading_order=5,
        caption_raw="Figure 1.1: The northern border.",
        caption_normalized="Figure 1.1: The northern border.",
        alt_text="A dark dense forest under a full moon",
        relative_path="images/forest.png",
    )

    sec = Section(
        id="ch_0001_sec_0001",
        chapter_id="ch_0001",
        title="Part A: The Crossing",
        reading_order=1,
        order_index=1,
    )

    seg = Segment(
        id="ch_0001_seg_00001",
        chapter_id="ch_0001",
        paragraph_id="ch_0001_p_00001",
        sequence_order=1,
        original_text="The trees stood tall and ominous in the night.",
        status=SegmentStatus.PENDING,
    )

    chapter = Chapter(
        id="ch_0001",
        title="Chapter 1: The Dark Forest",
        order=1,
        reading_order=1,
        headings=[h1],
        paragraphs=[p1],
        dialogue_blocks=[diag],
        footnotes=[fn],
        image_placeholders=[img],
        sections=[sec],
        segments=[seg],
    )

    ref = Reference(
        id="ref_0001",
        citation_key="Henderson1984",
        raw_text="Henderson, J. (1984). Northern Geography.",
        normalized_text="Henderson, J. (1984). Northern Geography.",
        url="https://example.org/geography",
        reading_order=100,
    )

    meta = DocumentMetadata(
        title="The Northern Chronicles",
        author="Evelyn Vance",
        language="en",
        publisher="Editorial House",
        publication_date="2023",
        isbn="978-0-123456-47-2",
        source_format="epub",
    )

    return Document(
        id="doc_northern_chronicles",
        metadata=meta,
        chapters=[chapter],
        references=[ref],
    )


def test_synthetic_document_representation() -> None:
    """Verifica se todas as unidades estruturais são mantidas no modelo."""
    doc = build_sample_document()
    assert doc.id == "doc_northern_chronicles"
    assert doc.title == "The Northern Chronicles"
    assert doc.author == "Evelyn Vance"
    assert doc.total_chapters == 1

    ch = doc.chapters[0]
    assert len(ch.headings) == 1
    assert len(ch.paragraphs) == 1
    assert len(ch.dialogue_blocks) == 1
    assert len(ch.footnotes) == 1
    assert len(ch.image_placeholders) == 1
    assert len(ch.sections) == 1
    assert len(doc.references) == 1


def test_reading_order_determinism() -> None:
    """Garante que a ordem de leitura das unidades de conteúdo seja estritamente determinística."""
    doc = build_sample_document()
    ch = doc.chapters[0]
    ordered_units = ch.get_reading_sequence()

    # Esperado: Heading (1) -> Paragraph (2) -> Dialogue (3) -> Footnote (4) -> Image (5)
    assert len(ordered_units) == 5
    assert isinstance(ordered_units[0], Heading)
    assert isinstance(ordered_units[1], Paragraph)
    assert isinstance(ordered_units[2], DialogueBlock)
    assert isinstance(ordered_units[3], Footnote)
    assert isinstance(ordered_units[4], ImagePlaceholder)

    linear_doc = doc.get_linear_reading_order()
    assert len(linear_doc) == 6  # 5 unidades do capítulo + 1 referência bibliográfica
    assert isinstance(linear_doc[-1], Reference)


def test_json_serialization_roundtrip() -> None:
    """Garante que a serialização e desserialização JSON sejam simétricas e sem perdas."""
    doc = build_sample_document()
    json_str = doc.to_json()
    reconstructed = Document.from_json(json_str)

    assert reconstructed.id == doc.id
    assert reconstructed.title == doc.title
    assert reconstructed.metadata.isbn == "978-0-123456-47-2"

    ch = reconstructed.chapters[0]
    orig_ch = doc.chapters[0]
    assert ch.headings[0].spans[0].style == orig_ch.headings[0].spans[0].style
    assert ch.dialogue_blocks[0].speaker_hint == "Jack Henderson"
    assert ch.dialogue_blocks[0].dialogue_marker == "—"
    assert ch.footnotes[0].marker == "1"
    assert ch.image_placeholders[0].caption_raw == "Figure 1.1: The northern border."
    assert reconstructed.references[0].citation_key == "Henderson1984"


def test_database_persistence_roundtrip(tmp_path: Path) -> None:
    """Valida se a estrutura completa pode ser gravada e reconstruída via SQLiteDatabase."""
    db = SQLiteDatabase(tmp_path / "doc_test.db")
    db.initialize()

    # 1. Cria projeto
    meta = ProjectMetadata(
        project_id="proj_northern",
        book_title="The Northern Chronicles",
        source_file_path=str(tmp_path / "book.epub"),
    )
    db.save_project(Project(metadata=meta, project_dir=tmp_path, db_path=db.db_path))

    # 2. Salva documento com árvore completa
    doc = build_sample_document()
    db.save_document(doc, project_id="proj_northern")

    # 3. Carrega documento do banco
    loaded_doc = db.load_document("proj_northern")
    assert loaded_doc is not None
    assert loaded_doc.id == doc.id
    assert loaded_doc.title == "The Northern Chronicles"
    assert loaded_doc.author == "Evelyn Vance"

    ch = loaded_doc.chapters[0]
    assert len(ch.headings) == 1
    assert ch.headings[0].normalized_text == "Chapter 1: The Dark Forest"
    assert ch.headings[0].spans[0].style == "bold"

    assert len(ch.paragraphs) == 1
    assert ch.paragraphs[0].spans[0].style == "italic"

    assert len(ch.dialogue_blocks) == 1
    assert ch.dialogue_blocks[0].speaker_hint == "Jack Henderson"

    assert len(ch.footnotes) == 1
    assert ch.footnotes[0].marker == "1"

    assert len(ch.image_placeholders) == 1
    assert ch.image_placeholders[0].relative_path == "images/forest.png"

    assert len(loaded_doc.references) == 1
    assert loaded_doc.references[0].citation_key == "Henderson1984"

    db.close()
