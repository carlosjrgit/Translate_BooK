"""Pipeline unificado de pré-processamento editorial e segmentação inicial."""

from __future__ import annotations

from book_translator.core.document import Document, DocumentMetadata
from book_translator.core.ids import (
    generate_dialogue_id,
    generate_document_id,
    generate_paragraph_id,
)
from book_translator.core.models import DialogueBlock, Paragraph, SourceLocation
from book_translator.logging import get_logger
from book_translator.preprocessing.config import PreprocessingConfig
from book_translator.preprocessing.dehyphenator import Dehyphenator
from book_translator.preprocessing.dialogue_detector import DialogueDetector
from book_translator.preprocessing.normalizer import UnicodeNormalizer
from book_translator.preprocessing.paragraph_reconstructor import ParagraphReconstructor
from book_translator.preprocessing.repetition_detector import RepetitionDetector
from book_translator.preprocessing.segmenter import InitialSegmenter
from book_translator.preprocessing.structure_analyzer import StructureAnalyzer

logger = get_logger("preprocessing.pipeline")


class PreprocessingPipeline:
    """Orquestrador completo de pré-processamento editorial e segmentação inicial."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()
        self.normalizer = UnicodeNormalizer(self.config)
        self.dehyphenator = Dehyphenator(self.config)
        self.reconstructor = ParagraphReconstructor(self.config)
        self.structure_analyzer = StructureAnalyzer(self.config)
        self.dialogue_detector = DialogueDetector(self.config)
        self.repetition_detector = RepetitionDetector(self.config)
        self.segmenter = InitialSegmenter(self.config)

    def process_document(self, document: Document) -> Document:
        """Aplica normalização e segmentação a um Document já previamente parseado."""
        logger.info(f"Iniciando pré-processamento do documento: '{document.title}'")

        for chapter in document.chapters:
            # 1. Normaliza Headings
            for h in chapter.headings:
                h.normalized_text = self.normalizer.normalize(
                    self.dehyphenator.dehyphenate(h.normalized_text or h.raw_text)
                )

            # 2. Normaliza e refina Parágrafos e Diálogos
            new_paragraphs: list[Paragraph] = []
            for p in chapter.paragraphs:
                cleaned_text = self.normalizer.normalize(
                    self.dehyphenator.dehyphenate(p.normalized_text or p.raw_text)
                )
                p.normalized_text = cleaned_text

                # Verifica se o parágrafo na verdade é um diálogo ainda não classificado
                if self.config.detect_dialogues:
                    is_diag, marker, diag_text, speaker = self.dialogue_detector.analyze_dialogue(
                        cleaned_text
                    )
                    if is_diag:
                        d_id = generate_dialogue_id(chapter.id, len(chapter.dialogue_blocks) + 1)
                        d_block = DialogueBlock(
                            id=d_id,
                            chapter_id=chapter.id,
                            dialogue_marker=marker,
                            speaker_hint=speaker,
                            raw_text=p.raw_text,
                            normalized_text=cleaned_text,
                            reading_order=p.reading_order,
                            spans=p.spans,
                            source_location=p.source_location,
                            metadata=p.metadata,
                        )
                        chapter.dialogue_blocks.append(d_block)
                        continue

                new_paragraphs.append(p)
            chapter.paragraphs = new_paragraphs

            # 3. Normaliza Diálogos existentes
            for d in chapter.dialogue_blocks:
                cleaned_text = self.normalizer.normalize(
                    self.dehyphenator.dehyphenate(d.normalized_text or d.raw_text)
                )
                d.normalized_text = cleaned_text
                if not d.speaker_hint and self.config.extract_speaker_hints:
                    d.speaker_hint = self.dialogue_detector.extract_speaker_hint(cleaned_text)

            # 4. Normaliza Footnotes
            for fn in chapter.footnotes:
                fn.normalized_text = self.normalizer.normalize(
                    self.dehyphenator.dehyphenate(fn.normalized_text or fn.raw_text)
                )

            # 5. Gera a lista canônica e ordenada de segmentos do capítulo
            chapter.segments = self.segmenter.segment_chapter(chapter)

            # 6. Validação estrita de integridade textual
            valid, msg = self.segmenter.verify_no_content_loss(chapter, chapter.segments)
            if not valid:
                logger.warning(f"Alerta de integridade no capítulo '{chapter.title}': {msg}")

        document.metadata.extra["preprocessed"] = True
        logger.info(
            f"Pré-processamento concluído para '{document.title}'. "
            f"Capítulos: {len(document.chapters)} | "
            f"Total de segmentos: {sum(len(c.segments) for c in document.chapters)}"
        )
        return document

    def process_text(
        self,
        raw_text: str,
        title: str = "Untitled",
        author: str = "Desconhecido",
    ) -> Document:
        """Cria e estrutura um Document completo diretamente a partir de texto bruto."""
        # 1. Normalização Unicode inicial
        norm_text = self.normalizer.normalize(raw_text)

        # 2. Des-hifenização
        dehyphenated = self.dehyphenator.dehyphenate(norm_text)

        # 3. Reconstrução de parágrafos e detecção de quebras de cena
        blocks = self.reconstructor.reconstruct(dehyphenated)

        # 4. Estruturação em capítulos e seções
        chapters = self.structure_analyzer.structure_blocks(blocks)

        # 5. Classificação em parágrafos e diálogos para cada capítulo
        for ch in chapters:
            reading_order = 2  # 1 foi o Heading do capítulo
            # Filtra os blocos pertencentes conceitualmente a este capítulo
            for block in blocks:
                if (
                    block.is_scene_break
                    or self.structure_analyzer.is_chapter_heading(block.text)[0]
                ):
                    continue

                if self.config.detect_dialogues:
                    is_diag, marker, clean_text, speaker = self.dialogue_detector.analyze_dialogue(
                        block.text
                    )
                    if is_diag:
                        d_id = generate_dialogue_id(ch.id, len(ch.dialogue_blocks) + 1)
                        ch.dialogue_blocks.append(
                            DialogueBlock(
                                id=d_id,
                                chapter_id=ch.id,
                                dialogue_marker=marker,
                                speaker_hint=speaker,
                                raw_text=block.text,
                                normalized_text=clean_text,
                                reading_order=reading_order,
                                source_location=SourceLocation(
                                    line_number=block.original_line_start
                                ),
                            )
                        )
                        reading_order += 1
                        continue

                p_id = generate_paragraph_id(ch.id, len(ch.paragraphs) + 1)
                ch.paragraphs.append(
                    Paragraph(
                        id=p_id,
                        chapter_id=ch.id,
                        raw_text=block.text,
                        normalized_text=block.text,
                        reading_order=reading_order,
                        source_location=SourceLocation(line_number=block.original_line_start),
                    )
                )
                reading_order += 1

            # 6. Segmenta o capítulo
            ch.segments = self.segmenter.segment_chapter(ch)

        doc_id = generate_document_id(title)
        metadata = DocumentMetadata(
            title=title,
            author=author,
            source_format="txt",
            extra={"preprocessed": True},
        )
        return Document(id=doc_id, metadata=metadata, chapters=chapters)
