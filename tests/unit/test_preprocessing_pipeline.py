"""Testes de integração ponta-a-ponta do pipeline de pré-processamento e segmentação."""

from __future__ import annotations

from book_translator.core.document import Document, DocumentMetadata
from book_translator.core.models import Chapter, Heading, Paragraph
from book_translator.preprocessing.pipeline import PreprocessingPipeline
from book_translator.preprocessing.segmenter import SegmentType


def test_process_document_enriches_existing_document() -> None:
    pipeline = PreprocessingPipeline()

    doc = Document(id="doc_pipe_1", metadata=DocumentMetadata(title="Pipeline Test"))
    ch = Chapter(id="ch_0001", title="Chapter 1", order=1)
    ch.headings.append(
        Heading(
            id="h1",
            chapter_id="ch_0001",
            level=1,
            raw_text="Chapter 1",
            reading_order=1,
        )
    )
    # Parágrafo contendo travessão que deve ser promovido a diálogo
    ch.paragraphs.append(
        Paragraph(
            id="p1",
            chapter_id="ch_0001",
            raw_text="— Welcome to London — said Watson warmly.",
            reading_order=2,
        )
    )
    # Parágrafo de narrativa normal
    ch.paragraphs.append(
        Paragraph(
            id="p2",
            chapter_id="ch_0001",
            raw_text="The fog was thick and dense upon the Thames.",
            reading_order=3,
        )
    )
    doc.chapters.append(ch)

    processed = pipeline.process_document(doc)

    assert processed.metadata.extra.get("preprocessed") is True
    assert len(processed.chapters) == 1

    proc_ch = processed.chapters[0]
    # O parágrafo de fala deve ter sido identificado como DialogueBlock
    assert len(proc_ch.dialogue_blocks) == 1
    assert proc_ch.dialogue_blocks[0].speaker_hint == "Watson"
    assert len(proc_ch.paragraphs) == 1
    assert "fog was thick" in proc_ch.paragraphs[0].normalized_text

    # Verifica os segmentos gerados
    assert len(proc_ch.segments) >= 3
    seg_types = [s.segment_type for s in proc_ch.segments]
    assert SegmentType.HEADING.value in seg_types
    assert SegmentType.DIALOGUE.value in seg_types
    assert (
        SegmentType.PARAGRAPH.value in seg_types or SegmentType.PARAGRAPH_GROUP.value in seg_types
    )


def test_process_text_creates_complete_document() -> None:
    pipeline = PreprocessingPipeline()

    sample_text = (
        "CHAPTER 1: THE ARRIVAL\n\n"
        "The carriage rattled along the stony road, moving slowly\n"
        "under the grey November sky.\n\n"
        "* * *\n\n"
        "— Are we almost there? — asked Lucy.\n\n"
        "— Very soon, my dear — replied Thomas gently."
    )

    doc = pipeline.process_text(sample_text, title="The Arrival Book")

    assert doc.id.startswith("doc_")
    assert doc.title == "The Arrival Book"
    assert len(doc.chapters) == 1

    ch = doc.chapters[0]
    assert "CHAPTER 1" in ch.title
    assert len(ch.headings) == 1
    assert len(ch.sections) >= 1  # Scene break '* * *' gera seção
    assert len(ch.paragraphs) >= 1
    assert len(ch.dialogue_blocks) == 2

    # Verifica speaker hints
    hints = {d.speaker_hint for d in ch.dialogue_blocks}
    assert "Lucy" in hints
    assert "Thomas" in hints

    # Verifica segmentos
    assert len(ch.segments) >= 4
    for seg in ch.segments:
        assert seg.id.startswith("ch_0001_seg_")
        assert seg.original_text.strip() != ""
        assert seg.original_hash != ""


def test_pipeline_idempotence_and_determinism() -> None:
    pipeline = PreprocessingPipeline()

    raw_text = (
        "CHAPTER I\n\n"
        "This is paragraph one of the test book.\n\n"
        "This is paragraph two.\n\n"
        "— What do you mean? — asked Helen."
    )

    doc1 = pipeline.process_text(raw_text, title="Determinism Test")
    doc2 = pipeline.process_text(raw_text, title="Determinism Test")

    assert len(doc1.chapters) == len(doc2.chapters)
    ch1 = doc1.chapters[0]
    ch2 = doc2.chapters[0]

    assert len(ch1.segments) == len(ch2.segments)
    for s1, s2 in zip(ch1.segments, ch2.segments):
        assert s1.id == s2.id
        assert s1.original_text == s2.original_text
        assert s1.original_hash == s2.original_hash
        assert s1.sequence_order == s2.sequence_order
        assert s1.segment_type == s2.segment_type
