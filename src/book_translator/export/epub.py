"""Exportador determinístico de EPUB 3 para obras traduzidas."""

from __future__ import annotations

import datetime
import html
import re
import uuid
import zipfile
from pathlib import Path

from book_translator.core.models import Document
from book_translator.export.base import ExporterInterface, ExportOptions
from book_translator.export.naming import generate_safe_output_path, validate_safe_output_path
from book_translator.logging import get_logger

logger = get_logger("export.epub")


class EpubExporter(ExporterInterface):
    """Exportador determinístico para formato EPUB 3 (com compatibilidade EPUB 2).

    Garante que a estrutura física (OPF, NCX, NAV XHTML) seja estritamente
    reconstruída de forma programática determinística, sem intervenção direta
    de IA em estruturas XML/XHTML.
    """

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return ("epub",)

    def can_export(self, format_name: str) -> bool:
        return format_name.strip().lower().lstrip(".") == "epub"

    def export(
        self,
        document: Document,
        output_path: Path | str,
        options: ExportOptions | None = None,
    ) -> Path:
        """Gera o arquivo .epub de forma determinística."""
        opts = options or ExportOptions()
        target_path = Path(output_path).resolve()

        source_path_str = getattr(document.metadata, "source_file_path", "")
        validate_safe_output_path(target_path, source_path_str)

        if source_path_str and Path(source_path_str).resolve() == target_path:
            target_path = generate_safe_output_path(
                source_reference=source_path_str,
                output_dir=target_path.parent,
                format_name="epub",
            )
            logger.warning(
                f"Destino original protegido contra sobrescrita. Redirecionado para '{target_path.name}'"
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)

        title = opts.custom_title or document.title or "Obra Traduzida"
        author = opts.custom_author or document.author or "Desconhecido"
        book_id = str(uuid.uuid4())
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        # 1. Extrair capítulos estruturados
        chapters_data = self._extract_chapters_data(document)

        # 2. Gerar arquivos do pacote EPUB
        css_content = self._generate_css()
        chapter_files: list[tuple[str, str, str]] = []  # (id, filename, content)
        all_footnotes: list[tuple[str, str, str]] = []  # (id, ref_id, text)

        for idx, (chap_title, paragraphs, footnotes) in enumerate(chapters_data, start=1):
            chap_id = f"chap_{idx:03d}"
            chap_filename = f"chapter_{idx:03d}.xhtml"
            xhtml, chap_notes = self._render_chapter_xhtml(
                chap_id=chap_id,
                title=chap_title,
                paragraphs=paragraphs,
                footnotes=footnotes,
                chapter_index=idx,
                preserve_formatting=opts.preserve_formatting,
                include_footnotes=opts.include_footnotes,
            )
            chapter_files.append((chap_id, chap_filename, xhtml))
            all_footnotes.extend(chap_notes)

        # Se houver notas globais
        if opts.include_footnotes and all_footnotes:
            notes_xhtml = self._render_notes_xhtml(all_footnotes)
            chapter_files.append(("notes", "notes.xhtml", notes_xhtml))

        # 3. Gerar manifesto e espinha (content.opf)
        content_opf = self._generate_content_opf(
            book_id=book_id,
            title=title,
            author=author,
            date_str=date_str,
            chapter_files=chapter_files,
        )

        # 4. Gerar Navegação (nav.xhtml e toc.ncx)
        nav_xhtml = self._generate_nav_xhtml(
            title=title,
            chapters=chapters_data,
            has_notes=bool(all_footnotes and opts.include_footnotes),
        )
        toc_ncx = self._generate_toc_ncx(
            book_id=book_id,
            title=title,
            author=author,
            chapters=chapters_data,
        )

        # 5. Empacotar ZIP seguindo rigorosamente a especificação EPUB 3
        self._pack_epub(
            target_path=target_path,
            css_content=css_content,
            chapter_files=chapter_files,
            content_opf=content_opf,
            nav_xhtml=nav_xhtml,
            toc_ncx=toc_ncx,
        )

        logger.info(f"Documento EPUB exportado com sucesso em '{target_path}'")
        return target_path

    def _extract_chapters_data(
        self, document: Document
    ) -> list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]]:
        """Retorna lista de (chap_title, [(kind, text)], [(marker, text)])."""
        chapters_data: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]] = []

        if document.chapters:
            for ch_idx, ch in enumerate(document.chapters, start=1):
                ch_title = ch.title or f"Capítulo {ch.order or ch_idx}"
                paras: list[tuple[str, str]] = []
                notes: list[tuple[str, str]] = []

                if ch.segments:
                    for seg in sorted(ch.segments, key=lambda s: getattr(s, "sequence_order", 0)):
                        txt = seg.translated_text if seg.translated_text else seg.original_text
                        if not txt or not txt.strip():
                            continue
                        unit_type = seg.metadata.get("unit_type", "paragraph")
                        paras.append((unit_type, txt.strip()))
                elif ch.paragraphs:
                    for p in sorted(ch.paragraphs, key=lambda x: getattr(x, "reading_order", 0)):
                        txt = getattr(p, "normalized_text", p.raw_text)
                        if txt and txt.strip():
                            paras.append(("paragraph", txt.strip()))

                if ch.footnotes:
                    for fn in ch.footnotes:
                        f_marker = fn.marker or "*"
                        f_text = fn.normalized_text or fn.raw_text
                        notes.append((f_marker, f_text))

                chapters_data.append((ch_title, paras, notes))
        else:
            # Fallback caso não haja capítulos explícitos
            ch_title = document.title or "Capítulo 1"
            paras = []
            notes = []
            if hasattr(document, "global_footnotes"):
                for fn in document.global_footnotes:
                    notes.append((fn.marker or "*", fn.normalized_text or fn.raw_text))
            chapters_data.append((ch_title, paras, notes))

        return chapters_data

    def _format_inline_text(self, raw_text: str, preserve_formatting: bool) -> str:
        """Escapa entidades HTML e preserva marcações de itálico/negrito e links."""
        escaped = html.escape(raw_text)
        if not preserve_formatting:
            return escaped

        # Negrito: **texto** ou __texto__
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"__(.+?)__", r"<strong>\1</strong>", escaped)

        # Itálico: *texto* ou _texto_
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        escaped = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", escaped)

        # Links em markdown: [link](url)
        escaped = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2">\1</a>', escaped)

        # Quebras de linha
        escaped = escaped.replace("\n", "<br/>\n")
        return escaped

    def _render_chapter_xhtml(
        self,
        chap_id: str,
        title: str,
        paragraphs: list[tuple[str, str]],
        footnotes: list[tuple[str, str]],
        chapter_index: int,
        preserve_formatting: bool,
        include_footnotes: bool,
    ) -> tuple[str, list[tuple[str, str, str]]]:
        body_parts = [f"<h1>{html.escape(title)}</h1>"]
        chapter_notes: list[tuple[str, str, str]] = []

        for kind, text in paragraphs:
            formatted_text = self._format_inline_text(text, preserve_formatting)
            if kind == "heading":
                body_parts.append(f"<h2>{formatted_text}</h2>")
            elif kind == "caption":
                body_parts.append(f'<p class="caption">{formatted_text}</p>')
            elif kind == "footnote":
                if include_footnotes:
                    n_idx = len(chapter_notes) + 1
                    fn_id = f"fn_{chapter_index}_{n_idx}"
                    ref_id = f"ref_{chapter_index}_{n_idx}"
                    chapter_notes.append((fn_id, ref_id, text))
            else:
                body_parts.append(f"<p>{formatted_text}</p>")

        # Processar footnotes explícitas do capítulo
        if footnotes and include_footnotes:
            for marker, fn_text in footnotes:
                n_idx = len(chapter_notes) + 1
                fn_id = f"fn_{chapter_index}_{n_idx}"
                ref_id = f"ref_{chapter_index}_{n_idx}"
                chapter_notes.append((fn_id, ref_id, f"[{marker}] {fn_text}"))

        if chapter_notes and include_footnotes:
            body_parts.append('<section class="footnotes" epub:type="footnotes">')
            body_parts.append("<h3>Notas</h3>")
            for fn_id, ref_id, note_text in chapter_notes:
                esc_note = html.escape(note_text)
                body_parts.append(
                    f'<aside id="{fn_id}" epub:type="footnote">'
                    f'<p><a href="#{ref_id}" class="fn-backlink">[{fn_id}]</a> {esc_note}</p>'
                    f'</aside>'
                )
            body_parts.append("</section>")

        xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt-BR" lang="pt-BR">
