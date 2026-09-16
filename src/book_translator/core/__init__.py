"""Módulo central com modelos de domínio, contratos e representação documental."""

from __future__ import annotations

from book_translator.core.contracts import Identifiable, Serializable
from book_translator.core.document import (
    Chapter,
    DialogueBlock,
    Document,
    DocumentMetadata,
    Footnote,
    FormattingSpan,
    Heading,
    ImagePlaceholder,
    Paragraph,
    Reference,
    Section,
    SourceLocation,
)
from book_translator.core.models import (
    Checkpoint,
    Entity,
    EventLog,
    Project,
    ProjectMetadata,
    Segment,
    SegmentStatus,
)

__all__ = [
    "Identifiable",
    "Serializable",
    "SourceLocation",
    "FormattingSpan",
    "Heading",
    "Paragraph",
    "DialogueBlock",
    "Footnote",
    "Reference",
    "ImagePlaceholder",
    "Section",
    "Chapter",
    "DocumentMetadata",
    "Document",
    "SegmentStatus",
    "Segment",
    "Entity",
    "Checkpoint",
    "EventLog",
    "ProjectMetadata",
    "Project",
]
