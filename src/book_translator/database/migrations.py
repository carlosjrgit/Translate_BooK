"""Motor de migrations para versionamento evolutivo do schema SQLite."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from book_translator.database.connection import transaction
from book_translator.errors import DatabaseError
from book_translator.logging import get_logger

logger = get_logger("database.migrations")

MIGRATIONS_DIR = Path(__file__).parent / "sql"


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Garante a existência da tabela de controle de migrations."""
    with transaction(conn) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Retorna o conjunto de versões de migrations já aplicadas no banco."""
    ensure_migrations_table(conn)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        rows = cursor.fetchall()
        return {int(row[0]) for row in rows}
    finally:
        cursor.close()


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """Retorna a versão mais recente aplicada no schema."""
    applied = get_applied_versions(conn)
    return max(applied) if applied else 0


def discover_migration_files(migrations_dir: Path | None = None) -> list[tuple[int, str, Path]]:
    """Descobre e ordena os arquivos SQL de migration disponíveis."""
    directory = migrations_dir or MIGRATIONS_DIR
    if not directory.exists():
        return []

    migration_files: list[tuple[int, str, Path]] = []
    pattern = re.compile(r"^(\d{4})_(.+)\.sql$")

    for file_path in directory.glob("*.sql"):
        match = pattern.match(file_path.name)
        if match:
            version = int(match.group(1))
            name = match.group(2)
            migration_files.append((version, name, file_path))

    return sorted(migration_files, key=lambda item: item[0])


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path | None = None,
) -> list[int]:
    """Aplica todas as migrations pendentes de forma determinística e transacional."""
    ensure_migrations_table(conn)
    applied = get_applied_versions(conn)
    all_migrations = discover_migration_files(migrations_dir)

    newly_applied: list[int] = []

    for version, name, file_path in all_migrations:
        if version in applied:
            continue

        logger.info(f"Aplicando migration v{version:04d}: {name} ({file_path.name})")
        sql_content = file_path.read_text(encoding="utf-8")

        try:
            with transaction(conn) as cur:
                cur.executescript(sql_content)
                cur.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                    (version, name),
                )
            newly_applied.append(version)
        except Exception as exc:
            raise DatabaseError(
                f"Falha crítica ao aplicar migration v{version:04d} ({file_path.name}): {exc}"
            ) from exc

    return newly_applied
