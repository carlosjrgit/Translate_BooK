"""Tests for the unified MemoryManager facade coordinating all memories and persistence."""

from uuid import uuid4

import pytest

from book_translator.core.models import Project, ProjectMetadata
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.memory.manager import MemoryManager
from book_translator.memory.models import (
    CharacterEntry,
    GlossaryEntry,
    StyleBible,
    TranslationMemoryEntry,
)


@pytest.fixture
def temp_db(tmp_path):
    """Provide an initialized SQLiteDatabase with a pre-created test project."""
    db_path = tmp_path / "test_manager.db"
    db = SQLiteDatabase(db_path)
    db.initialize()
    meta = ProjectMetadata(
        project_id="test_project",
        book_title="Manager Test Book",
        source_file_path=str(tmp_path / "source.txt"),
        source_file_sha256="abcdef123456",
    )
    proj = Project(
        metadata=meta,
        project_dir=tmp_path,
        db_path=db_path,
    )
    db.save_project(proj)
    yield db
    db.close()


def test_memory_manager_persistence_and_reload(temp_db):
    project_id = "test_project"
    mgr1 = MemoryManager(project_id, db=temp_db)

    # Add character
    c = CharacterEntry(
        id=str(uuid4()),
        project_id=project_id,
        canonical_name="Lord John",
        aliases=["John", "Lord J."],
        treatment="My Lord",
        confidence=0.9,
    )
    mgr1.characters.add_character(c, changed_by="user_1")

    # Add glossary
    g = GlossaryEntry(
        id=str(uuid4()),
        project_id=project_id,
        source_term="Wand",
        target_term="Varinha",
        locked=True,
    )
    mgr1.glossary.add_entry(g, changed_by="user_1")

    # Add TM
    tm = TranslationMemoryEntry(
        id=str(uuid4()),
        project_id=project_id,
        source_term="Magic spell",
        target_term="Feitiço mágico",
        locked=True,
        confidence=0.95,
    )
    mgr1.translation_memory.add_entry(tm, changed_by="user_1")

    # Style Bible
    sb = StyleBible(
        project_id=project_id,
        tone="literary",
        formality_level="formal",
        custom_rules={"honorifics": "preserve"},
    )
    mgr1.set_style_bible(sb)

    # Now create a brand new MemoryManager pointing to the same DB and verify data reloaded
    mgr2 = MemoryManager(project_id, db=temp_db)

    assert len(mgr2.characters.find_by_alias("Lord J.")) > 0
    assert mgr2.characters.find_by_alias("Lord J.")[0].treatment == "My Lord"

    assert mgr2.glossary.get_entry("Wand") is not None
    assert mgr2.glossary.get_entry("Wand").target_term == "Varinha"

    assert mgr2.translation_memory.get_entry("Magic spell") is not None
    assert mgr2.translation_memory.get_entry("Magic spell").target == "Feitiço mágico"

    assert mgr2.style_bible.tone == "literary"


def test_memory_manager_cross_memory_conflict_detection(temp_db):
    project_id = "test_project"
    mgr = MemoryManager(project_id, db=temp_db)

    # Glossary has source "Elder Wand" -> "Varinha das Varinhas"
    mgr.glossary.add_entry(
        GlossaryEntry(
            id=str(uuid4()),
            project_id=project_id,
            source_term="Elder Wand",
            target_term="Varinha das Varinhas",
            locked=True,
        )
    )

    # TM has source "Elder Wand" -> "Varinha Anciã" (divergent target!)
    mgr.translation_memory.add_entry(
        TranslationMemoryEntry(
            id=str(uuid4()),
            project_id=project_id,
            source_term="Elder Wand",
            target_term="Varinha Anciã",
            confidence=0.8,
        )
    )

    all_conflicts = mgr.detect_all_conflicts()
    cross_conflicts = [c for c in all_conflicts if c.memory_type == "cross_memory_conflict"]
    assert len(cross_conflicts) == 1
    assert cross_conflicts[0].term_or_name == "Elder Wand"
    assert "Varinha das Varinhas" in cross_conflicts[0].existing_value
    assert "Varinha Anciã" in cross_conflicts[0].conflicting_value


def test_memory_manager_verify_all_locked_terms(temp_db):
    project_id = "test_project"
    mgr = MemoryManager(project_id, db=temp_db)

    # Add locked glossary term
    mgr.glossary.add_entry(
        GlossaryEntry(
            id=str(uuid4()),
            project_id=project_id,
            source_term="Hogwarts",
            target_term="Hogwarts",
            locked=True,
        )
    )

    # Add locked TM segment
    mgr.translation_memory.add_entry(
        TranslationMemoryEntry(
            id=str(uuid4()),
            project_id=project_id,
            source_term="Welcome home",
            target_term="Bem-vindo ao lar",
            locked=True,
        )
    )

    # Both present
    res_all_pass = mgr.verify_all_locked_terms(
        "Welcome home to Hogwarts!",
        "Bem-vindo ao lar em Hogwarts!",
    )
    assert res_all_pass.passed is True
    assert len(res_all_pass.violations) == 0

    # One missing
    res_one_fail = mgr.verify_all_locked_terms(
        "Welcome home to Hogwarts!",
        "Bem-vindo ao castelo!",  # Missing "Hogwarts" and "Bem-vindo ao lar"
    )
    assert res_one_fail.passed is False
    assert len(res_one_fail.violations) == 2


def test_memory_manager_audit_history(temp_db):
    project_id = "test_project"
    mgr = MemoryManager(project_id, db=temp_db)

    char_id = str(uuid4())
    char = CharacterEntry(
        id=char_id,
        project_id=project_id,
        canonical_name="Sherlock Holmes",
        aliases=["Holmes"],
    )
    mgr.characters.add_character(char, changed_by="detective_fan")

    # Update character
    mgr.characters.update_character(
        "Sherlock Holmes",
        treatment="Mr. Holmes",
        changed_by="editor_watson",
        reason="Add honorific",
    )

    # Retrieve audit history from database
    history = mgr.get_audit_history(entry_id=char_id)
    assert len(history) == 2
    authors = [h["changed_by"] for h in history]
    assert "detective_fan" in authors
    assert "editor_watson" in authors

    watson_entry = next(h for h in history if h["changed_by"] == "editor_watson")
    assert watson_entry["field_changed"] == "treatment"
    assert watson_entry["new_value"] == "Mr. Holmes"
