"""Testes para o motor de NER heurístico e fábrica de interfaces plugáveis."""

from __future__ import annotations

import pytest

from book_translator.analysis.models import EntityType
from book_translator.analysis.ner.factory import get_ner_engine
from book_translator.analysis.ner.heuristic_ner import HeuristicNER
from book_translator.errors import ConfigurationError


def test_ner_extract_character_with_honorific() -> None:
    ner = HeuristicNER()
    text = "Yesterday, Dr. John Watson visited Mrs. Hudson at her residence."
    mentions = ner.extract_entities(text)

    names = [m.text for m in mentions]
    assert "Dr. John Watson" in names
    assert "Mrs. Hudson" in names

    watson = next(m for m in mentions if "Watson" in m.text)
    assert watson.entity_type == EntityType.CHARACTER
    assert watson.honorific == "Dr."
    assert watson.confidence >= 0.90


def test_ner_extract_location() -> None:
    ner = HeuristicNER()
    text = "They walked down Baker Street and crossed London Bridge."
    mentions = ner.extract_entities(text)

    locs = [m for m in mentions if m.entity_type == EntityType.LOCATION]
    loc_names = [loc.text for loc in locs]

    assert "Baker Street" in loc_names
    assert "London Bridge" in loc_names
    assert all(loc.confidence >= 0.85 for loc in locs)


def test_ner_extract_organization() -> None:
    ner = HeuristicNER()
    text = "The Inspector contacted Scotland Yard and alerted the Royal Guard."
    mentions = ner.extract_entities(text)

    orgs = [m for m in mentions if m.entity_type == EntityType.ORGANIZATION]
    org_names = [o.text for o in orgs]

    assert "Scotland Yard" in org_names
    assert "Royal Guard" in org_names
    assert all(o.confidence >= 0.85 for o in orgs)


def test_ner_speech_verb_confidence_boost() -> None:
    ner = HeuristicNER()
    # Menção sem verbo de elocução
    text1 = "Arthur Conan stood silently in the corner."
    m1 = ner.extract_entities(text1)

    # Menção com verbo de elocução
    text2 = "Arthur Conan said that the door was locked."
    m2 = ner.extract_entities(text2)

    assert len(m1) >= 1
    assert len(m2) >= 1
    # O com verbo de fala deve ter maior ou igual confiança
    assert m2[0].confidence >= m1[0].confidence


def test_ner_factory() -> None:
    engine = get_ner_engine("heuristic")
    assert isinstance(engine, HeuristicNER)
    assert engine.engine_name == "heuristic"

    with pytest.raises(ConfigurationError, match="não suportado"):
        get_ner_engine("unsupported_ai_engine")
