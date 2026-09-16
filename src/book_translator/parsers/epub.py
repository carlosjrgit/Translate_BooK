"""Parser canônico para e-books em formato EPUB (EPUB2 e EPUB3)."""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
import zipfile
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

logger = get_logger("parsers.epub")

NS_CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
NS_OPF = "{http://www.idpf.org/2007/opf}"
NS_DC = "{http://purl.org/dc/elements/1.1/}"

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


class EpubParser(BaseParser):
    """Analisador de arquivos EPUB 2 e 3 com respeito à spine e prevenção de duplicações de TOC."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".epub",)

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        path = self.validate_source_file(file_path)

        if not zipfile.is_zipfile(path):
            raise ParsingError(f"Arquivo EPUB corrompido ou formato inválido: '{path.name}'")

        try:
            with zipfile.ZipFile(path, "r") as zf:
                namelist = zf.namelist()

                # 1. Localização do arquivo OPF através de META-INF/container.xml
                if "META-INF/container.xml" not in namelist:
                    raise ParsingError(
                        f"Estrutura OCF inválida (arquivo 'META-INF/container.xml' ausente): "
                        f"'{path.name}'"
                    )

                container_xml = zf.read("META-INF/container.xml")
                try:
                    c_root = ET.fromstring(container_xml)
                except ET.ParseError as e:
                    raise ParsingError(f"XML corrompido em 'META-INF/container.xml': {e}") from e

                rootfile_el = c_root.find(f".//{NS_CONTAINER}rootfile")
                if rootfile_el is None or not rootfile_el.get("full-path"):
                    raise ParsingError(
                        f"Elemento <rootfile> ausente em 'container.xml': '{path.name}'"
                    )

                opf_path = rootfile_el.get("full-path", "").strip()
                if opf_path not in namelist:
                    raise ParsingError(
                        f"Arquivo OPF '{opf_path}' não encontrado no EPUB: '{path.name}'"
                    )

                opf_dir = posixpath.dirname(opf_path)

                # 2. Leitura e parsing do pacote OPF
                opf_xml = zf.read(opf_path)
                try:
                    opf_root = ET.fromstring(opf_xml)
                except ET.ParseError as e:
                    raise ParsingError(f"XML corrompido no arquivo OPF '{opf_path}': {e}") from e

                epub_version = opf_root.get("version", "2.0")

                # Metadados Dublin Core
                meta_el = opf_root.find(f"{NS_OPF}metadata")
                if meta_el is None:
                    meta_el = opf_root.find("metadata")

                doc_title = title
                doc_author = "Desconhecido"
                doc_lang = "en"
                doc_publisher = ""
                doc_date = ""
                doc_isbn = ""

                if meta_el is not None:
                    t_el = meta_el.find(f"{NS_DC}title")
                    if t_el is not None and t_el.text and not doc_title:
                        doc_title = t_el.text.strip()
                    a_el = meta_el.find(f"{NS_DC}creator")
                    if a_el is not None and a_el.text:
                        doc_author = a_el.text.strip()
                    l_el = meta_el.find(f"{NS_DC}language")
                    if l_el is not None and l_el.text:
                        doc_lang = l_el.text.strip()
                    p_el = meta_el.find(f"{NS_DC}publisher")
                    if p_el is not None and p_el.text:
                        doc_publisher = p_el.text.strip()
                    d_el = meta_el.find(f"{NS_DC}date")
                    if d_el is not None and d_el.text:
                        doc_date = d_el.text.strip()
                    i_el = meta_el.find(f"{NS_DC}identifier")
                    if i_el is not None and i_el.text:
                        doc_isbn = i_el.text.strip()

                # Manifest
                manifest_el = opf_root.find(f"{NS_OPF}manifest")
                if manifest_el is None:
                    manifest_el = opf_root.find("manifest")
                if manifest_el is None:
                    raise ParsingError(f"Manifest ausente no arquivo OPF '{opf_path}'")

                manifest: dict[str, dict[str, str]] = {}
                nav_item_ids: set[str] = set()

                items = manifest_el.findall(f"{NS_OPF}item") or manifest_el.findall("item")
                for item in items:
                    i_id = item.get("id", "")
                    href = item.get("href", "")
                    mtype = item.get("media-type", "")
                    props = item.get("properties", "")

                    manifest[i_id] = {
                        "href": href,
                        "media_type": mtype,
                        "properties": props,
                    }

                    # Identifica itens de navegação / TOC
                    if "nav" in props.split():
                        nav_item_ids.add(i_id)
                    if mtype == "application/x-dtbncx+xml":
                        nav_item_ids.add(i_id)
                    lower_href = href.lower()
                    if lower_href in ("toc.xhtml", "nav.xhtml", "toc.ncx", "toc.html"):
                        nav_item_ids.add(i_id)

                # Spine (ordem canônica de leitura)
                spine_el = opf_root.find(f"{NS_OPF}spine")
                if spine_el is None:
                    spine_el = opf_root.find("spine")
                if spine_el is None:
                    raise ParsingError(f"Spine ausente no arquivo OPF '{opf_path}'")

                toc_ncx_id = spine_el.get("toc")
                if toc_ncx_id:
                    nav_item_ids.add(toc_ncx_id)

                spine_itemrefs: list[str] = []
                itemrefs = spine_el.findall(f"{NS_OPF}itemref") or spine_el.findall("itemref")
                for itemref in itemrefs:
                    idref = itemref.get("idref")
                    if idref:
                        spine_itemrefs.append(idref)

                # Instancia o documento canônico
                doc = self.create_base_document(
                    file_path=path,
                    source_format="epub",
                    title=doc_title,
                    author=doc_author,
                )
                doc.metadata.language = doc_lang
                doc.metadata.publisher = doc_publisher
                doc.metadata.publication_date = doc_date
                doc.metadata.isbn = doc_isbn

                # Salva metadados de empacotamento para futura reconstrução do EPUB traduzido
                doc.metadata.extra.update(
                    {
                        "epub_version": epub_version,
                        "opf_path": opf_path,
                        "spine": spine_itemrefs,
                        "manifest": manifest,
                        "nav_item_ids": list(nav_item_ids),
                    }
                )

                # 3. Processamento dos documentos XHTML na sequência da Spine
                chapters: list[Chapter] = []
                ch_order = 1

                for idref in spine_itemrefs:
                    # Evita duplicação de texto causada por TOC/Nav
                    if idref in nav_item_ids:
                        logger.debug(
                            f"Item da spine '{idref}' identificado como TOC/Nav; "
                            "ignorando duplicação textual."
                        )
                        continue

                    item_info = manifest.get(idref)
                    if not item_info:
                        continue

                    # Processa apenas documentos de texto XHTML/HTML
                    if item_info["media_type"] not in (
                        "application/xhtml+xml",
                        "text/html",
                        "application/xml",
                    ):
                        continue

                    rel_href = item_info["href"]
                    # Resolve caminho dentro do arquivo ZIP
                    if opf_dir:
                        zip_entry_path = posixpath.normpath(posixpath.join(opf_dir, rel_href))
                    else:
                        zip_entry_path = rel_href

                    if zip_entry_path not in namelist:
                        logger.warning(
                            f"Arquivo XHTML '{zip_entry_path}' referenciado na spine "
                            "não encontrado no ZIP."
                        )
                        continue

                    raw_xhtml = zf.read(zip_entry_path)
                    ch_doc = self._parse_xhtml_chapter(
                        raw_bytes=raw_xhtml,
                        zip_entry_path=zip_entry_path,
                        doc_id=doc.id,
                        chapter_order=ch_order,
                        item_id=idref,
                    )

                    if ch_doc:
                        chapters.append(ch_doc)
                        ch_order += 1

                if not chapters:
                    raise ParsingError(
                        f"Nenhum capítulo de leitura pôde ser extraído do EPUB '{path.name}'."
                    )

                doc.chapters = chapters
                return doc

        except zipfile.BadZipFile as e:
            raise ParsingError(f"Arquivo EPUB corrompido ou truncado: '{path.name}'") from e
        except ParsingError:
            raise
        except Exception as e:
            raise ParsingError(f"Falha ao processar arquivo EPUB '{path.name}': {e}") from e

    def _parse_xhtml_chapter(
        self,
        raw_bytes: bytes,
        zip_entry_path: str,
        doc_id: str,
        chapter_order: int,
        item_id: str,
    ) -> Chapter | None:
        """Processa um arquivo XHTML individual da spine e constrói um Chapter canônico."""
        encoding = detect_encoding(raw_bytes)
        try:
            raw_text = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        norm_html = normalize_unicode(raw_text)
        if not norm_html.strip():
            return None

        soup = BeautifulSoup(norm_html, "html.parser")

        # Verifica se o documento é puramente de navegação TOC (ex: <nav epub:type="toc">)
        nav_tag = soup.find("nav", attrs={"epub:type": "toc"}) or soup.find(
            "nav", attrs={"role": "doc-toc"}
        )
        if nav_tag and not soup.find_all("p"):
            logger.debug(
                f"Arquivo '{zip_entry_path}' contém apenas navegação TOC; ignorando duplicação."
            )
            return None

        # Título do capítulo
        ch_title = f"Capítulo {chapter_order}"
        first_h = soup.find(["h1", "h2"])
        if first_h and first_h.get_text(strip=True):
            ch_title = first_h.get_text(strip=True)
        elif soup.title and soup.title.string:
            ch_title = soup.title.string.strip()

        ch_id = generate_chapter_id(doc_id, chapter_order)
        chapter = Chapter(
            id=ch_id,
            title=ch_title,
            order=chapter_order,
            reading_order=chapter_order,
            metadata={
                "original_href": zip_entry_path,
                "item_id": item_id,
            },
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

        root = soup.body if soup.body else soup

        # Itera nós blocos relevantes no XHTML
        for elem in root.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "img", "image", "aside"],
            recursive=True,
        ):
            if elem.parent and elem.parent.name in ("p", "li", "blockquote", "aside"):
                continue

            tag_name = elem.name.lower()

            # 1. Imagem (img ou svg:image)
            if tag_name in ("img", "image"):
                src = elem.get("src") or elem.get("xlink:href") or elem.get("href", "")
                alt = elem.get("alt", "")
                # Resolve caminho da imagem relativo ao XHTML
                xhtml_dir = posixpath.dirname(zip_entry_path)
                if xhtml_dir and not src.startswith("/"):
                    resolved_img_path = posixpath.normpath(posixpath.join(xhtml_dir, src))
                else:
                    resolved_img_path = src

                img_obj = ImagePlaceholder(
                    id=generate_image_id(ch_id, img_idx),
                    chapter_id=ch_id,
                    reading_order=reading_order,
                    caption_raw=alt,
                    caption_normalized=alt,
                    alt_text=alt,
                    relative_path=resolved_img_path,
                    original_src=src,
                    source_location=SourceLocation(file_path=zip_entry_path),
                )
                chapter.image_placeholders.append(img_obj)
                reading_order += 1
                img_idx += 1
                continue

            # 2. Footnote / Nota de rodapé (epub:type="footnote", role="doc-footnote", etc.)
            epub_type = elem.get("epub:type", "")
            role = elem.get("role", "")
            is_footnote = (
                "footnote" in epub_type
                or "doc-footnote" in role
                or "footnote" in elem.get("class", [])
                or tag_name == "aside"
            )
            if is_footnote:
                fn_text, _ = extract_text_and_spans(elem)
                if fn_text:
                    fn_obj = Footnote(
                        id=generate_footnote_id(ch_id, fn_idx),
                        chapter_id=ch_id,
                        marker=str(fn_idx),
                        raw_text=fn_text,
                        normalized_text=fn_text,
                        reading_order=reading_order,
                        source_location=SourceLocation(file_path=zip_entry_path),
                    )
                    chapter.footnotes.append(fn_obj)
                    reading_order += 1
                    fn_idx += 1
                continue

            # 3. Headings
            if tag_name.startswith("h") and len(tag_name) == 2 and tag_name[1].isdigit():
                level = int(tag_name[1])
                h_text, h_spans = extract_text_and_spans(elem)
                if not h_text:
                    continue

                heading_obj = Heading(
                    id=generate_heading_id(ch_id, h_idx),
                    chapter_id=ch_id,
                    level=level,
                    raw_text=h_text,
                    normalized_text=h_text,
                    reading_order=reading_order,
                    spans=h_spans,
                    source_location=SourceLocation(file_path=zip_entry_path),
                )
                chapter.headings.append(heading_obj)
                reading_order += 1
                h_idx += 1
                continue

            # 4. Parágrafo ou Diálogo
            block_text, block_spans = extract_text_and_spans(elem)
            if not block_text:
                continue

            is_diag, marker, clean_diag = self.identify_dialogue(block_text)
            if is_diag:
                diag_obj = DialogueBlock(
                    id=generate_dialogue_id(ch_id, diag_idx),
                    chapter_id=ch_id,
                    reading_order=reading_order,
                    raw_text=block_text,
                    normalized_text=clean_diag,
                    dialogue_marker=marker,
                    spans=block_spans,
                    source_location=SourceLocation(file_path=zip_entry_path),
                )
                chapter.dialogue_blocks.append(diag_obj)
                diag_idx += 1
            else:
                para_obj = Paragraph(
                    id=generate_paragraph_id(ch_id, p_idx),
                    chapter_id=ch_id,
                    reading_order=reading_order,
                    raw_text=block_text,
                    normalized_text=block_text,
                    spans=block_spans,
                    source_location=SourceLocation(file_path=zip_entry_path),
                )
                chapter.paragraphs.append(para_obj)
                p_idx += 1

            reading_order += 1

        if not chapter.headings and not chapter.paragraphs and not chapter.dialogue_blocks:
            return None

        return chapter
