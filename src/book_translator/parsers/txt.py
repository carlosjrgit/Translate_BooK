"""Parser para arquivos de texto simples (TXT)."""

from __future__ import annotations

import re
from pathlib import Path

from book_translator.core.document import (
    Chapter,
    DialogueBlock,
    Document,
    Heading,
    Paragraph,
    SourceLocation,
)
from book_translator.core.ids import (
    generate_chapter_id,
    generate_dialogue_id,
    generate_heading_id,
    generate_paragraph_id,
)
from book_translator.errors import ParsingError
from book_translator.logging import get_logger
from book_translator.parsers.base import BaseParser
from book_translator.parsers.normalization import detect_encoding, normalize_unicode

logger = get_logger("parsers.txt")

CHAPTER_PATTERN = re.compile(
    r"^(?:CHAPTER|CAPÍTULO|PARTE|ACT|SCENE)\s+([0-9IVXLCDM]+|[A-Z]+)(?:\s*[:.\-—]\s*(.*))?$",
    re.IGNORECASE,
)


class TxtParser(BaseParser):
    """Analisador de arquivos TXT com detecção de encoding, capítulos e diálogos."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".txt", ".text")

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        path = self.validate_source_file(file_path)

        try:
            raw_bytes = path.read_bytes()
        except OSError as e:
            raise ParsingError(f"Erro ao ler arquivo TXT '{path}': {e}") from e

        encoding = detect_encoding(raw_bytes)
        logger.info(f"Processando '{path.name}' com encoding detectado '{encoding}'")

        try:
            raw_text = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError) as e:
            logger.warning(
                f"Falha ao decodificar com {encoding}, tentando utf-8 com substituição: {e}"
            )
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        norm_text = normalize_unicode(raw_text)
        if not norm_text.strip():
            raise ParsingError(f"O arquivo TXT '{path.name}' está vazio ou contém apenas espaços.")

        doc = self.create_base_document(
            file_path=path,
            source_format="txt",
            title=title,
        )

        lines = norm_text.split("\n")
        chapters: list[Chapter] = []

        # Identifica seções ou capítulos
        current_chapter_num = 1
        current_chapter_title = "Capítulo 1"
        current_chapter_id = generate_chapter_id(doc.id, current_chapter_num)
        current_lines: list[tuple[int, str]] = []  # (line_no, line_content)

        def flush_chapter(
            ch_num: int,
            ch_title: str,
            ch_id: str,
            content_lines: list[tuple[int, str]],
        ) -> Chapter | None:
            if not content_lines:
                return None

            chapter = Chapter(
                id=ch_id,
                title=ch_title,
                order=ch_num,
                reading_order=ch_num,
            )

            reading_order = 1
            h_idx = 1
            p_idx = 1
            diag_idx = 1

            # Cabeçalho do capítulo
            heading_loc = SourceLocation(
                file_path=str(path.name),
                line_number=content_lines[0][0] if content_lines else 1,
            )
            ch_heading = Heading(
                id=generate_heading_id(ch_id, h_idx),
                chapter_id=ch_id,
                level=1,
                raw_text=ch_title,
                normalized_text=ch_title,
                reading_order=reading_order,
                source_location=heading_loc,
            )
            chapter.headings.append(ch_heading)
            reading_order += 1
            h_idx += 1

            # Agrupa linhas em parágrafos separados por linhas em branco
            current_p_lines: list[str] = []
            p_start_line = content_lines[0][0]

            for line_no, line in content_lines:
                stripped = line.strip()
                if not stripped:
                    if current_p_lines:
                        para_raw = "\n".join(current_p_lines)
                        para_norm = " ".join(
                            line_part.strip() for line_part in current_p_lines if line_part.strip()
                        )
                        loc = SourceLocation(file_path=str(path.name), line_number=p_start_line)

                        is_diag, marker, clean_diag = self.identify_dialogue(para_norm)
                        if is_diag:
                            chapter.dialogue_blocks.append(
                                DialogueBlock(
                                    id=generate_dialogue_id(ch_id, diag_idx),
                                    chapter_id=ch_id,
                                    reading_order=reading_order,
                                    raw_text=para_raw,
                                    normalized_text=clean_diag,
                                    dialogue_marker=marker,
                                    source_location=loc,
                                )
                            )
                            diag_idx += 1
                        else:
                            chapter.paragraphs.append(
                                Paragraph(
                                    id=generate_paragraph_id(ch_id, p_idx),
                                    chapter_id=ch_id,
                                    reading_order=reading_order,
                                    raw_text=para_raw,
                                    normalized_text=para_norm,
                                    source_location=loc,
                                )
                            )
                            p_idx += 1

                        reading_order += 1
                        current_p_lines = []
                    continue

                if not current_p_lines:
                    p_start_line = line_no
                current_p_lines.append(line)

            # Flush do último parágrafo
            if current_p_lines:
                para_raw = "\n".join(current_p_lines)
                para_norm = " ".join(
                    line_part.strip() for line_part in current_p_lines if line_part.strip()
                )
                loc = SourceLocation(file_path=str(path.name), line_number=p_start_line)
                is_diag, marker, clean_diag = self.identify_dialogue(para_norm)
                if is_diag:
                    chapter.dialogue_blocks.append(
                        DialogueBlock(
                            id=generate_dialogue_id(ch_id, diag_idx),
                            chapter_id=ch_id,
                            reading_order=reading_order,
                            raw_text=para_raw,
                            normalized_text=clean_diag,
                            dialogue_marker=marker,
                            source_location=loc,
                        )
                    )
                else:
                    chapter.paragraphs.append(
                        Paragraph(
                            id=generate_paragraph_id(ch_id, p_idx),
                            chapter_id=ch_id,
                            reading_order=reading_order,
                            raw_text=para_raw,
                            normalized_text=para_norm,
                            source_location=loc,
                        )
                    )

            return chapter

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            ch_match = CHAPTER_PATTERN.match(stripped)
            if ch_match and idx > 1:  # Início de um novo capítulo
                # Salva capítulo anterior
                ch_obj = flush_chapter(
                    current_chapter_num,
                    current_chapter_title,
                    current_chapter_id,
                    current_lines,
                )
                if ch_obj:
                    chapters.append(ch_obj)

                current_chapter_num += 1
                current_chapter_title = stripped
                current_chapter_id = generate_chapter_id(doc.id, current_chapter_num)
                current_lines = []
            elif ch_match and idx == 1:
                # Primeiro capítulo já começa na primeira linha
                current_chapter_title = stripped
            else:
                current_lines.append((idx, line))

        # Salva o último capítulo acumulado
        ch_obj = flush_chapter(
            current_chapter_num,
            current_chapter_title,
            current_chapter_id,
            current_lines,
        )
        if ch_obj:
            chapters.append(ch_obj)

        if not chapters:
            raise ParsingError(f"Nenhum conteúdo estruturado pôde ser extraído de '{path.name}'.")

        doc.chapters = chapters
        return doc
