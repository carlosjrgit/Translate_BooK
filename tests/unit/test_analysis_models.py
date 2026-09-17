"""Testes unitários para os modelos do subsistema de análise."""

from __future__ import annotations

from book_translator.analysis.models import (
    AnalyzedEntity,
    EntityInference,
    EntityOccurrence,
    EntityType,
    Relationship,
)


def test_entity_models_and_properties() -> None:
    occ1 = EntityOccurrence(
        chapter_id="ch_0001",
        unit_id="p1",
        text="Sherlock Holmes",
        line_number=5,
        surrounding_snippet="...Sherlock Holmes looked closely...",
    )
    occ2 = EntityOccurrence(
        chapter_id="ch_0002",
        unit_id="p12",
        text="Holmes",
        line_number=20,
        surrounding_snippet="...Holmes nodded in agreement...",
    )

    inference = EntityInference(
        inference_type="alias_resolution",
        value="Refers to Sherlock Holmes",
        confidence=0.85,
        evidence="Holmes in Ch 2 refers to Sherlock Holmes",
        source_unit_id="p12",
        source_chapter_id="ch_0002",
    )

    entity = AnalyzedEntity(
        id="char_0001",
        canonical_name="Sherlock Holmes",
        entity_type=EntityType.CHARACTER,
        aliases=["Holmes"],
        occurrences=[occ1, occ2],
        inferences=[inference],
        honorifics=["Mr."],
        gender="masculine",
    )

    assert entity.id == "char_0001"
    assert entity.canonical_name == "Sherlock Holmes"
    assert entity.entity_type == EntityType.CHARACTER
    assert entity.occurrences_count == 2
    assert entity.first_appearance_chapter == "ch_0001"
    assert len(entity.inferences) == 1
    assert entity.inferences[0].confidence == 0.85
    assert entity.inferences[0].evidence != ""


def test_relationship_model() -> None:
    rel = Relationship(
        source_entity_id="char_0002",
        target_entity_id="char_0001",
        source_name="Lady Margaret",
        target_name="Arthur",
        relation_type="mother_of",
        confidence=0.90,
        evidence="Arthur's mother Lady Margaret entered.",
        source_unit_id="p5",
        source_chapter_id="ch_0001",
    )

    assert rel.source_entity_id == "char_0002"
    assert rel.target_entity_id == "char_0001"
    assert rel.relation_type == "mother_of"
    assert rel.confidence == 0.90
    assert "mother" in rel.evidence
