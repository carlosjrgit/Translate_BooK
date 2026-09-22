"""Testes unitários para o segmentador semântico inicial e garantia de zero perda de conteúdo."""

from __future__ import annotations

from book_translator.core.models import (
    Chapter,
    DialogueBlock,
    Footnote,
    Heading,
    Paragraph,
    SourceLocation,
)
from book_translator.preprocessing.config import PreprocessingConfig
from book_translator.preprocessing.segmenter import InitialSegmenter, SegmentType


def test_segmenter_semantic_types() -> None:
    segmenter = InitialSegmenter()

    ch = Chapter(id="ch_0001", title="Chapter 1", order=1)
    ch.headings.append(
        Heading(
            id="ch_0001_h_0001",
            chapter_id="ch_0001",
            level=1,
            raw_text="Chapter 1: The Gathering",
            reading_order=1,
        )
    )
    ch.paragraphs.append(
        Paragraph(
            id="ch_0001_p_00001",
            chapter_id="ch_0001",
            raw_text="This is an introductory narrative paragraph with sufficient detail.",
            reading_order=2,
            source_location=SourceLocation(file_path="book.txt", line_number=3),
        )
    )
    ch.dialogue_blocks.append(
        DialogueBlock(
            id="ch_0001_diag_0001",
            chapter_id="ch_0001",
            dialogue_marker="—",
            speaker_hint="Arthur",
            raw_text="— We must proceed immediately — Arthur warned.",
            reading_order=3,
            source_location=SourceLocation(file_path="book.txt", line_number=5),
        )
    )
    ch.footnotes.append(
        Footnote(
            id="ch_0001_fn_0001",
            chapter_id="ch_0001",
            marker="[1]",
            raw_text="[1] Note on historical gathering location.",
            referencing_unit_id="ch_0001_p_00001",
            reading_order=4,
        )
    )

    segments = segmenter.segment_chapter(ch)

    assert len(segments) == 4

    # 1. Heading
    assert segments[0].id == "ch_0001_seg_00001"
    assert segments[0].sequence_order == 1
    assert segments[0].segment_type == SegmentType.HEADING.value
    assert segments[0].original_text == "Chapter 1: The Gathering"

    # 2. Paragraph
    assert segments[1].id == "ch_0001_seg_00002"
    assert segments[1].sequence_order == 2
    assert segments[1].segment_type == SegmentType.PARAGRAPH.value
    assert segments[1].paragraph_id == "ch_0001_p_00001"

    # 3. Dialogue
    assert segments[2].id == "ch_0001_seg_00003"
    assert segments[2].sequence_order == 3
    assert segments[2].segment_type == SegmentType.DIALOGUE.value
    assert segments[2].metadata["dialogue_marker"] == "—"
    assert segments[2].metadata["speaker_hint"] == "Arthur"

    # 4. Footnote
    assert segments[3].id == "ch_0001_seg_00004"
    assert segments[3].sequence_order == 4
    assert segments[3].segment_type == SegmentType.FOOTNOTE.value
    assert segments[3].metadata["marker"] == "[1]"


def test_segmenter_short_paragraph_grouping() -> None:
    cfg = PreprocessingConfig(group_short_paragraphs=True, max_group_words=50)
    segmenter = InitialSegmenter(cfg)

    ch = Chapter(id="ch_0002", title="Chapter 2", order=2)
    # 3 parágrafos muito curtos (12 palavras no total)
    ch.paragraphs.append(
        Paragraph(id="p1", chapter_id="ch_0002", raw_text="Short sentence one.", reading_order=1)
    )
    ch.paragraphs.append(
        Paragraph(id="p2", chapter_id="ch_0002", raw_text="Short sentence two.", reading_order=2)
    )
    ch.paragraphs.append(
        Paragraph(id="p3", chapter_id="ch_0002", raw_text="Short sentence three.", reading_order=3)
    )

    segments = segmenter.segment_chapter(ch)

    # Devem ter sido agrupados em 1 único segmento do tipo PARAGRAPH_GROUP
    assert len(segments) == 1
    seg = segments[0]
    assert seg.segment_type == SegmentType.PARAGRAPH_GROUP.value
    assert seg.metadata["paragraph_count"] == 3
    expected_text = "Short sentence one.\n\nShort sentence two.\n\nShort sentence three."
    assert seg.original_text == expected_text


