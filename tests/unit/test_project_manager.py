"""Testes do ProjectManager: ciclo de vida, integridade, erros e recuperação."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.core.models import Chapter, Checkpoint, Document, Segment, SegmentStatus
from book_translator.errors import ConfigurationError, DatabaseError, IngestionError
from book_translator.projects.manager import ProjectManager, compute_file_sha256


def test_create_close_and_reopen_project(tmp_path: Path) -> None:
    """Valida a criação de um projeto, fechamento e subsequente reabertura íntegra."""
    # 1. Cria arquivo de teste
    source_file = tmp_path / "war_and_peace.txt"
    source_file.write_text(
        "Well, Prince, so Genoa and Lucca are now just family estates...",
        encoding="utf-8",
    )

    mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    project, db = mgr.create_project(
        book_title="War and Peace",
        source_file_path=source_file,
    )

    assert project.metadata.project_id == "war_and_peace"
    assert (project.project_dir / "project.db").exists()
    assert (project.project_dir / "source" / f"original_{source_file.name}").exists()
    assert (project.project_dir / "cache").exists()
    assert (project.project_dir / "translations").exists()
    assert (project.project_dir / "output").exists()

    # Fecha o projeto
    mgr.close_project(project, db)

    # Reabre o projeto
    reopened_proj, reopened_db = mgr.open_project(project.project_dir)
    assert reopened_proj.metadata.book_title == "War and Peace"
    assert reopened_proj.metadata.project_id == "war_and_peace"
    assert mgr.verify_source_integrity(reopened_proj) is True

    mgr.close_project(reopened_proj, reopened_db)


def test_source_file_remains_strictly_unmodified(tmp_path: Path) -> None:
    """Garante que o arquivo fonte original do usuário NUNCA é modificado em nenhuma operação."""
    user_docs_dir = tmp_path / "user_documents"
    user_docs_dir.mkdir()
    original_file = user_docs_dir / "my_original_manuscript.txt"
    original_content = "This original book text must remain 100% sacred and untouched forever."
    original_file.write_text(original_content, encoding="utf-8")

    # Coleta atributos originais antes de qualquer operação
    original_hash_before = compute_file_sha256(original_file)
    original_stat_before = original_file.stat()
    original_mtime_before = original_stat_before.st_mtime
    original_size_before = original_stat_before.st_size

    # Executa criação de projeto e operações no banco
    mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    project, db = mgr.create_project(
        book_title="Sacred Manuscript",
        source_file_path=original_file,
    )

    # Simula gravação de dados
    doc = Document(id="doc_sacred", title="Sacred Manuscript")
    db.save_document(doc, project.metadata.project_id)
    ch = Chapter(id="ch_01", title="Chapter 1", order=1)
    db.save_chapter(ch, "doc_sacred")
    seg = Segment(id="seg_01", chapter_id="ch_01", original_text="Untouched sentence.")
    db.save_segment(seg)

    # Fecha e reabre
    mgr.close_project(project, db)
    reopened_proj, reopened_db = mgr.open_project(project.project_dir)
    mgr.close_project(reopened_proj, reopened_db)

    # Re-avalia o arquivo do usuário após todas as operações
    original_hash_after = compute_file_sha256(original_file)
    original_stat_after = original_file.stat()
    original_mtime_after = original_stat_after.st_mtime
    original_size_after = original_stat_after.st_size

    assert original_hash_after == original_hash_before
    assert original_mtime_after == original_mtime_before
    assert original_size_after == original_size_before
    assert original_file.read_text(encoding="utf-8") == original_content


def test_missing_source_file_raises_error(tmp_path: Path) -> None:
    """Testa tentativa de criar projeto com arquivo inexistente."""
    mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    with pytest.raises(IngestionError):
        mgr.create_project("Ghost Book", tmp_path / "non_existent_file.txt")


def test_opening_invalid_project_dir(tmp_path: Path) -> None:
    """Testa abertura de diretório que não é um projeto válido."""
    mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    empty_dir = tmp_path / "empty_folder"
    empty_dir.mkdir()

    with pytest.raises(DatabaseError):
        mgr.open_project(empty_dir)

    with pytest.raises(ConfigurationError):
        mgr.open_project(tmp_path / "folder_does_not_exist")


def test_opening_corrupted_database(tmp_path: Path) -> None:
    """Testa comportamento gracioso ao tentar abrir um project.db corrompido."""
    mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    corrupt_dir = tmp_path / "corrupt_proj"
    corrupt_dir.mkdir()
    corrupt_db = corrupt_dir / "project.db"
    corrupt_db.write_bytes(b"CORRUPTED_GARBAGE_HEADER_NOT_A_SQLITE_DATABASE")

    with pytest.raises(DatabaseError):
        mgr.open_project(corrupt_dir)


def test_simulated_interruption_and_recovery(tmp_path: Path) -> None:
    """Simula uma interrupção abrupta no meio do processamento e valida retomada exata."""
    source_file = tmp_path / "the_hobbit.txt"
    source_file.write_text("In a hole in the ground there lived a hobbit...", encoding="utf-8")

    mgr = ProjectManager(base_projects_dir=tmp_path / "projects")
    project, db = mgr.create_project(
        book_title="The Hobbit",
        source_file_path=source_file,
    )
    pid = project.metadata.project_id

    # Cria documento e capítulo com 6 segmentos
    doc = Document(id="doc_hobbit", title="The Hobbit")
    db.save_document(doc, pid)
    ch = Chapter(id="ch_01", title="An Unexpected Party", order=1)
    db.save_chapter(ch, "doc_hobbit")

    for i in range(1, 7):
        seg = Segment(
            id=f"ch_01_seg_{i:04d}",
            chapter_id="ch_01",
            original_text=f"Sentence {i}",
            sequence_order=i,
        )
        db.save_segment(seg)

    # Simula tradução concluída de apenas 2 segmentos antes de um crash / interrupção
    s1 = db.get_segment("ch_01_seg_0001")
    assert s1 is not None
    s1.translated_text = "Sentença 1 traduzida"
    s1.status = SegmentStatus.TRANSLATED
    db.save_segment(s1)

    s2 = db.get_segment("ch_01_seg_0002")
    assert s2 is not None
    s2.translated_text = "Sentença 2 traduzida"
    s2.status = SegmentStatus.TRANSLATED
    db.save_segment(s2)

    # Salva checkpoint intermediário
    chk = Checkpoint(
        id="chk_crash_point",
        project_id=pid,
        last_completed_chapter_id="ch_01",
        last_completed_segment_id="ch_01_seg_0002",
        completed_segments=2,
        total_segments=6,
        status="in_progress",
    )
    db.save_checkpoint(chk)

    # Simula crash: fecha o banco de forma abrupta
    db.conn.close()

    # O sistema é reiniciado e chama resume_project
    resume_info = mgr.resume_project(project.project_dir)

    assert resume_info["project_id"] == pid
    assert resume_info["total_segments"] == 6
    assert resume_info["completed_segments"] == 2
    assert resume_info["pending_segments_count"] == 4
    assert resume_info["latest_checkpoint"]["last_completed_segment_id"] == "ch_01_seg_0002"
