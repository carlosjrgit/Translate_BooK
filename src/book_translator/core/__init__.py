"""Módulo central com modelos de domínio e contratos canônicos."""

from __future__ import annotations

from book_translator.core.contracts import Identifiable, Serializable
from book_translator.core.models import (
    Chapter,
    Checkpoint,
    Document,
    Entity,
    EventLog,
    Paragraph,
    Project,
    ProjectMetadata,
    Section,
    Segment,
    SegmentStatus,
)

__all__ = [
    "Identifiable",
    "Serializable",
    "SegmentStatus",
    "Section",
    "Paragraph",
    "Segment",
    "Chapter",
    "Document",
    "Entity",
    "Checkpoint",
    "EventLog",
    "ProjectMetadata",
    "Project",
]
