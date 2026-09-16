"""Módulo de persistência de projetos e banco de dados local."""

from __future__ import annotations

from book_translator.database.base import DatabaseInterface
from book_translator.database.connection import get_sqlite_connection, transaction, wal_checkpoint
from book_translator.database.migrations import apply_migrations, get_current_schema_version
from book_translator.database.sqlite import SQLiteDatabase

__all__ = [
    "DatabaseInterface",
    "SQLiteDatabase",
    "get_sqlite_connection",
    "transaction",
    "wal_checkpoint",
    "apply_migrations",
    "get_current_schema_version",
]
