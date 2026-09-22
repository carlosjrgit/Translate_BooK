"""Contratos e modelos para exportação e reconstrução do documento traduzido."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from book_translator.core.models import Document, Segment


@dataclass
class ExportOptions:
    """Opções de customização para reconstrução do documento."""

    preserve_formatting: bool = True
    include_translator_preface: bool = False
    include_metadata: bool = True
    include_footnotes: bool = True
    target_encoding: str = "utf-8"
    custom_title: str | None = None
    custom_author: str | None = None
    extra_options: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ExporterInterface(Protocol):
    """Protocolo formal para exportadores de documentos em PT-BR."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        """Formatos aceitos por este exportador (ex: ('epub', 'docx', 'txt'))."""
        ...

    def can_export(self, format_name: str) -> bool:
        """Verifica se o formato solicitado é suportado."""
        ...

    def export(
        self,
        document: Document,
        output_path: Path | str,
        options: ExportOptions | None = None,
    ) -> Path:
        """Gera o arquivo reconstruído sem jamais sobrescrever o arquivo original."""
        ...


def stitch_chapter_segments(segments: list[Segment]) -> list[tuple[str, str]]:
    """Agrupa e remonta (stitch) segmentos fracionados pertencentes ao mesmo parágrafo.

    Retorna uma lista de tuplas (unit_type, texto_completo_do_paragrafo).
    """
    if not segments:
        return []

    sorted_segs = sorted(segments, key=lambda s: getattr(s, "sequence_order", 0))
    stitched: list[tuple[str, str]] = []

    current_p_id: str | None = None
    current_texts: list[str] = []
    current_unit_type: str = "paragraph"
    current_is_split: bool = False

    for seg in sorted_segs:
        text = (seg.translated_text if seg.translated_text else seg.original_text) or ""
        text = text.strip()
        if not text:
            continue

        unit_type = (
            seg.metadata.get("unit_type")
            or getattr(seg.type, "value", str(seg.type))
            if hasattr(seg, "type")
            else "paragraph"
        )
        is_split = bool(seg.metadata.get("paragraph_split"))
        p_id = getattr(seg, "paragraph_id", None)

        is_continuation = (
            p_id is not None
            and current_p_id is not None
            and p_id == current_p_id
            and (is_split or current_is_split)
        )

        if is_continuation:
            current_texts.append(text)
        else:
            if current_texts:
                stitched.append((current_unit_type, " ".join(current_texts)))
                current_texts = []

            if is_split and p_id:
                current_p_id = p_id
                current_unit_type = unit_type
                current_texts = [text]
                current_is_split = True
            else:
                current_p_id = None
                current_unit_type = unit_type
                current_is_split = False
                stitched.append((unit_type, text))

    if current_texts:
        stitched.append((current_unit_type, " ".join(current_texts)))

    return stitched