<head>
    <meta charset="utf-8" />
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css" />
</head>
<body epub:type="bodymatter">
    <section id="{chap_id}" epub:type="chapter">
        {"".join(body_parts)}
    </section>
</body>
</html>"""
        return xhtml, chapter_notes

    def _render_notes_xhtml(self, notes: list[tuple[str, str, str]]) -> str:
        items = []
        for fn_id, _, text in notes:
            items.append(f'<li id="{fn_id}"><p>{html.escape(text)}</p></li>')

        return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt-BR" lang="pt-BR">
<head>
    <meta charset="utf-8" />
    <title>Notas de Rodapé</title>
    <link rel="stylesheet" type="text/css" href="styles.css" />
</head>
<body epub:type="backmatter">
    <section epub:type="footnotes">
        <h1>Notas de Rodapé</h1>
        <ol>
            {"".join(items)}
        </ol>
    </section>
</body>
</html>"""

    def _generate_css(self) -> str:
        return """@charset "utf-8";
body {
    font-family: serif;
    font-size: 1.05em;
    line-height: 1.5;
    margin: 5%;
    text-align: justify;
    color: #1a1a1a;
}
h1 {
    font-size: 1.6em;
    text-align: center;
    margin-top: 2em;
    margin-bottom: 1em;
    page-break-before: always;
}
h2 {
    font-size: 1.3em;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}
h3 {
    font-size: 1.1em;
    margin-top: 1.2em;
}
p {
    margin-top: 0;
    margin-bottom: 0.8em;
    text-indent: 1.5em;
}
.caption {
    font-size: 0.9em;
    font-style: italic;
    text-align: center;
    text-indent: 0;
}
.footnotes {
    margin-top: 2em;
    border-top: 1px solid #ccc;
    font-size: 0.9em;
}
aside[epub\\:type="footnote"] {
    margin-top: 0.5em;
}
a {
    color: #0366d6;
    text-decoration: underline;
}
"""

    def _generate_content_opf(
        self,
        book_id: str,
        title: str,
        author: str,
        date_str: str,
        chapter_files: list[tuple[str, str, str]],
    ) -> str:
        manifest_items = [
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />',
            '<item id="css" href="styles.css" media-type="text/css" />',
        ]
        spine_items = []

        for cid, filename, _ in chapter_files:
            manifest_items.append(f'<item id="{cid}" href="{filename}" media-type="application/xhtml+xml" />')
            spine_items.append(f'<itemref idref="{cid}" />')

        manifest_str = "\n        ".join(manifest_items)
        spine_str = "\n        ".join(spine_items)

        return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" xml:lang="pt-BR">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="pub-id">urn:uuid:{book_id}</dc:identifier>
        <dc:title>{html.escape(title)}</dc:title>
        <dc:creator>{html.escape(author)}</dc:creator>
        <dc:language>pt-BR</dc:language>
        <dc:date>{date_str}</dc:date>
        <meta property="dcterms:modified">{date_str}T00:00:00Z</meta>
    </metadata>
    <manifest>
        {manifest_str}
    </manifest>
    <spine toc="ncx">
        {spine_str}
    </spine>