def test_segmenter_zero_content_loss_verification() -> None:
    segmenter = InitialSegmenter()

    ch = Chapter(id="ch_0003", title="Chapter 3", order=3)
    ch.headings.append(
        Heading(id="h1", chapter_id="ch_0003", level=1, raw_text="Title", reading_order=1)
    )
    ch.paragraphs.append(
        Paragraph(
            id="p1",
            chapter_id="ch_0003",
            raw_text="The quick brown fox jumps over the lazy dog.",
            reading_order=2,
        )
    )
    ch.dialogue_blocks.append(
        DialogueBlock(
            id="d1",
            chapter_id="ch_0003",
            dialogue_marker="—",
            raw_text="— Indeed it does.",
            reading_order=3,
        )
    )

    segments = segmenter.segment_chapter(ch)
    valid, msg = InitialSegmenter.verify_no_content_loss(ch, segments)

    assert valid is True
    assert "100%" in msg


def test_segmenter_idempotence_and_determinism() -> None:
    segmenter = InitialSegmenter()

    ch = Chapter(id="ch_0004", title="Chapter 4", order=4)
    ch.headings.append(
        Heading(id="h1", chapter_id="ch_0004", level=1, raw_text="Heading Test", reading_order=1)
    )
    ch.paragraphs.append(
        Paragraph(
            id="p1",
            chapter_id="ch_0004",
            raw_text="Determinism test paragraph one.",
            reading_order=2,
        )
    )
    ch.paragraphs.append(
        Paragraph(
            id="p2",
            chapter_id="ch_0004",
            raw_text="Determinism test paragraph two.",
            reading_order=3,
        )
    )

    segs1 = segmenter.segment_chapter(ch)
    segs2 = segmenter.segment_chapter(ch)

    assert len(segs1) == len(segs2)
    for s1, s2 in zip(segs1, segs2):
        assert s1.id == s2.id
        assert s1.original_text == s2.original_text
        assert s1.original_hash == s2.original_hash
        assert s1.sequence_order == s2.sequence_order
        assert s1.metadata == s2.metadata


def test_segmenter_long_paragraph_sentence_splitting() -> None:
    # Configura segmentador para dividir parágrafos com mais de 30 palavras
    cfg = PreprocessingConfig(split_long_paragraphs=True, max_segment_words=30)
    segmenter = InitialSegmenter(cfg)

    ch = Chapter(id="ch_0005", title="Chapter 5", order=5)
    long_text = (
        "Call me Ishmael. Some years ago, never mind how long precisely, having little or no money "
        "in my purse, and nothing particular to interest me on shore, I thought I would sail about "
        "a little and see the watery part of the world. It is a way I have of driving off the spleen "
        "and regulating the circulation. This is my substitute for pistol and ball."
    )
    ch.paragraphs.append(
        Paragraph(id="p_long", chapter_id="ch_0005", raw_text=long_text, reading_order=1)
    )

    segments = segmenter.segment_chapter(ch)
    # Deve ser subdividido em múltiplos segmentos
    assert len(segments) > 1

    # Valida integridade absoluta sem perda de nenhuma palavra
    valid, msg = InitialSegmenter.verify_no_content_loss(ch, segments)
    assert valid is True, msg

    # Todos os segmentos devem apontar para o parágrafo original
    for s in segments:
        assert s.paragraph_id == "p_long"
        assert s.metadata.get("paragraph_split") is True

