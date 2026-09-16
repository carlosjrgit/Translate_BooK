"""Modelos de domínio canônicos da representação interna do documento e projeto."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SegmentStatus(str, Enum):
    """Estado do ciclo de vida de um segmento de tradução."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    TRANSLATED = "translated"
    VALIDATED = "validated"
    FLAGGED = "flagged"
    ERROR = "error"


@dataclass
class Section:
    """Seção ou subseção hierárquica dentro de um capítulo."""

    id: str  # ex: "chapter_0001_sec_0001"
    chapter_id: str
    title: str
    order_index: int = 0
    parent_section_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Paragraph:
    """Parágrafo original extraído do documento."""

    id: str  # ex: "chapter_0001_p_00001"
    chapter_id: str
    order_index: int
    raw_text: str
    section_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Segment:
    """Unidade atômica de tradução com rastreabilidade persistente."""

    id: str  # ex: "chapter_0001_seg_00001"
    chapter_id: str
    original_text: str
    translated_text: str = ""
    status: SegmentStatus = SegmentStatus.PENDING
    sequence_order: int = 0
    paragraph_id: str | None = None
    section_id: str | None = None
    original_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    revisions: list[str] = field(default_factory=list)

    @property
    def is_translated(self) -> bool:
        return bool(self.translated_text and self.status != SegmentStatus.PENDING)


@dataclass
class Chapter:
    """Capítulo ou seção macro do documento."""

    id: str  # ex: "chapter_0001"
    title: str
    order: int
    segments: list[Segment] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def total_words(self) -> int:
        return sum(len(s.original_text.split()) for s in self.segments)


@dataclass
class Document:
    """Representação intermediária padronizada e canônica de uma obra."""

    id: str
    title: str
    author: str = "Desconhecido"
    source_format: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    chapters: list[Chapter] = field(default_factory=list)
    footnotes: list[dict[str, Any]] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    @property
    def total_segments(self) -> int:
        return sum(len(c.segments) for c in self.chapters)


@dataclass
class Entity:
    """Entidade global identificada na obra (local, organização, conceito)."""

    id: str
    project_id: str
    name: str
    entity_type: str  # 'location', 'organization', 'concept', etc.
    description: str = ""
    occurrences: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Checkpoint:
    """Ponto de restauração persistido do progresso da tradução."""

    id: str
    project_id: str
    last_completed_chapter_id: str = ""
    last_completed_segment_id: str = ""
    completed_segments: int = 0
    total_segments: int = 0
    status: str = "in_progress"  # 'initialized', 'in_progress', 'paused', 'completed'
    created_at: str = ""


@dataclass
class EventLog:
    """Registro de evento ou erro ocorrido durante a execução do projeto."""

    id: str
    project_id: str
    level: str  # 'INFO', 'WARNING', 'ERROR'
    phase: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class ProjectMetadata:
    """Metadados de identificação do projeto do livro."""

    project_id: str
    book_title: str
    source_file_path: str
    source_language: str = "en"
    target_language: str = "pt-BR"
    source_file_sha256: str = ""
    created_at: str = ""
    updated_at: str = ""
    status: str = "active"


@dataclass
class Project:
    """Entidade que agrupa o livro, diretórios locais e banco de dados do projeto."""

    metadata: ProjectMetadata
    project_dir: Path
    db_path: Path
    document: Document | None = None
    config: dict[str, Any] = field(default_factory=dict)