</package>"""

    def _generate_nav_xhtml(
        self,
        title: str,
        chapters: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]],
        has_notes: bool,
    ) -> str:
        nav_items = []
        for idx, (chap_title, _, _) in enumerate(chapters, start=1):
            filename = f"chapter_{idx:03d}.xhtml"
            nav_items.append(f'<li><a href="{filename}">{html.escape(chap_title)}</a></li>')

        if has_notes:
            nav_items.append('<li><a href="notes.xhtml">Notas de Rodapé</a></li>')

        nav_str = "\n                ".join(nav_items)

        return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt-BR" lang="pt-BR">
<head>
    <meta charset="utf-8" />
    <title>Sumário</title>
    <link rel="stylesheet" type="text/css" href="styles.css" />
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Sumário</h1>
        <ol>
            {nav_str}
        </ol>
    </nav>
</body>
</html>"""

    def _generate_toc_ncx(
        self,
        book_id: str,
        title: str,
        author: str,
        chapters: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]],
    ) -> str:
        nav_points = []
        for idx, (chap_title, _, _) in enumerate(chapters, start=1):
            filename = f"chapter_{idx:03d}.xhtml"
            nav_points.append(
                f'<navPoint id="navPoint-{idx}" playOrder="{idx}">'
                f'<navLabel><text>{html.escape(chap_title)}</text></navLabel>'
                f'<content src="{filename}"/>'
                f'</navPoint>'
            )

        points_str = "\n        ".join(nav_points)

        return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="urn:uuid:{book_id}"/>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle><text>{html.escape(title)}</text></docTitle>
    <docAuthor><text>{html.escape(author)}</text></docAuthor>
    <navMap>
        {points_str}
    </navMap>
</ncx>"""

    def _pack_epub(
        self,
        target_path: Path,
        css_content: str,
        chapter_files: list[tuple[str, str, str]],
        content_opf: str,
        nav_xhtml: str,
        toc_ncx: str,
    ) -> None:
        """Gera o arquivo zip com o mimetype descompactado primeiro (especificação EPUB)."""
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""

        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", container_xml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/content.opf", content_opf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/nav.xhtml", nav_xhtml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/toc.ncx", toc_ncx.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("OEBPS/styles.css", css_content.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)

            for _, filename, content in chapter_files:
                zf.writestr(f"OEBPS/{filename}", content.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
