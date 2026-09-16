"""Módulo de ingestão e inspeção prévia de documentos."""

from __future__ import annotations

from book_translator.ingestion.base import (
    IngestionInspection,
    IngestionInspectorInterface,
)
from book_translator.ingestion.inspector import IngestionInspector

__all__ = ["IngestionInspection", "IngestionInspectorInterface", "IngestionInspector"]
