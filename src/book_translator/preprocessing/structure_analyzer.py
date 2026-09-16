"""Análise de estrutura, detecção hierárquica de títulos, capítulos e seções."""

from __future__ import annotations

import re

from book_translator.core.ids import generate_chapter_id, generate_heading_id, generate_section_id
from book_translator.core.models import Chapter, Heading, Section, SourceLocation
from book_translator.preprocessing.config import PreprocessingConfig
from book_translator.preprocessing.paragraph_reconstructor import ReconstructedBlock


class StructureAnalyzer:
    """Detecta títulos, capítulos e seções estruturais na narrativa."""

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        self.config = config or PreprocessingConfig()
        self._compiled_chapter_regex = [
            re.compile(p, re.IGNORECASE) for p in self.config.chapter_regex_patterns
        ]

    def is_chapter_heading(self, text: str) -> tuple[bool, str]:
        """Verifica se o texto corresponde a um cabeçalho de capítulo.

        Retorna:
            (is_chapter, clean_title)
        """
        trimmed = text.strip()
        if not trimmed or len(trimmed) > self.config.max_heading_length:
            return False, ""

        for regex in self._compiled_chapter_regex:
            match = regex.match(trimmed)
            if match:
                return True, trimmed

        # Heurística: Linhas curtas em caixa alta que comecem com números romanos ou arábicos
        if (
            len(trimmed) < 40
            and trimmed.isupper()
            and re.match(r"^(?:[0-9]+|[IVXLCDM]+)\.?\s+[A-Z\s]+$", trimmed)
        ):
            return True, trimmed

        return False, ""

    def is_section_heading(self, text: str) -> tuple[bool, int]:
        """Verifica se o texto parece ser um subtítulo ou seção intermediária.

        Retorna:
            (is_section, level)
        """
        trimmed = text.strip()
        if not trimmed or len(trimmed) > 80:
            return False, 0

        # Termina com pontuação típica de frase? Se sim, não é heading
        if trimmed.endswith((".", "!", "?", ":", ";", "—", "-")):
            return False, 0

        # Padrões do tipo "1.1 Introdução" ou "Section 2"
        if re.match(r"^(?:Section|Seção)\s+[0-9IVXLCDM]+", trimmed, re.IGNORECASE):
            return True, 2

        if re.match(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?\s+[A-Za-z]", trimmed):
            return True, 3

        # Linha curta em Title Case ou ALL CAPS com poucas palavras (<= 6)
        words = trimmed.split()
        if 1 <= len(words) <= 6:
            if trimmed.isupper() and len(trimmed) < 50:
                return True, 2
            if all(w[0].isupper() for w in words if len(w) > 3):
                return True, 3

        return False, 0

    def structure_blocks(
        self,
        blocks: list[ReconstructedBlock],
        source_file_path: str = "",
    ) -> list[Chapter]:
        """Agrupa blocos reconstruídos em capítulos e seções organizados."""
        chapters: list[Chapter] = []

        current_chapter: Chapter | None = None
        current_section: Section | None = None
        current_reading_order = 1

        def start_new_chapter(title: str, line_num: int) -> Chapter:
            nonlocal current_reading_order, current_section
            ch_idx = len(chapters) + 1
            ch_id = generate_chapter_id(ch_idx)
            new_ch = Chapter(id=ch_id, title=title, order=ch_idx, reading_order=ch_idx)
            current_reading_order = 1
            current_section = None

            # Adiciona o Heading correspondente ao capítulo
            h_id = generate_heading_id(ch_id, 1)
            new_ch.headings.append(
                Heading(
                    id=h_id,
                    chapter_id=ch_id,
                    level=1,
                    raw_text=title,
                    normalized_text=title,
                    reading_order=current_reading_order,
                    source_location=SourceLocation(
                        file_path=source_file_path, line_number=line_num
                    ),
                )
            )
            current_reading_order += 1
            return new_ch

        for block in blocks:
            # 1. Verifica se é início de um novo capítulo
            is_ch, ch_title = self.is_chapter_heading(block.text)
            if is_ch:
                if current_chapter is not None:
                    chapters.append(current_chapter)
                current_chapter = start_new_chapter(ch_title, block.original_line_start)
                continue

            # Se ainda não temos um capítulo aberto, cria o capítulo padrão inicial
            if current_chapter is None:
                current_chapter = start_new_chapter("Chapter 1", block.original_line_start)

            # 2. Verifica se é uma quebra de cena
            if block.is_scene_break:
                # Registra como separador estrutural de seção
                sec_idx = len(current_chapter.sections) + 1
                sec_id = generate_section_id(current_chapter.id, sec_idx)
                current_section = Section(
                    id=sec_id,
                    chapter_id=current_chapter.id,
                    title=block.scene_marker or "* * *",
                    reading_order=current_reading_order,
                    order_index=sec_idx,
                )
                current_chapter.sections.append(current_section)
                continue

            # 3. Verifica se é subtítulo / heading intermediário
            is_sec, level = self.is_section_heading(block.text)
            if is_sec:
                h_idx = len(current_chapter.headings) + 1
                h_id = generate_heading_id(current_chapter.id, h_idx)
                current_chapter.headings.append(
                    Heading(
                        id=h_id,
                        chapter_id=current_chapter.id,
                        level=level,
                        raw_text=block.text,
                        normalized_text=block.text,
                        reading_order=current_reading_order,
                        source_location=SourceLocation(
                            file_path=source_file_path,
                            line_number=block.original_line_start,
                        ),
                    )
                )
                current_reading_order += 1

                sec_idx = len(current_chapter.sections) + 1
                sec_id = generate_section_id(current_chapter.id, sec_idx)
                current_section = Section(
                    id=sec_id,
                    chapter_id=current_chapter.id,
                    title=block.text,
                    reading_order=current_reading_order,
                    order_index=sec_idx,
                )
                current_chapter.sections.append(current_section)
                continue

            # 4. Parágrafo comum (será classificado em diálogo ou prosa nas próximas etapas)
            # Associamos temporariamente no bloco os metadados de seção corrente
            if current_section:
                block.metadata["section_id"] = current_section.id
            block.metadata["reading_order"] = str(current_reading_order)
            current_reading_order += 1

        if current_chapter is not None:
            chapters.append(current_chapter)

        return chapters
