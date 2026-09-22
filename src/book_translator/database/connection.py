"""Gerenciador de conexão SQLite configurado com integridade e WAL mode."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from book_translator.errors import DatabaseError


def get_sqlite_connection(
    db_path: Path | str,
    timeout: float = 30.0,
    check_same_thread: bool = False,
) -> sqlite3.Connection:
    """Cria e configura uma conexão SQLite com foreign keys ativadas e WAL mode."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(
            str(path),
            timeout=timeout,
            check_same_thread=check_same_thread,
        )
        conn.row_factory = sqlite3.Row

        # Configurações essenciais de integridade e concorrência
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn
    except sqlite3.Error as exc:
        raise DatabaseError(f"Falha ao conectar com banco SQLite em {path}: {exc}") from exc


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Cursor, None, None]:
    """Gerenciador de contexto para transações com rollback automático em falhas."""
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise DatabaseError(f"Erro na transação SQLite (rollback executado): {exc}") from exc
    finally:
        cursor.close()


def wal_checkpoint(conn: sqlite3.Connection) -> None:
    """Força o flush do log WAL para o arquivo principal de banco de dados."""
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except sqlite3.Error as exc:
        raise DatabaseError(f"Falha ao executar wal_checkpoint: {exc}") from exc
