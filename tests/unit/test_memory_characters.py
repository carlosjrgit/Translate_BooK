"""Testes unitários da Character Memory, aliases e auditoria de alterações."""

from __future__ import annotations

import pytest

from book_translator.errors import MemoryConflictError
from book_translator.memory.character_memory import CharacterMemory
from book_translator.memory.models import CharacterEntry


def test_character_memory_add_and_get() -> None:
    mem = CharacterMemory(project_id="p1")

    char = CharacterEntry(
        id="char_0042",
        name="Margaret Henderson",
        aliases=["Margaret", "Mrs. Henderson", "Maggie"],
        gender="feminine",
        relations=["mãe de Jack", "ex-esposa de Robert"],
        treatment="Lady",
        occurrences=10,
    )
    mem.add_character(char)

    by_id = mem.get_character("char_0042")
    assert by_id is not None
    assert by_id.name == "Margaret Henderson"

    by_name = mem.get_by_name("margaret henderson")
    assert by_name is not None
    assert by_name.id == "char_0042"


def test_character_memory_find_by_alias() -> None:
    mem = CharacterMemory(project_id="p1")

    char = CharacterEntry(
        id="char_0042",
        name="Margaret Henderson",
        aliases=["Margaret", "Mrs. Henderson", "Maggie"],
    )
    mem.add_character(char)

    # Busca por cada alias
    m1 = mem.find_by_alias("Maggie")
    assert len(m1) == 1
    assert m1[0].name == "Margaret Henderson"

    m2 = mem.find_by_alias("mrs. henderson")
    assert len(m2) == 1
    assert m2[0].name == "Margaret Henderson"

    # Alias inexistente
    m3 = mem.find_by_alias("Desconhecido")
    assert len(m3) == 0


def test_character_memory_update_with_audit_history() -> None:
    mem = CharacterMemory(project_id="p1")

    char = CharacterEntry(
        id="char_0042",
        name="Margaret Henderson",
        speech_style="neutro",
        gender="unknown",
    )
    mem.add_character(char)

    # Atualização com autor e justificativa
    updated = mem.update_character(
        character_id="char_0042",
        changes={"speech_style": "formal irônico", "gender": "feminine"},
        author="editor_carlos",
        reason="Análise do capítulo 3 confirmou tom e gênero",
    )

    assert updated.speech_style == "formal irônico"
    assert updated.gender == "feminine"
    assert len(updated.history) == 2

    # Verifica os registros de revisão
    rev_speech = next(r for r in updated.history if r.field_name == "speech_style")
    assert rev_speech.old_value == "neutro"
    assert rev_speech.new_value == "formal irônico"
    assert rev_speech.changed_by == "editor_carlos"
    assert "capítulo 3" in rev_speech.reason

    rev_gender = next(r for r in updated.history if r.field_name == "gender")
    assert rev_gender.old_value == "unknown"
    assert rev_gender.new_value == "feminine"


def test_character_memory_conflict_duplicate_canonical_name() -> None:
    mem = CharacterMemory(project_id="p1")

    c1 = CharacterEntry(id="char_01", name="Sherlock Holmes")
    mem.add_character(c1)

    c2 = CharacterEntry(id="char_02", name="Sherlock Holmes")
    with pytest.raises(MemoryConflictError, match="já pertence ao personagem"):
        mem.add_character(c2)


def test_character_memory_detect_conflicts_shared_alias() -> None:
    mem = CharacterMemory(project_id="p1")

    c1 = CharacterEntry(
        id="char_01",
        name="Robert Henderson",
        aliases=["Henderson", "Bob"],
    )
    c2 = CharacterEntry(
        id="char_02",
        name="Jack Henderson",
        aliases=["Henderson", "Jackie"],
    )
    mem.add_character(c1)
    mem.add_character(c2)

    # Detecta que "Henderson" é um alias compartilhado por dois personagens
    conflicts = mem.detect_conflicts()
    assert len(conflicts) >= 1
    shared = next(c for c in conflicts if c.term_or_name == "henderson")
    assert shared.severity == "warning"
    assert "char_01" in shared.details["character_ids"]
    assert "char_02" in shared.details["character_ids"]
