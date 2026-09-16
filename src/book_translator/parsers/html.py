"""Parser para arquivos HTML com suporte a marcação malformada, spans e notas."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

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

logger = get_logger("parsers.html")

INLINE_TAG_MAP = {
    "i": "italic",
    "em": "italic",
    "b": "bold",
    "strong": "bold",
    "u": "underline",
    "s": "strikethrough",
    "strike": "strikethrough",
    "del": "strikethrough",
    "code": "code",
    "a": "link",
}


class HtmlParser(BaseParser):
    """Analisador de arquivos HTML tolerante a erros e com preservação de estrutura."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".html", ".htm", ".xhtml")

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        path = self.validate_source_file(file_path)

        try:
            raw_bytes = path.read_bytes()
        except OSError as e:
            raise ParsingError(f"Erro ao ler arquivo HTML '{path}': {e}") from e

        encoding = detect_encoding(raw_bytes)
        try:
            raw_html = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            raw_html = raw_bytes.decode("utf-8", errors="replace")

        norm_html = normalize_unicode(raw_html)
        if not norm_html.strip():
            raise ParsingError(f"O arquivo HTML '{path.name}' está vazio.")

        # BeautifulSoup com o parser padrão 'html.parser' repara tags malformadas automaticamente
        soup = BeautifulSoup(norm_html, "html.parser")

        # Metadados
        extracted_title = title
        if not extracted_title and soup.title and soup.title.string:
            extracted_title = soup.title.string.strip()

        extracted_author = "Desconhecido"
        author_meta = soup.find("meta", attrs={"name": "author"})
        if author_meta and isinstance(author_meta, Tag) and author_meta.get("content"):
            extracted_author = str(author_meta["content"]).strip()

        doc = self.create_base_document(
            file_path=path,
            source_format="html",
            title=extracted_title,
            author=extracted_author,
        )

        root = soup.body if soup.body else soup

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

        def extract_text_and_spans(node: Tag) -> tuple[str, list[FormattingSpan]]:
            parts: list[str] = []
            spans: list[FormattingSpan] = []
            curr_pos = 0

            def recurse(current_node):
                nonlocal curr_pos
                if isinstance(current_node, NavigableString):
                    t = str(current_node)
                    if t:
                        parts.append(t)
                        curr_pos += len(t)
                    return

                tag_name = current_node.name.lower() if current_node.name else ""
                style = INLINE_TAG_MAP.get(tag_name)
                start_pos = curr_pos

                for child in current_node.children:
                    recurse(child)

                if style and curr_pos > start_pos:
                    spans.append(FormattingSpan(start=start_pos, end=curr_pos, style=style))

            recurse(node)
            full_text = "".join(parts).strip()
            return full_text, spans

        first_h1 = True
        # Itera nós blocos relevantes no body
        for elem in root.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "img", "aside"],
            recursive=True,
        ):
            # Ignora nós que já estejam dentro de outro bloco já processado (evita duplicação)
            if elem.parent and elem.parent.name in ("p", "li", "blockquote", "aside"):
                continue

            tag_name = elem.name.lower()

            # 1. Imagem
            if tag_name == "img":
                src = elem.get("src", "")
                alt = elem.get("alt", "")
                img_obj = ImagePlaceholder(
                    id=generate_image_id(current_ch_id, img_idx),
                    chapter_id=current_ch_id,
                    reading_order=reading_order,
                    caption_raw=alt,
                    caption_normalized=alt,
                    alt_text=alt,
                    original_src=src,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.image_placeholders.append(img_obj)
                reading_order += 1
                img_idx += 1
                continue

            # 2. Footnote / Nota de rodapé
            is_footnote = (
                tag_name == "aside"
                or "footnote" in elem.get("class", [])
                or "footnote" in str(elem.get("id", "")).lower()
            )
            if is_footnote:
                fn_text, _ = extract_text_and_spans(elem)
                if fn_text:
                    fn_obj = Footnote(
                        id=generate_footnote_id(current_ch_id, fn_idx),
                        chapter_id=current_ch_id,
                        marker=str(fn_idx),
                        raw_text=fn_text,
                        normalized_text=fn_text,
                        reading_order=reading_order,
                        source_location=SourceLocation(file_path=str(path.name)),
                    )
                    current_chapter.footnotes.append(fn_obj)
                    reading_order += 1
                    fn_idx += 1
                continue

            # 3. Headings (h1 a h6)
            if tag_name.startswith("h") and len(tag_name) == 2 and tag_name[1].isdigit():
                level = int(tag_name[1])
                h_text, h_spans = extract_text_and_spans(elem)
                if not h_text:
                    continue

                if level == 1:
                    if first_h1:
                        current_ch_title = h_text
                        current_chapter.title = h_text
                        first_h1 = False
                    else:
                        start_new_chapter(h_text)

                heading_obj = Heading(
                    id=generate_heading_id(current_ch_id, h_idx),
                    chapter_id=current_ch_id,
                    level=level,
                    raw_text=h_text,
                    normalized_text=h_text,
                    reading_order=reading_order,
                    spans=h_spans,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.headings.append(heading_obj)
                reading_order += 1
                h_idx += 1
                continue

            # 4. Paragraph, List Item ou Blockquote
            block_text, block_spans = extract_text_and_spans(elem)
            if not block_text:
                continue

            is_diag, marker, clean_diag = self.identify_dialogue(block_text)
            if is_diag:
                diag_obj = DialogueBlock(
                    id=generate_dialogue_id(current_ch_id, diag_idx),
                    chapter_id=current_ch_id,
                    reading_order=reading_order,
                    raw_text=block_text,
                    normalized_text=clean_diag,
                    dialogue_marker=marker,
                    spans=block_spans,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.dialogue_blocks.append(diag_obj)
                diag_idx += 1
            else:
                para_obj = Paragraph(
                    id=generate_paragraph_id(current_ch_id, p_idx),
                    chapter_id=current_ch_id,
                    reading_order=reading_order,
                    raw_text=block_text,
                    normalized_text=block_text,
                    spans=block_spans,
                    source_location=SourceLocation(file_path=str(path.name)),
                )
                current_chapter.paragraphs.append(para_obj)
                p_idx += 1

            reading_order += 1

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
