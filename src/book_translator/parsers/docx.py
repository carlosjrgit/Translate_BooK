"""Parser para documentos DOCX (Office Open XML) com suporte a estilos, formatação e notas."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from book_translator.core.document import (
    Chapter,
    DialogueBlock,
    Document,
    Footnote,
    FormattingSpan,
    Heading,
    Paragraph,
    SourceLocation,
)
from book_translator.core.ids import (
    generate_chapter_id,
    generate_dialogue_id,
    generate_footnote_id,
    generate_heading_id,
    generate_paragraph_id,
)
from book_translator.errors import ParsingError
from book_translator.logging import get_logger
from book_translator.parsers.base import BaseParser
from book_translator.parsers.normalization import normalize_unicode

logger = get_logger("parsers.docx")

# Namespaces do padrão OpenXML (WordprocessingML)
NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS_DC = "{http://purl.org/dc/elements/1.1/}"


class DocxParser(BaseParser):
    """Analisador nativo de documentos DOCX baseado em descompactação ZIP e parsing de XML."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".docx",)

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        path = self.validate_source_file(file_path)

        if not zipfile.is_zipfile(path):
            logger.error(f"Arquivo DOCX não é um ZIP válido: {path}")
            raise ParsingError(f"Arquivo DOCX corrompido ou formato inválido: '{path.name}'")

        try:
            with zipfile.ZipFile(path, "r") as zf:
                namelist = zf.namelist()
                if "word/document.xml" not in namelist:
                    raise ParsingError(
                        "Estrutura DOCX corrompida (arquivo 'word/document.xml' ausente): "
                        f"'{path.name}'"
                    )

                # 1. Metadados do documento (docProps/core.xml)
                doc_title = title
                doc_author = "Desconhecido"
                if "docProps/core.xml" in namelist:
                    try:
                        core_xml = zf.read("docProps/core.xml")
                        core_root = ET.fromstring(core_xml)
                        title_el = core_root.find(f"{NS_DC}title")
                        if title_el is not None and title_el.text and not doc_title:
                            doc_title = title_el.text.strip()
                        author_el = core_root.find(f"{NS_DC}creator")
                        if author_el is not None and author_el.text:
                            doc_author = author_el.text.strip()
                    except Exception as e:
                        logger.debug(f"Aviso ao ler metadados core.xml de {path.name}: {e}")

                # 2. Notas de rodapé (word/footnotes.xml)
                footnotes_dict: dict[str, str] = {}
                if "word/footnotes.xml" in namelist:
                    try:
                        fn_xml = zf.read("word/footnotes.xml")
                        fn_root = ET.fromstring(fn_xml)
                        for fn_node in fn_root.findall(f"{NS_W}footnote"):
                            fn_id = fn_node.get(f"{NS_W}id")
                            # IDs negativos (-1, 0) são reservadas para separadores no Word
                            if fn_id and int(fn_id) > 0:
                                texts = [t.text for t in fn_node.iter(f"{NS_W}t") if t.text]
                                if texts:
                                    footnotes_dict[fn_id] = "".join(texts).strip()
                    except Exception as e:
                        logger.debug(f"Aviso ao ler footnotes.xml de {path.name}: {e}")

                # 3. Conteúdo principal (word/document.xml)
                try:
                    doc_xml = zf.read("word/document.xml")
                    doc_root = ET.fromstring(doc_xml)
                except ET.ParseError as e:
                    raise ParsingError(
                        f"Arquivo DOCX contém XML corrompido em document.xml: {e}"
                    ) from e

        except zipfile.BadZipFile as e:
            raise ParsingError(f"Arquivo DOCX corrompido ou truncado: '{path.name}'") from e
        except ParsingError:
            raise
        except Exception as e:
            raise ParsingError(f"Falha ao processar arquivo DOCX '{path.name}': {e}") from e

        doc = self.create_base_document(
            file_path=path,
            source_format="docx",
            title=doc_title,
            author=doc_author,
        )

        body = doc_root.find(f"{NS_W}body")
        if body is None:
            raise ParsingError(
                f"Estrutura DOCX inválida (elemento <w:body> ausente): '{path.name}'"
            )

        chapters: list[Chapter] = []
        current_ch_order = 1
        current_ch_title = "Capítulo 1"
        current_ch_id = generate_chapter_id(doc.id, current_ch_order)
        current_chapter = Chapter(
            id=current_ch_id,
            title=current_ch_title,
            order=current_ch_order,
            reading_order=current_ch_order,
        )

        reading_order = 1
        h_idx = 1
        p_idx = 1
        diag_idx = 1
        fn_idx = 1
        first_h1 = True

        def start_new_chapter(new_title: str) -> None:
            nonlocal current_ch_order, current_ch_title, current_ch_id, current_chapter
            nonlocal reading_order, h_idx, p_idx, diag_idx, fn_idx

            has_content = (
                current_chapter.headings
                or current_chapter.paragraphs
                or current_chapter.dialogue_blocks
            )
            if has_content:
                chapters.append(current_chapter)

            current_ch_order += 1
            current_ch_title = new_title
            current_ch_id = generate_chapter_id(doc.id, current_ch_order)
            current_chapter = Chapter(
                id=current_ch_id,
                title=current_ch_title,
                order=current_ch_order,
                reading_order=current_ch_order,
            )
            reading_order = 1
            h_idx = 1
            p_idx = 1
            diag_idx = 1
            fn_idx = 1

        for p_elem in body.findall(f"{NS_W}p"):
            # Verifica estilo do parágrafo
            p_style = ""
            p_pr = p_elem.find(f"{NS_W}pPr")
            if p_pr is not None:
                style_el = p_pr.find(f"{NS_W}pStyle")
                if style_el is not None:
                    p_style = style_el.get(f"{NS_W}val", "")

            # Itera runs de texto (<w:r>) acumulando texto e formatações
            parts: list[str] = []
            spans: list[FormattingSpan] = []
            referenced_fn_ids: list[str] = []
            curr_pos = 0

            for child in p_elem:
                if child.tag == f"{NS_W}r":
                    r_pr = child.find(f"{NS_W}rPr")
                    is_bold = r_pr is not None and (
                        r_pr.find(f"{NS_W}b") is not None or r_pr.find(f"{NS_W}bCs") is not None
                    )
                    is_italic = r_pr is not None and (
                        r_pr.find(f"{NS_W}i") is not None or r_pr.find(f"{NS_W}iCs") is not None
                    )
                    is_underline = r_pr is not None and r_pr.find(f"{NS_W}u") is not None
                    is_strike = r_pr is not None and (
                        r_pr.find(f"{NS_W}strike") is not None
                        or r_pr.find(f"{NS_W}dstrike") is not None
                    )

                    # Verifica se há referência a nota de rodapé
                    fn_ref = child.find(f"{NS_W}footnoteReference")
                    if fn_ref is not None:
                        ref_id = fn_ref.get(f"{NS_W}id")
                        if ref_id and ref_id in footnotes_dict:
                            referenced_fn_ids.append(ref_id)

                    run_texts = [t.text for t in child.findall(f"{NS_W}t") if t.text]
                    run_text = "".join(run_texts)
                    if run_text:
                        start_pos = curr_pos
                        parts.append(run_text)
                        curr_pos += len(run_text)

                        if is_bold:
                            spans.append(FormattingSpan(start_pos, curr_pos, "bold"))
                        if is_italic:
                            spans.append(FormattingSpan(start_pos, curr_pos, "italic"))
                        if is_underline:
                            spans.append(FormattingSpan(start_pos, curr_pos, "underline"))
                        if is_strike:
                            spans.append(FormattingSpan(start_pos, curr_pos, "strikethrough"))

            full_text = "".join(parts).strip()
            if not full_text:
                continue

            full_norm = normalize_unicode(full_text)

            # Verifica se o estilo indica Heading
            is_heading = False
            heading_level = 1
            lower_style = p_style.lower()
            if "heading" in lower_style or "titulo" in lower_style or "title" in lower_style:
                is_heading = True
                for char in lower_style:
                    if char in "123456":
                        heading_level = int(char)
                        break

            if is_heading:
                if heading_level == 1:
                    if first_h1:
                        current_ch_title = full_norm
                        current_chapter.title = full_norm
                        first_h1 = False
                    else:
                        start_new_chapter(full_norm)

                heading_obj = Heading(
                    id=generate_heading_id(current_ch_id, h_idx),
                    chapter_id=current_ch_id,
                    level=heading_level,
                    raw_text=full_norm,
                    normalized_text=full_norm,
                    reading_order=reading_order,
                    spans=spans,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.headings.append(heading_obj)
                reading_order += 1
                h_idx += 1
                continue

            # Diálogo ou Parágrafo comum
            is_diag, marker, clean_diag = self.identify_dialogue(full_norm)
            unit_id: str
            if is_diag:
                unit_id = generate_dialogue_id(current_ch_id, diag_idx)
                diag_obj = DialogueBlock(
                    id=unit_id,
                    chapter_id=current_ch_id,
                    reading_order=reading_order,
                    raw_text=full_norm,
                    normalized_text=clean_diag,
                    dialogue_marker=marker,
                    spans=spans,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.dialogue_blocks.append(diag_obj)
                diag_idx += 1
            else:
                unit_id = generate_paragraph_id(current_ch_id, p_idx)
                para_obj = Paragraph(
                    id=unit_id,
                    chapter_id=current_ch_id,
                    reading_order=reading_order,
                    raw_text=full_norm,
                    normalized_text=full_norm,
                    spans=spans,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.paragraphs.append(para_obj)
                p_idx += 1

            reading_order += 1

            # Processa notas de rodapé referenciadas nesta unidade
            for fn_id in referenced_fn_ids:
                fn_text = normalize_unicode(footnotes_dict[fn_id])
                fn_obj = Footnote(
                    id=generate_footnote_id(current_ch_id, fn_idx),
                    chapter_id=current_ch_id,
                    marker=fn_id,
                    referencing_unit_id=unit_id,
                    raw_text=fn_text,
                    normalized_text=fn_text,
                    reading_order=reading_order,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.footnotes.append(fn_obj)
                reading_order += 1
                fn_idx += 1

        has_content = (
            current_chapter.headings
            or current_chapter.paragraphs
            or current_chapter.dialogue_blocks
        )
        if has_content:
            chapters.append(current_chapter)

        if not chapters:
            raise ParsingError(
                f"Nenhum conteúdo textual estruturado pôde ser extraído de '{path.name}'."
            )

        doc.chapters = chapters
        return doc
