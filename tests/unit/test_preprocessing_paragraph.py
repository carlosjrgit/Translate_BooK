"""Testes para reconstrução de parágrafos e detecção de quebras de cena."""

from __future__ import annotations

from book_translator.preprocessing.paragraph_reconstructor import ParagraphReconstructor


def test_soft_wrap_line_joining() -> None:
    reconstructor = ParagraphReconstructor()

    # Linhas de largura fixa que compõem um único parágrafo
    raw = (
        "The sun dipped beneath the horizon, casting long\n"
        "shadows across the deserted valley.\n"
        "A distant train whistle echoed softly."
    )
    blocks = reconstructor.reconstruct(raw)

    assert len(blocks) == 1
    assert blocks[0].text == (
        "The sun dipped beneath the horizon, casting long "
        "shadows across the deserted valley. "
        "A distant train whistle echoed softly."
    )
    assert blocks[0].original_line_start == 1
    assert blocks[0].original_line_end == 3


def test_hard_line_break_paragraph_separation() -> None:
    reconstructor = ParagraphReconstructor()

    raw = "Paragraph one starts here.\n\nParagraph two follows after blank line."
    blocks = reconstructor.reconstruct(raw)

    assert len(blocks) == 2
    assert blocks[0].text == "Paragraph one starts here."
    assert blocks[1].text == "Paragraph two follows after blank line."


def test_scene_break_detection() -> None:
    reconstructor = ParagraphReconstructor()

    raw = "End of the morning scene.\n\n* * *\n\nBeginning of the evening scene."
    blocks = reconstructor.reconstruct(raw)

    assert len(blocks) == 3
    assert blocks[0].text == "End of the morning scene."
    assert blocks[0].is_scene_break is False

    assert blocks[1].text == "* * *"
    assert blocks[1].is_scene_break is True
    assert blocks[1].scene_marker == "* * *"

    assert blocks[2].text == "Beginning of the evening scene."


def test_dialogue_lines_split_from_narrative() -> None:
    reconstructor = ParagraphReconstructor()

    raw = "He stopped walking.\n— Who goes there? — he demanded.\n— A friend — she answered."
    blocks = reconstructor.reconstruct(raw)

    assert len(blocks) == 3
    assert blocks[0].text == "He stopped walking."
    assert blocks[1].text == "— Who goes there? — he demanded."
    assert blocks[1].is_dialogue_candidate is True
    assert blocks[2].text == "— A friend — she answered."
    assert blocks[2].is_dialogue_candidate is True
