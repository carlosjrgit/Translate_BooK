"""Testes de consolidação de aliases, homônimos e resolução de ambiguidade."""

from __future__ import annotations

from book_translator.analysis.alias_resolver import AliasResolver
from book_translator.analysis.models import EntityType
from book_translator.analysis.ner.interface import RawEntityMention


def test_alias_consolidation_unambiguous() -> None:
    resolver = AliasResolver()

    mentions = [
        RawEntityMention(
            text="Sherlock Holmes",
            entity_type=EntityType.CHARACTER,
            confidence=0.95,
            start_char=0,
            end_char=15,
            chapter_id="ch_0001",
            unit_id="p1",
            snippet="Sherlock Holmes arrived early.",
        ),
        RawEntityMention(
            text="Holmes",
            entity_type=EntityType.CHARACTER,
            confidence=0.85,
            start_char=20,
            end_char=26,
            chapter_id="ch_0001",
            unit_id="p3",
            snippet="Holmes examined the carpet.",
        ),
    ]

    entities = resolver.resolve(mentions)

    # Deve haver apenas 1 entidade canônica ("Sherlock Holmes") com "Holmes" como alias
    assert len(entities) == 1
    holmes = entities[0]
    assert holmes.canonical_name == "Sherlock Holmes"
    assert "Holmes" in holmes.aliases
    assert holmes.occurrences_count == 2
    assert not holmes.is_ambiguous

    # As ocorrências apontam para suas respectivas unidades
    u_ids = [occ.unit_id for occ in holmes.occurrences]
    assert "p1" in u_ids
    assert "p3" in u_ids


def test_homonym_ambiguity_flagging() -> None:
    resolver = AliasResolver()

    # Temos dois personagens com o mesmo sobrenome: Robert Henderson e Jack Henderson
    mentions = [
        RawEntityMention(
            text="Robert Henderson",
            entity_type=EntityType.CHARACTER,
            confidence=0.95,
            start_char=0,
            end_char=16,
            chapter_id="ch_0001",
            unit_id="p1",
            snippet="Robert Henderson was the older brother.",
        ),
        RawEntityMention(
            text="Jack Henderson",
            entity_type=EntityType.CHARACTER,
            confidence=0.95,
            start_char=30,
            end_char=44,
            chapter_id="ch_0001",
            unit_id="p2",
            snippet="Jack Henderson was the younger one.",
        ),
        # Menção isolada a "Henderson": NÃO PODE ser fundida cegamente!
        RawEntityMention(
            text="Henderson",
            entity_type=EntityType.CHARACTER,
            confidence=0.70,
            start_char=60,
            end_char=69,
            chapter_id="ch_0002",
            unit_id="p10",
            snippet="Henderson smiled faintly at the remark.",
        ),
    ]

    entities = resolver.resolve(mentions)

    # Esperamos:
    # 1. Entidade Robert Henderson
    # 2. Entidade Jack Henderson
    # 3. Entidade ambígua Henderson com is_ambiguous=True
    robert = next((e for e in entities if e.canonical_name == "Robert Henderson"), None)
    jack = next((e for e in entities if e.canonical_name == "Jack Henderson"), None)
    ambiguous = next((e for e in entities if e.canonical_name == "Henderson"), None)

    assert robert is not None
    assert jack is not None
    assert ambiguous is not None

    # O registro ambíguo deve estar marcado como ambíguo
    assert ambiguous.is_ambiguous is True
    assert len(ambiguous.candidate_entity_ids) == 2
    assert robert.id in ambiguous.candidate_entity_ids
    assert jack.id in ambiguous.candidate_entity_ids

    # Confere que possui inferência de ambiguidade com evidência
    assert len(ambiguous.inferences) >= 1
    assert ambiguous.inferences[0].inference_type == "alias_ambiguity"
    assert ambiguous.inferences[0].evidence != ""
