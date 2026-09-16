"""Parser para arquivos Markdown (MD) com extração precisa de tokens e spans de formatação."""

from __future__ import annotations

import re
from pathlib import Path

from markdown_it import MarkdownIt

from book_translator.core.document import (
    Chapter,
    DialogueBlock,
    Document,
    Footnote,
    FormattingSpan,
    Heading,
    ImagePlaceholder,
    Paragraph,
    SourceLocation,
)
from book_translator.core.ids import (
    generate_chapter_id,
    generate_dialogue_id,
    generate_footnote_id,
    generate_heading_id,
    generate_image_id,
    generate_paragraph_id,
)
from book_translator.errors import ParsingError
from book_translator.logging import get_logger
from book_translator.parsers.base import BaseParser
from book_translator.parsers.normalization import detect_encoding, normalize_unicode

logger = get_logger("parsers.markdown")

FOOTNOTE_DEF_REGEX = re.compile(r"^\[\^([a-zA-Z0-9_\-]+)\]:\s*(.*)$")


class MarkdownParser(BaseParser):
    """Analisador de arquivos Markdown com preservação de estrutura, spans e diálogos."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".md", ".markdown", ".mdown", ".mkd")

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        path = self.validate_source_file(file_path)

        try:
            raw_bytes = path.read_bytes()
        except OSError as e:
            raise ParsingError(f"Erro ao ler arquivo Markdown '{path}': {e}") from e

        encoding = detect_encoding(raw_bytes)
        try:
            raw_text = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        norm_text = normalize_unicode(raw_text)
        if not norm_text.strip():
            raise ParsingError(f"O arquivo Markdown '{path.name}' está vazio.")

        doc = self.create_base_document(
            file_path=path,
            source_format="markdown",
            title=title,
        )

        md = MarkdownIt("commonmark", {"breaks": True, "html": True})
        tokens = md.parse(norm_text)

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
        img_idx = 1

        def start_new_chapter(new_title: str) -> None:
            nonlocal current_ch_order, current_ch_title, current_ch_id, current_chapter
            nonlocal reading_order, h_idx, p_idx, diag_idx, fn_idx, img_idx

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
            img_idx = 1

        def process_inline(inline_token) -> tuple[str, list[FormattingSpan], list[dict]]:
            active: dict[str, int] = {}
            parts: list[str] = []
            curr_pos = 0
            spans: list[FormattingSpan] = []
            extracted_imgs: list[dict] = []

            if not inline_token or not inline_token.children:
                return "", spans, extracted_imgs

            for child in inline_token.children:
                if child.type == "text":
                    parts.append(child.content)
                    curr_pos += len(child.content)
                elif child.type == "code_inline":
                    start = curr_pos
                    parts.append(child.content)
                    curr_pos += len(child.content)
                    spans.append(FormattingSpan(start=start, end=curr_pos, style="code"))
                elif child.type == "strong_open":
                    active["bold"] = curr_pos
                elif child.type == "strong_close":
                    if "bold" in active:
                        s_idx = active.pop("bold")
                        if curr_pos > s_idx:
                            spans.append(FormattingSpan(start=s_idx, end=curr_pos, style="bold"))
                elif child.type == "em_open":
                    active["italic"] = curr_pos
                elif child.type == "em_close":
                    if "italic" in active:
                        s_idx = active.pop("italic")
                        if curr_pos > s_idx:
                            spans.append(FormattingSpan(start=s_idx, end=curr_pos, style="italic"))
                elif child.type == "s_open":
                    active["strikethrough"] = curr_pos
                elif child.type == "s_close":
                    if "strikethrough" in active:
                        s_idx = active.pop("strikethrough")
                        if curr_pos > s_idx:
                            spans.append(
                                FormattingSpan(start=s_idx, end=curr_pos, style="strikethrough")
                            )
                elif child.type == "link_open":
                    active["link"] = curr_pos
                elif child.type == "link_close":
                    if "link" in active:
                        s_idx = active.pop("link")
                        if curr_pos > s_idx:
                            spans.append(FormattingSpan(start=s_idx, end=curr_pos, style="link"))
                elif child.type == "image":
                    src = child.attrs.get("src", "") if child.attrs else ""
                    alt = child.content or ""
                    extracted_imgs.append({"src": src, "alt": alt})
                elif child.type in ("softbreak", "hardbreak"):
                    parts.append(" ")
                    curr_pos += 1

            full_text = "".join(parts)
            return full_text, spans, extracted_imgs

        i = 0
        n_tokens = len(tokens)
        first_heading = True

        while i < n_tokens:
            tok = tokens[i]

            # 1. Headings (h1 a h6)
            if tok.type == "heading_open":
                level = int(tok.tag[1:]) if len(tok.tag) > 1 and tok.tag[1:].isdigit() else 1
                line_no = tok.map[0] + 1 if tok.map else 1
                i += 1
                inline_tok = tokens[i] if i < n_tokens and tokens[i].type == "inline" else None
                h_text, h_spans, _ = process_inline(inline_tok)

                if level == 1:
                    if first_heading:
                        current_ch_title = h_text or "Capítulo 1"
                        current_chapter.title = current_ch_title
                        first_heading = False
                    else:
                        start_new_chapter(h_text or f"Capítulo {current_ch_order + 1}")

                loc = SourceLocation(file_path=str(path.name), line_number=line_no)
                heading = Heading(
                    id=generate_heading_id(current_ch_id, h_idx),
                    chapter_id=current_ch_id,
                    level=level,
                    raw_text=h_text,
                    normalized_text=h_text,
                    reading_order=reading_order,
                    spans=h_spans,
                    source_location=loc,
                )
                current_chapter.headings.append(heading)
                reading_order += 1
                h_idx += 1

                while i < n_tokens and tokens[i].type != "heading_close":
                    i += 1

            # 2. Paragraphs e List Items
            elif tok.type in ("paragraph_open", "list_item_open"):
                line_no = tok.map[0] + 1 if tok.map else 1
                close_type = (
                    "paragraph_close" if tok.type == "paragraph_open" else "list_item_close"
                )
                i += 1
                # Avança até encontrar o token inline
                while i < n_tokens and tokens[i].type != "inline" and tokens[i].type != close_type:
                    i += 1

                if i < n_tokens and tokens[i].type == "inline":
                    p_text, p_spans, p_imgs = process_inline(tokens[i])

                    # Processa imagens inline encontradas
                    for img_dict in p_imgs:
                        loc_img = SourceLocation(file_path=str(path.name), line_number=line_no)
                        img_obj = ImagePlaceholder(
                            id=generate_image_id(current_ch_id, img_idx),
                            chapter_id=current_ch_id,
                            reading_order=reading_order,
                            caption_raw=img_dict["alt"],
                            caption_normalized=img_dict["alt"],
                            alt_text=img_dict["alt"],
                            original_src=img_dict["src"],
                            source_location=loc_img,
                        )
                        current_chapter.image_placeholders.append(img_obj)
                        reading_order += 1
                        img_idx += 1

                    if p_text.strip():
                        # Checa nota de rodapé com sintaxe [^key]: nota
                        fn_match = FOOTNOTE_DEF_REGEX.match(p_text.strip())
                        if fn_match:
                            marker = fn_match.group(1)
                            fn_text = fn_match.group(2).strip()
                            loc_fn = SourceLocation(file_path=str(path.name), line_number=line_no)
                            fn_obj = Footnote(
                                id=generate_footnote_id(current_ch_id, fn_idx),
                                chapter_id=current_ch_id,
                                marker=marker,
                                raw_text=p_text,
                                normalized_text=fn_text,
                                reading_order=reading_order,
                                source_location=loc_fn,
                            )
                            current_chapter.footnotes.append(fn_obj)
                            reading_order += 1
                            fn_idx += 1
                        else:
                            loc = SourceLocation(file_path=str(path.name), line_number=line_no)
                            is_diag, marker, clean_diag = self.identify_dialogue(p_text)
                            if is_diag:
                                diag_obj = DialogueBlock(
                                    id=generate_dialogue_id(current_ch_id, diag_idx),
                                    chapter_id=current_ch_id,
                                    reading_order=reading_order,
                                    raw_text=p_text,
                                    normalized_text=clean_diag,
                                    dialogue_marker=marker,
                                    spans=p_spans,
                                    source_location=loc,
                                )
                                current_chapter.dialogue_blocks.append(diag_obj)
                                diag_idx += 1
                            else:
                                para_obj = Paragraph(
                                    id=generate_paragraph_id(current_ch_id, p_idx),
                                    chapter_id=current_ch_id,
                                    reading_order=reading_order,
                                    raw_text=p_text,
                                    normalized_text=p_text,
                                    spans=p_spans,
                                    source_location=loc,
                                )
                                current_chapter.paragraphs.append(para_obj)
                                p_idx += 1
                            reading_order += 1

                while i < n_tokens and tokens[i].type != close_type:
                    i += 1

            i += 1

        has_content = (
            current_chapter.headings
            or current_chapter.paragraphs
            or current_chapter.dialogue_blocks
        )
        if has_content:
            chapters.append(current_chapter)

        if not chapters:
            raise ParsingError(f"Nenhum conteúdo estruturado pôde ser extraído de '{path.name}'.")

        doc.chapters = chapters
        return doc
