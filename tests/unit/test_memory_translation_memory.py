"""Tests for Translation Memory functionality in the memory layer."""

import pytest

from book_translator.core.models import Project, ProjectMetadata
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.errors import LockedTermError
from book_translator.memory.models import TranslationMemoryEntry
from book_translator.memory.translation_memory import TranslationMemory


@pytest.fixture
def temp_db(tmp_path):
    """Provide an initialized SQLiteDatabase with a base project for testing."""
    db_path = tmp_path / "test_tm.db"
    db = SQLiteDatabase(db_path)
    db.initialize()
    meta = ProjectMetadata(
        project_id="test_project",
        book_title="Test Book",
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


def test_tm_add_and_get(temp_db):
    project_id = "test_project"
    tm = TranslationMemory(project_id, db=temp_db)

    entry = TranslationMemoryEntry(
        project_id=project_id,
        source_term="Once upon a time",
        target_term="Era uma vez",
        context="Story opening",
        origin="human",
        status="approved",
        locked=True,
        confidence=1.0,
    )
    tm.add_entry(entry, changed_by="translator_1")

    retrieved = tm.get_entry("Once upon a time")
    assert retrieved is not None
    assert retrieved.target == "Era uma vez"
    assert retrieved.locked is True
    assert retrieved.confidence == 1.0
    assert len(retrieved.history) == 1
    assert retrieved.history[0].field_name == "created"


def test_tm_locked_term_protection(temp_db):
    project_id = "test_project"
    tm = TranslationMemory(project_id, db=temp_db)

    entry = TranslationMemoryEntry(
        project_id=project_id,
        source_term="Good morning",
        target_term="Bom dia",
        locked=True,
        confidence=0.95,
    )
    tm.add_entry(entry)

    # Attempting to overwrite locked entry without force must fail
    replacement = TranslationMemoryEntry(
        project_id=project_id,
        source_term="Good morning",
        target_term="Olá",
        locked=False,
    )
    with pytest.raises(LockedTermError):
        tm.add_entry(replacement)

    # With force=True, updating locked entry succeeds and creates revision
    updated = tm.update_entry(
        "Good morning",
        target="Bom dia a todos",
        force=True,
        changed_by="lead_editor",
        reason="Context specific correction",
    )
    assert updated.target == "Bom dia a todos"
    assert len(updated.history) >= 2


def test_tm_search(temp_db):
    project_id = "test_project"
    tm = TranslationMemory(project_id, db=temp_db)

    tm.add_entry(
        TranslationMemoryEntry(
            project_id=project_id,
            source_term="Farewell, my friend.",
            target_term="Adeus, meu amigo.",
            confidence=0.9,
        )
    )
    tm.add_entry(
        TranslationMemoryEntry(
            project_id=project_id,
            source_term="Farewell and good luck.",
            target_term="Adeus e boa sorte.",
            confidence=0.7,
        )
    )

    # Exact search
    exact = tm.search("Farewell, my friend.", exact=True)
    assert len(exact) == 1
    assert exact[0].target == "Adeus, meu amigo."

    # Substring search
    sub = tm.search("Farewell", exact=False)
    assert len(sub) == 2

    # Confidence filter
    high_conf = tm.search("Farewell", exact=False, min_confidence=0.85)
    assert len(high_conf) == 1
    assert high_conf[0].source == "Farewell, my friend."


def test_tm_verify_locked_terms(temp_db):
    project_id = "test_project"
    tm = TranslationMemory(project_id, db=temp_db)

    tm.add_entry(
        TranslationMemoryEntry(
            project_id=project_id,
            source_term="The end.",
            target_term="Fim.",
            locked=True,
        )
    )

    # Compliant target
    res_compliant = tm.verify_locked_terms(
        "And that is the end. Truly.", "E esse é o Fim. Verdadeiramente."
    )
    assert res_compliant.passed is True
    assert len(res_compliant.missing_terms) == 0

    # Non-compliant target
    res_failed = tm.verify_locked_terms(
        "And that is the end. Truly.", "E esse é o término. Verdadeiramente."
    )
    assert res_failed.passed is False
    assert len(res_failed.missing_terms) == 1
    assert res_failed.missing_terms[0]["expected_target"] == "Fim."


def test_tm_conflict_detection(temp_db):
    project_id = "test_project"
    tm = TranslationMemory(project_id, db=temp_db)

    tm.add_entry(
        TranslationMemoryEntry(
            project_id=project_id,
            source_term="Bad segment",
            target_term="Segmento ruim",
            status="rejected",
        )
    )

    conflicts = tm.detect_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].memory_type == "translation_memory"
    assert "rejected" in conflicts[0].reason
