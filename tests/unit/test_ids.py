"""Testes para geração determinística de IDs estáveis."""

from __future__ import annotations

from book_translator.core.ids import (
    compute_content_hash,
    generate_chapter_id,
    generate_document_id,
    generate_paragraph_id,
    generate_project_id,
    generate_section_id,
    generate_segment_id,
    slugify,
)


def test_slugify_accents_and_spaces() -> None:
    """Valida normalização de acentuação, maiúsculas e caracteres especiais."""
    assert slugify("Dom Casmurro — Edição Especial!") == "dom_casmurro_edicao_especial"
    assert slugify("Moby-Dick, or The Whale") == "moby_dick_or_the_whale"
    assert slugify("") == "untitled"


def test_ids_determinism_and_format() -> None:
    """Garante formato estável e determinismo dos IDs hierárquicos."""
    proj_id = generate_project_id("O Primo Basílio")
    assert proj_id == "o_primo_basilio"

    doc_id = generate_document_id(proj_id)
    assert doc_id == "doc_o_primo_basilio"

    ch_id = generate_chapter_id(3)
    assert ch_id == "ch_0003"

    sec_id = generate_section_id(ch_id, 1)
    assert sec_id == "ch_0003_sec_0001"

    p_id = generate_paragraph_id(ch_id, 42)
    assert p_id == "ch_0003_p_00042"

    seg_id = generate_segment_id(ch_id, 127)
    assert seg_id == "ch_0003_seg_00127"


def test_content_hash_stability() -> None:
    """Garante que o hash do conteúdo seja idêntico mesmo com espaços em branco extras."""
    text1 = "It was the best of times, it was the worst of times."
    text2 = "  It was the best of times, it was the worst of times.  \n"
    assert compute_content_hash(text1) == compute_content_hash(text2)
    assert len(compute_content_hash(text1)) == 16
