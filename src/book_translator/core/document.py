"""Representação interna comum e canônica de documentos e unidades de conteúdo."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
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
class SourceLocation:
    """Localização e vínculo exato do conteúdo no arquivo fonte original."""

    file_path: str = ""
    page_number: int | None = None
    line_number: int | None = None
    char_offset: int | None = None
    xpath_or_selector: str | None = None


@dataclass
class FormattingSpan:
    """Span de formatação de texto com offsets no texto normalizado ou bruto."""

    start: int
    end: int
    style: str  # 'italic', 'bold', 'underline', 'strikethrough', 'code', 'link', 'superscript'
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Heading:
    """Título ou subtítulo dentro da hierarquia do documento."""

    id: str
    chapter_id: str
    level: int  # 1 a 6
    raw_text: str
    normalized_text: str = ""
    reading_order: int = 0
    spans: list[FormattingSpan] = field(default_factory=list)
    source_location: SourceLocation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text and self.raw_text:
            self.normalized_text = self.raw_text


@dataclass
class Paragraph:
    """Parágrafo padrão de prosa ou bloco textual narrativo."""

    id: str
    chapter_id: str
    raw_text: str = ""
    reading_order: int = 0
    order_index: int = 0
    normalized_text: str = ""
    section_id: str | None = None
    spans: list[FormattingSpan] = field(default_factory=list)
    source_location: SourceLocation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text and self.raw_text:
            self.normalized_text = self.raw_text
        if self.order_index and not self.reading_order:
            self.reading_order = self.order_index
        elif self.reading_order and not self.order_index:
            self.order_index = self.reading_order


@dataclass
class DialogueBlock:
    """Bloco explícito de diálogo ou fala de personagem."""

    id: str
    chapter_id: str
    raw_text: str
    reading_order: int = 0
    normalized_text: str = ""
    dialogue_marker: str = "—"  # '—', '"', etc.
    speaker_hint: str | None = None
    spans: list[FormattingSpan] = field(default_factory=list)
    source_location: SourceLocation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text and self.raw_text:
            self.normalized_text = self.raw_text


@dataclass
class Footnote:
    """Nota de rodapé ou nota explicativa vinculada ao texto."""

    id: str
    chapter_id: str
    marker: str  # "1", "*", "a", etc.
    raw_text: str
    normalized_text: str = ""
    reading_order: int = 0
    referencing_unit_id: str | None = None
    source_location: SourceLocation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text and self.raw_text:
            self.normalized_text = self.raw_text


@dataclass
class Reference:
    """Entrada bibliográfica ou referência documental."""

    id: str
    citation_key: str
    raw_text: str
    normalized_text: str = ""
    url: str | None = None
    reading_order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text and self.raw_text:
            self.normalized_text = self.raw_text


@dataclass
class ImagePlaceholder:
    """Representação de imagem ou elemento gráfico contido na obra."""

    id: str
    chapter_id: str
    reading_order: int = 0
    caption_raw: str = ""
    caption_normalized: str = ""
    alt_text: str = ""
    relative_path: str = ""
    original_src: str = ""
    source_location: SourceLocation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Section:
    """Seção ou subseção estrutural dentro de um capítulo."""

    id: str
    chapter_id: str
    title: str
    reading_order: int = 0
    order_index: int = 0
    parent_section_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.order_index and not self.reading_order:
            self.reading_order = self.order_index
        elif self.reading_order and not self.order_index:
            self.order_index = self.reading_order


@dataclass
class Chapter:
    """Capítulo da obra agrupando unidades ordenadas de leitura."""

    id: str
    title: str
    order: int
    reading_order: int = 0
    headings: list[Heading] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    dialogue_blocks: list[DialogueBlock] = field(default_factory=list)
    image_placeholders: list[ImagePlaceholder] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def total_words(self) -> int:
        """Calcula o total de palavras a partir dos segmentos ou parágrafos."""
        if self.segments:
            return sum(len(s.original_text.split()) for s in self.segments)
        text_units = [u.normalized_text for u in self.get_reading_sequence()]
        return sum(len(t.split()) for t in text_units if t)

    def get_reading_sequence(self) -> list[Any]:
        """Retorna todas as unidades de conteúdo do capítulo ordenadas por reading_order."""
        units: list[Any] = []
        units.extend(self.headings)
        units.extend(self.paragraphs)
        units.extend(self.dialogue_blocks)
        units.extend(self.image_placeholders)
        units.extend(self.footnotes)
        return sorted(units, key=lambda u: getattr(u, "reading_order", 0))


@dataclass
class DocumentMetadata:
    """Metadados bibliográficos completos da obra."""

    title: str
    author: str = "Desconhecido"
    language: str = "en"
    publisher: str = ""
    publication_date: str = ""
    isbn: str = ""
    source_format: str = "unknown"
    source_file_path: str = ""
    source_file_sha256: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(init=False)
class Document:
    """Representação canônica do livro, unificando capítulos, notas e referências."""

    id: str
    metadata: DocumentMetadata
    chapters: list[Chapter]
    global_footnotes: list[Footnote]
    references: list[Reference]
    global_images: list[ImagePlaceholder]

    def __init__(
        self,
        id: str,
        metadata: DocumentMetadata | dict[str, Any] | None = None,
        title: str | None = None,
        author: str | None = None,
        source_format: str | None = None,
        chapters: list[Chapter] | None = None,
        global_footnotes: list[Footnote] | None = None,
        references: list[Reference] | None = None,
        global_images: list[ImagePlaceholder] | None = None,
        **kwargs: Any,
    ) -> None:
        self.id = id
        if isinstance(metadata, DocumentMetadata):
            self.metadata = metadata
            if title:
                self.metadata.title = title
            if author:
                self.metadata.author = author
            if source_format:
                self.metadata.source_format = source_format
        else:
            meta_dict = metadata if isinstance(metadata, dict) else {}
            self.metadata = DocumentMetadata(
                title=title or meta_dict.get("title", "Sem Título"),
                author=author or meta_dict.get("author", "Desconhecido"),
                language=meta_dict.get("language", "en"),
                publisher=meta_dict.get("publisher", ""),
                publication_date=meta_dict.get("publication_date", ""),
                isbn=meta_dict.get("isbn", ""),
                source_format=source_format or meta_dict.get("source_format", "unknown"),
                source_file_path=meta_dict.get("source_file_path", ""),
                source_file_sha256=meta_dict.get("source_file_sha256", ""),
                extra=meta_dict.get("extra", {}),
            )
        self.chapters = chapters or []
        self.global_footnotes = global_footnotes or []
        self.references = references or []
        self.global_images = global_images or []

    # Propriedades de compatibilidade com interfaces anteriores
    @property
    def title(self) -> str:
        return self.metadata.title

    @property
    def author(self) -> str:
        return self.metadata.author

    @property
    def source_format(self) -> str:
        return self.metadata.source_format

    @property
    def footnotes(self) -> list[dict[str, Any]]:
        return [asdict(fn) for fn in self.global_footnotes]

    @property
    def images(self) -> list[dict[str, Any]]:
        return [asdict(img) for img in self.global_images]

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    @property
    def total_segments(self) -> int:
        return sum(len(c.segments) for c in self.chapters)

    def get_linear_reading_order(self) -> list[Any]:
        """Retorna a sequência linear de leitura de todas as unidades da obra completa."""
        linear: list[Any] = []
        for ch in sorted(self.chapters, key=lambda c: c.order):
            linear.extend(ch.get_reading_sequence())
        linear.extend(sorted(self.references, key=lambda r: r.reading_order))
        return linear

    def to_dict(self) -> dict[str, Any]:
        """Serializa o documento completo para um dicionário primitivo sem perdas."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        """Reconstrói com fidelidade a árvore completa do documento a partir de um dicionário."""
        raw_meta = data.get("metadata", {})
        if isinstance(raw_meta, dict):
            # Suporta tanto chave 'title' direta quanto metadata aninhado
            meta = DocumentMetadata(
                title=raw_meta.get("title", data.get("title", "Sem Título")),
                author=raw_meta.get("author", data.get("author", "Desconhecido")),
                language=raw_meta.get("language", "en"),
                publisher=raw_meta.get("publisher", ""),
                publication_date=raw_meta.get("publication_date", ""),
                isbn=raw_meta.get("isbn", ""),
                source_format=raw_meta.get("source_format", data.get("source_format", "unknown")),
                source_file_path=raw_meta.get("source_file_path", ""),
                source_file_sha256=raw_meta.get("source_file_sha256", ""),
                extra=raw_meta.get("extra", {}),
            )
        else:
            meta = raw_meta

        def parse_loc(d: dict[str, Any] | None) -> SourceLocation | None:
            return SourceLocation(**d) if d else None

        def parse_spans(spans_list: list[dict[str, Any]]) -> list[FormattingSpan]:
            return [FormattingSpan(**s) for s in spans_list]

        chapters: list[Chapter] = []
        for ch_data in data.get("chapters", []):
            headings = [
                Heading(
                    id=h["id"],
                    chapter_id=h["chapter_id"],
                    level=h["level"],
                    raw_text=h["raw_text"],
                    normalized_text=h["normalized_text"],
                    reading_order=h["reading_order"],
                    spans=parse_spans(h.get("spans", [])),
                    source_location=parse_loc(h.get("source_location")),
                    metadata=h.get("metadata", {}),
                )
                for h in ch_data.get("headings", [])
            ]
            paragraphs = [
                Paragraph(
                    id=p["id"],
                    chapter_id=p["chapter_id"],
                    reading_order=p.get("reading_order", p.get("order_index", 0)),
                    raw_text=p["raw_text"],
                    normalized_text=p.get("normalized_text", p["raw_text"]),
                    section_id=p.get("section_id"),
                    spans=parse_spans(p.get("spans", [])),
                    source_location=parse_loc(p.get("source_location")),
                    metadata=p.get("metadata", {}),
                )
                for p in ch_data.get("paragraphs", [])
            ]
            dialogues = [
                DialogueBlock(
                    id=d["id"],
                    chapter_id=d["chapter_id"],
                    reading_order=d["reading_order"],
                    raw_text=d["raw_text"],
                    normalized_text=d["normalized_text"],
                    dialogue_marker=d.get("dialogue_marker", "—"),
                    speaker_hint=d.get("speaker_hint"),
                    spans=parse_spans(d.get("spans", [])),
                    source_location=parse_loc(d.get("source_location")),
                    metadata=d.get("metadata", {}),
                )
                for d in ch_data.get("dialogue_blocks", [])
            ]
            images = [
                ImagePlaceholder(
                    id=img["id"],
                    chapter_id=img["chapter_id"],
                    reading_order=img["reading_order"],
                    caption_raw=img.get("caption_raw", ""),
                    caption_normalized=img.get("caption_normalized", ""),
                    alt_text=img.get("alt_text", ""),
                    relative_path=img.get("relative_path", ""),
                    original_src=img.get("original_src", ""),
                    source_location=parse_loc(img.get("source_location")),
                    metadata=img.get("metadata", {}),
                )
                for img in ch_data.get("image_placeholders", [])
            ]
            footnotes = [
                Footnote(
                    id=fn["id"],
                    chapter_id=fn["chapter_id"],
                    marker=fn["marker"],
                    raw_text=fn["raw_text"],
                    normalized_text=fn["normalized_text"],
                    reading_order=fn.get("reading_order", 0),
                    referencing_unit_id=fn.get("referencing_unit_id"),
                    source_location=parse_loc(fn.get("source_location")),
                    metadata=fn.get("metadata", {}),
                )
                for fn in ch_data.get("footnotes", [])
            ]
            sections = [
                Section(
                    id=sec["id"],
                    chapter_id=sec["chapter_id"],
                    title=sec["title"],
                    reading_order=sec.get("reading_order", sec.get("order_index", 0)),
                    order_index=sec.get("order_index", 0),
                    parent_section_id=sec.get("parent_section_id"),
                    metadata=sec.get("metadata", {}),
                )
                for sec in ch_data.get("sections", [])
            ]
            segments = [
                Segment(
                    id=s["id"],
                    chapter_id=s["chapter_id"],
                    original_text=s["original_text"],
                    translated_text=s.get("translated_text", ""),
                    status=s.get("status", "pending"),
                    sequence_order=s.get("sequence_order", 0),
                    paragraph_id=s.get("paragraph_id"),
                    section_id=s.get("section_id"),
                    original_hash=s.get("original_hash", ""),
                    metadata=s.get("metadata", {}),
                )
                for s in ch_data.get("segments", [])
            ]

            chapter = Chapter(
                id=ch_data["id"],
                title=ch_data["title"],
                order=ch_data["order"],
                reading_order=ch_data.get("reading_order", ch_data["order"]),
                headings=headings,
                paragraphs=paragraphs,
                dialogue_blocks=dialogues,
                image_placeholders=images,
                footnotes=footnotes,
                sections=sections,
                segments=segments,
                notes=ch_data.get("notes", []),
                metadata=ch_data.get("metadata", {}),
            )
            chapters.append(chapter)

        references = [
            Reference(
                id=r["id"],
                citation_key=r["citation_key"],
                raw_text=r["raw_text"],
                normalized_text=r["normalized_text"],
                url=r.get("url"),
                reading_order=r.get("reading_order", 0),
                metadata=r.get("metadata", {}),
            )
            for r in data.get("references", [])
        ]

        global_footnotes = [
            Footnote(
                id=fn["id"],
                chapter_id=fn["chapter_id"],
                marker=fn["marker"],
                raw_text=fn["raw_text"],
                normalized_text=fn["normalized_text"],
                reading_order=fn.get("reading_order", 0),
                referencing_unit_id=fn.get("referencing_unit_id"),
                source_location=parse_loc(fn.get("source_location")),
                metadata=fn.get("metadata", {}),
            )
            for fn in data.get("global_footnotes", [])
        ]

        global_images = [
            ImagePlaceholder(
                id=img["id"],
                chapter_id=img["chapter_id"],
                reading_order=img["reading_order"],
                caption_raw=img.get("caption_raw", ""),
                caption_normalized=img.get("caption_normalized", ""),
                alt_text=img.get("alt_text", ""),
                relative_path=img.get("relative_path", ""),
                original_src=img.get("original_src", ""),
                source_location=parse_loc(img.get("source_location")),
                metadata=img.get("metadata", {}),
            )
            for img in data.get("global_images", [])
        ]

        return cls(
            id=data["id"],
            metadata=meta,
            chapters=chapters,
            global_footnotes=global_footnotes,
            references=references,
            global_images=global_images,
        )

    def to_json(self, indent: int = 2) -> str:
        """Serializa o documento para uma string formatada em JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> Document:
        """Reconstrói uma instância de Document a partir de string JSON."""
        data = json.loads(json_str)
        return cls.from_dict(data)
