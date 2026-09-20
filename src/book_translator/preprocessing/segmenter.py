"""Segmentação inicial em unidades semanticamente coerentes com rastreabilidade total."""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any

from book_translator.core.ids import compute_content_hash, generate_segment_id
from book_translator.core.models import (
    Chapter,
    DialogueBlock,
    Footnote,
    Heading,
    Paragraph,
    Segment,
    SegmentStatus,
)
from book_translator.preprocessing.config import PreprocessingConfig


class SegmentType(str, Enum):
    """Classificação semântica da unidade de segmentação."""

    PARAGRAPH = "paragraph"
    PARAGRAPH_GROUP = "paragraph_group"
    DIALOGUE = "dialogue"
    SCENE = "small_scene"
    HEADING = "heading"
    FOOTNOTE = "footnote"


class InitialSegmenter:
    """Segmenta o conteúdo estruturado de capítulos em unidades semanticamente coerentes."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()

    def segment_chapter(self, chapter: Chapter) -> list[Segment]:
        """Gera a lista ordenada e rastreável de segmentos para um capítulo."""
        reading_units = chapter.get_reading_sequence()
        if not reading_units:
            return []

        segments: list[Segment] = []
        seg_counter = 1

        def create_segment(
            text: str,
            seg_type: SegmentType,
            unit_ids: list[str],
            locations: list[dict[str, Any]],
            primary_p_id: str | None = None,
            section_id: str | None = None,
            extra_meta: dict[str, Any] | None = None,
        ) -> Segment:
            nonlocal seg_counter
            seg_id = generate_segment_id(chapter.id, seg_counter)
            meta: dict[str, Any] = {
                "segment_type": seg_type.value,
                "unit_ids": unit_ids,
                "source_locations": locations,
                "word_count": len(text.split()),
                "char_count": len(text),
            }
            if hasattr(unit, "metadata") and unit.metadata.get("is_ocr"):
                meta["is_ocr"] = True
                meta["ocr_confidence"] = unit.metadata.get("ocr_confidence")
                meta["ocr_engine"] = unit.metadata.get("ocr_engine")
            if extra_meta:
                meta.update(extra_meta)

            seg = Segment(
                id=seg_id,
                chapter_id=chapter.id,
                original_text=text,
                translated_text="",
                status=SegmentStatus.PENDING,
                sequence_order=seg_counter,
                paragraph_id=primary_p_id,
                section_id=section_id,
                original_hash=compute_content_hash(text),
                metadata=meta,
            )
            seg_counter += 1
            return seg

        idx = 0
        total_units = len(reading_units)

        while idx < total_units:
            unit = reading_units[idx]

            # 1. Heading (Títulos) -> Segmento individual
            if isinstance(unit, Heading):
                raw_or_norm = unit.normalized_text or unit.raw_text
                loc = [asdict(unit.source_location)] if unit.source_location else []
                segments.append(
                    create_segment(
                        text=raw_or_norm,
                        seg_type=SegmentType.HEADING,
                        unit_ids=[unit.id],
                        locations=loc,
                        extra_meta={"level": unit.level},
                    )
                )
                idx += 1
                continue

            # 2. Footnote (Notas de rodapé) -> Segmento individual
            if isinstance(unit, Footnote):
                raw_or_norm = unit.normalized_text or unit.raw_text
                loc = [asdict(unit.source_location)] if unit.source_location else []
                segments.append(
                    create_segment(
                        text=raw_or_norm,
                        seg_type=SegmentType.FOOTNOTE,
                        unit_ids=[unit.id],
                        locations=loc,
                        extra_meta={
                            "marker": unit.marker,
                            "referencing_unit_id": unit.referencing_unit_id,
                        },
                    )
                )
                idx += 1
                continue

            # 3. DialogueBlock (Falas de Diálogo)
            if isinstance(unit, DialogueBlock):
                raw_or_norm = unit.normalized_text or unit.raw_text
                loc = [asdict(unit.source_location)] if unit.source_location else []
                diag_meta = {
                    "dialogue_marker": unit.dialogue_marker,
                    "speaker_hint": unit.speaker_hint,
                }
                segments.append(
                    create_segment(
                        text=raw_or_norm,
                        seg_type=SegmentType.DIALOGUE,
                        unit_ids=[unit.id],
                        locations=loc,
                        extra_meta=diag_meta,
                    )
                )
                idx += 1
                continue

            # 4. Paragraph (Parágrafos Narrativos)
            if isinstance(unit, Paragraph):
                # Verifica se podemos agrupar com parágrafos subsequentes muito curtos
                # se group_short_paragraphs estiver ativado
                if self.config.group_short_paragraphs:
                    grouped_paras: list[Paragraph] = [unit]
                    current_words = len((unit.normalized_text or unit.raw_text).split())
                    unit_is_ocr = bool(getattr(unit, "metadata", {}).get("is_ocr"))

                    next_idx = idx + 1
                    while next_idx < total_units and isinstance(reading_units[next_idx], Paragraph):
                        next_p = reading_units[next_idx]
                        next_is_ocr = bool(getattr(next_p, "metadata", {}).get("is_ocr"))
                        if unit_is_ocr != next_is_ocr:
                            # Não mistura parágrafos de OCR com parágrafos textuais puros
                            break

                        p_words = len((next_p.normalized_text or next_p.raw_text).split())

                        # Se o acúmulo ultrapassar o limite, para o agrupamento
                        if current_words + p_words > self.config.max_group_words:
                            break

                        grouped_paras.append(next_p)
                        current_words += p_words
                        next_idx += 1


                    if len(grouped_paras) > 1:
                        combined_text = "\n\n".join(
                            p.normalized_text or p.raw_text for p in grouped_paras
                        )
                        unit_ids = [p.id for p in grouped_paras]
                        locs = [
                            asdict(p.source_location) for p in grouped_paras if p.source_location
                        ]
                        segments.append(
                            create_segment(
                                text=combined_text,
                                seg_type=SegmentType.PARAGRAPH_GROUP,
                                unit_ids=unit_ids,
                                locations=locs,
                                primary_p_id=unit_ids[0],
                                section_id=grouped_paras[0].section_id,
                                extra_meta={"paragraph_count": len(grouped_paras)},
                            )
                        )
                        idx = next_idx
                        continue

                # Caso padrão: parágrafo individual
                raw_or_norm = unit.normalized_text or unit.raw_text
                loc = [asdict(unit.source_location)] if unit.source_location else []
                segments.append(
                    create_segment(
                        text=raw_or_norm,
                        seg_type=SegmentType.PARAGRAPH,
                        unit_ids=[unit.id],
                        locations=loc,
                        primary_p_id=unit.id,
                        section_id=unit.section_id,
                    )
                )
                idx += 1
                continue

            # Qualquer outro elemento gráfico / placeholder sem texto traduzível
            idx += 1

        return segments

    @staticmethod
    def verify_no_content_loss(
        chapter: Chapter,
        segments: list[Segment],
    ) -> tuple[bool, str]:
        """Garante que todo o conteúdo textual das unidades canônicas está
        presente nos segmentos.
        """
        reading_units = chapter.get_reading_sequence()

        # Coleta palavras de todas as unidades textuais do capítulo
        unit_words: list[str] = []
        for u in reading_units:
            text = getattr(u, "normalized_text", getattr(u, "raw_text", ""))
            if text and not getattr(u, "is_scene_break", False):
                unit_words.extend(text.split())

        # Coleta palavras de todos os segmentos gerados
        seg_words: list[str] = []
        for s in segments:
            seg_words.extend(s.original_text.split())

        if len(unit_words) != len(seg_words):
            return (
                False,
                f"Divergência de palavras: unidades têm {len(unit_words)} palavras "
                f"mas os segmentos possuem {len(seg_words)} palavras.",
            )

        if unit_words != seg_words:
            return (
                False,
                "A sequência exata das palavras divergiu entre unidades originais e segmentos.",
            )

        return True, "Integridade textual 100% verificada (zero perda de conteúdo)."
