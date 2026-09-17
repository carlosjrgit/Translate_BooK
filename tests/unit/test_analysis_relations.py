"""Testes para extração de relações entre entidades com evidência textual."""

from __future__ import annotations

from book_translator.analysis.models import AnalyzedEntity, EntityType
from book_translator.analysis.relation_extractor import RelationExtractor


def test_relation_extraction_possessive() -> None:
    extractor = RelationExtractor()

    arthur = AnalyzedEntity(id="char_01", canonical_name="Arthur", entity_type=EntityType.CHARACTER)
    margaret = AnalyzedEntity(
        id="char_02", canonical_name="Margaret", entity_type=EntityType.CHARACTER
    )

    sentence = "Arthur's mother Margaret stood by the fireplace."
    rels = extractor.extract_relations(
        text=sentence,
        entities=[arthur, margaret],
        chapter_id="ch_0001",
        unit_id="p1",
    )

    assert len(rels) == 1
    rel = rels[0]
    assert rel.source_entity_id == margaret.id
    assert rel.target_entity_id == arthur.id
    assert rel.relation_type == "mother_of"
    assert rel.confidence >= 0.85
    assert "mother" in rel.evidence
    assert rel.source_unit_id == "p1"


def test_relation_extraction_inverse() -> None:
    extractor = RelationExtractor()

    watson = AnalyzedEntity(id="char_01", canonical_name="Watson", entity_type=EntityType.CHARACTER)
    holmes = AnalyzedEntity(id="char_02", canonical_name="Holmes", entity_type=EntityType.CHARACTER)

    sentence = "Watson, the faithful friend of Holmes, smiled warmly."
    rels = extractor.extract_relations(
        text=sentence,
        entities=[watson, holmes],
        chapter_id="ch_0001",
        unit_id="p3",
    )

    assert len(rels) == 1
    rel = rels[0]
    assert rel.source_name == "Watson"
    assert rel.target_name == "Holmes"
    assert rel.relation_type == "friend_of"
    assert rel.confidence >= 0.85
    assert "friend" in rel.evidence
