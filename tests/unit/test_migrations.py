"""Testes do motor de migrations do SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from book_translator.database.connection import get_sqlite_connection
from book_translator.database.migrations import (
    apply_migrations,
    discover_migration_files,
    get_applied_versions,
    get_current_schema_version,
)


def test_discover_migration_files() -> None:
    """Verifica a descoberta e ordenação dos arquivos de migration."""
    migrations = discover_migration_files()
    assert len(migrations) >= 2
    assert migrations[0][0] == 1
    assert migrations[1][0] == 2
    assert migrations[0][1] == "initial_schema"
    assert migrations[1][1] == "add_indices"


def test_apply_migrations_and_idempotency(tmp_path: Path) -> None:
    """Testa aplicação inicial das migrations e confirma idempotência."""
    db_file = tmp_path / "migration_test.db"
    conn = get_sqlite_connection(db_file)

    # Aplicação inicial
    applied = apply_migrations(conn)
    assert 1 in applied
    assert 2 in applied
    assert 3 in applied
    assert 4 in applied
    assert get_current_schema_version(conn) >= 4

    # Verifica se as tabelas foram criadas
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    assert "projects" in tables
    assert "documents" in tables
    assert "chapters" in tables
    assert "segments" in tables
    assert "headings" in tables
    assert "dialogues" in tables
    assert "footnotes" in tables
    assert "references_bibliography" in tables
    assert "images" in tables
    assert "characters" in tables
    assert "glossary" in tables
    assert "translation_memory" in tables
    assert "style_bible" in tables
    assert "memory_audit_log" in tables
    assert "checkpoints" in tables
    assert "schema_migrations" in tables
    cur.close()

    # Segunda chamada: nenhuma nova migration deve ser executada
    reapplied = apply_migrations(conn)
    assert reapplied == []
    assert get_applied_versions(conn) == {1, 2, 3, 4}

    conn.close()


def test_migration_table_creation(tmp_path: Path) -> None:
    """Valida a criação e leitura da tabela schema_migrations."""
    conn = sqlite3.connect(":memory:")
    assert get_current_schema_version(conn) == 0
    applied = apply_migrations(conn)
    assert len(applied) >= 2
    assert get_current_schema_version(conn) == max(applied)
    conn.close()
