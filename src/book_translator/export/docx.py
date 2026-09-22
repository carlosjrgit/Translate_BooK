"""Exportador nativo de documentos para formato DOCX (Office Open XML)."""

from __future__ import annotations

import html
import zipfile
from pathlib import Path

from book_translator.core.models import Document
from book_translator.errors import ExportError
from book_translator.export.base import ExporterInterface, ExportOptions, stitch_chapter_segments
from book_translator.export.naming import generate_safe_output_path
from book_translator.logging import get_logger

logger = get_logger("export.docx")


class DocxExporter(ExporterInterface):
    """Exportador nativo para DOCX (Office Open XML) com preservação de estilos, formatação e notas."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return ("docx",)

    def can_export(self, format_name: str) -> bool:
        return format_name.lower().lstrip(".") in self.supported_formats

    def export(
        self,
        document: Document,
        output_path: Path | str,
        options: ExportOptions | None = None,
    ) -> Path:
        """Constrói um pacote DOCX válido e compatível com Word, LibreOffice e Google Docs."""
        opts = options or ExportOptions()
        target = Path(output_path).resolve()

        source_path_str = getattr(document.metadata, "source_file_path", "")
        if source_path_str and Path(source_path_str).resolve() == target:
            target = generate_safe_output_path(
                source_reference=source_path_str,
                output_dir=target.parent,
                format_name="docx",
            )
            logger.warning(
                f"Destino original protegido contra sobrescrita. Redirecionado para '{target.name}'"
            )

        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # 1. [Content_Types].xml
                zf.writestr("[Content_Types].xml", self._build_content_types_xml())
                # 2. _rels/.rels
                zf.writestr("_rels/.rels", self._build_root_rels_xml())
                # 3. word/_rels/document.xml.rels
                zf.writestr("word/_rels/document.xml.rels", self._build_document_rels_xml())
                # 4. word/styles.xml
                zf.writestr("word/styles.xml", self._build_styles_xml())

                # 5. Processamento do documento e notas de rodapé
                body_xml, footnotes_xml = self._build_body_and_footnotes(document, opts)
                zf.writestr("word/document.xml", body_xml)
                zf.writestr("word/footnotes.xml", footnotes_xml)

            logger.info(f"Documento DOCX exportado com sucesso em '{target}'")
            return target
        except Exception as exc:
            logger.error(f"Falha ao exportar arquivo DOCX '{target}': {exc}")
            raise ExportError(f"Erro ao exportar documento para DOCX: {exc}") from exc

    # -------------------------------------------------------------------------
    # Construtores XML de Pacote OpenXML
    # -------------------------------------------------------------------------

    def _build_content_types_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
            '  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>\n'
            '  <Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>\n'
            "</Types>"
        )

    def _build_root_rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
            "</Relationships>"
        )

    def _build_document_rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
            '  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>\n'
            "</Relationships>"
        )

    def _build_styles_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            '  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">\n'
            '    <w:name w:val="Normal"/>\n'
            "    <w:rPr>\n"
            '      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>\n'
            '      <w:sz w:val="24"/>\n'  # 12pt
            "    </w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="paragraph" w:styleId="Title">\n'
            '    <w:name w:val="Title"/>\n'
            '    <w:basedOn w:val="Normal"/>\n'
            "    <w:pPr>\n"
            '      <w:jc w:val="center"/>\n'
            '      <w:spacing w:before="240" w:after="240"/>\n'
            "    </w:pPr>\n"
            "    <w:rPr>\n"
            '      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>\n'
            '      <w:b/>\n'
            '      <w:sz w:val="36"/>\n'  # 18pt
            "    </w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="paragraph" w:styleId="Heading1">\n'
            '    <w:name w:val="heading 1"/>\n'
            '    <w:basedOn w:val="Normal"/>\n'
            "    <w:pPr>\n"
            '      <w:spacing w:before="360" w:after="120"/>\n'
            "    </w:pPr>\n"
            "    <w:rPr>\n"
            '      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>\n'
            '      <w:b/>\n'
            '      <w:sz w:val="30"/>\n'  # 15pt
            "    </w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="character" w:styleId="FootnoteReference">\n'
            '    <w:name w:val="footnote reference"/>\n'
            "    <w:rPr>\n"
            '      <w:vertAlign w:val="superscript"/>\n'
            "    </w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="paragraph" w:styleId="FootnoteText">\n'
            '    <w:name w:val="footnote text"/>\n'
            '    <w:basedOn w:val="Normal"/>\n'
            "    <w:rPr>\n"
            '      <w:sz w:val="20"/>\n'  # 10pt
            "    </w:rPr>\n"
            "  </w:style>\n"
            "</w:styles>"
        )

    def _build_body_and_footnotes(
        self, document: Document, options: ExportOptions
    ) -> tuple[str, str]:
        """Gera o XML do corpo principal (document.xml) e a tabela de notas (footnotes.xml)."""
        body_parts: list[str] = []
        footnotes_entries: list[str] = []
        footnote_counter = 1

        title = options.custom_title or document.title or "Sem Título"
        author = options.custom_author or document.author or ""

        # Cabeçalho da Obra
        if options.include_metadata:
            body_parts.append(
                f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>{html.escape(title)}</w:t></w:r></w:p>'
            )
            if author:
                body_parts.append(
                    f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:i/></w:rPr><w:t>Por {html.escape(author)}</w:t></w:r></w:p>'
                )
            body_parts.append(
                '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="400"/></w:pPr><w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:t>Tradução: Translate_BooK (PT-BR)</w:t></w:r></w:p>'
            )

        for ch_idx, chapter in enumerate(document.chapters, start=1):
            if ch_idx > 1:
                # Quebra de página entre capítulos
                body_parts.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

            ch_title = chapter.title or f"Capítulo {chapter.order or ch_idx}"
            body_parts.append(
                f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{html.escape(ch_title)}</w:t></w:r></w:p>'
            )

            # Segmentos ou parágrafos
            if chapter.segments:
                for _unit_type, txt in stitch_chapter_segments(chapter.segments):
                    body_parts.append(self._format_paragraph_xml(txt))
            elif chapter.paragraphs:
                for p in sorted(chapter.paragraphs, key=lambda x: getattr(x, "reading_order", 0)):
                    txt = getattr(p, "normalized_text", p.raw_text)
                    if txt.strip():
                        body_parts.append(self._format_paragraph_xml(txt.strip()))

            # Notas de rodapé do capítulo
            if options.include_footnotes and chapter.footnotes:
                for fn in chapter.footnotes:
                    fn_id = footnote_counter
                    footnote_counter += 1
                    fn_text = fn.normalized_text or fn.raw_text

                    # Vincula a nota no final do capítulo
                    body_parts.append(
                        f'<w:p><w:pPr><w:spacing w:before="120"/></w:pPr>'
                        f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr>'
                        f'<w:footnoteReference w:id="{fn_id}"/></w:r>'
                        f'<w:r><w:t xml:space="preserve"> [Nota de Rodapé]</w:t></w:r></w:p>'
                    )

                    footnotes_entries.append(
                        f'  <w:footnote w:id="{fn_id}">\n'
                        f'    <w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr>'
                        f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>'
                        f'<w:r><w:t xml:space="preserve"> {html.escape(fn_text)}</w:t></w:r></w:p>\n'
                        f"  </w:footnote>\n"
                    )

        # Monta document.xml
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            "  <w:body>\n"
            + "\n".join(body_parts)
            + "\n    <w:sectPr>\n"
            '      <w:pgSz w:w="12240" w:h="15840"/>\n'  # Carta / A4 padrão
            '      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>\n'
            "    </w:sectPr>\n"
            "  </w:body>\n"
            "</w:document>"
        )

        # Monta footnotes.xml (com separador padrão IDs 0 e -1)
        footnotes_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            '  <w:footnote w:type="separator" w:id="-1">\n'
            "    <w:p><w:r><w:separator/></w:r></w:p>\n"
            "  </w:footnote>\n"
            '  <w:footnote w:type="continuationSeparator" w:id="0">\n'
            "    <w:p><w:r><w:continuationSeparator/></w:r></w:p>\n"
            "  </w:footnote>\n"
            + "".join(footnotes_entries)
            + "</w:footnotes>"
        )

        return document_xml, footnotes_xml

    def _format_paragraph_xml(self, text: str) -> str:
        """Gera parágrafo WordProcessingML processando marcações inline ou texto puro."""
        # Se for diálogo com travessão editorial
        is_dialogue = text.startswith("—") or text.startswith("- ")

        p_pr = ""
        if is_dialogue:
            p_pr = '<w:pPr><w:ind w:left="360" w:firstLine="-360"/></w:pPr>'
        else:
            p_pr = '<w:pPr><w:ind w:firstLine="360"/><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>'

        runs_xml = self._parse_inline_runs(text)
        return f"<w:p>{p_pr}{runs_xml}</w:p>"

    def _parse_inline_runs(self, text: str) -> str:
        """Divide o texto em runs XML respeitando negrito (**), itálico (*) e texto plano."""
        import re

        # Regex para tokens: **bold**, *italic*, [link](url)
        token_pattern = re.compile(r"(\*\*.+?\*\*|\*.+?\*|\[.+?\]\(.+?\))")
        parts = token_pattern.split(text)

        runs: list[str] = []
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) >= 4:
                inner = html.escape(part[2:-2])
                runs.append(f'<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{inner}</w:t></w:r>')
            elif part.startswith("*") and part.endswith("*") and len(part) >= 2:
                inner = html.escape(part[1:-1])
                runs.append(f'<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">{inner}</w:t></w:r>')
            elif part.startswith("[") and "](" in part and part.endswith(")"):
                # Formato [link text](url) -> renderiza link text sublinhado
                link_match = re.match(r"\[(.+?)\]\((.+?)\)", part)
                if link_match:
                    link_text = html.escape(link_match.group(1))
                    runs.append(f'<w:r><w:rPr><w:u w:val="single"/><w:color w:val="0563C1"/></w:rPr><w:t xml:space="preserve">{link_text}</w:t></w:r>')
                else:
                    runs.append(f'<w:r><w:t xml:space="preserve">{html.escape(part)}</w:t></w:r>')
            else:
                runs.append(f'<w:r><w:t xml:space="preserve">{html.escape(part)}</w:t></w:r>')

        return "".join(runs) if runs else f'<w:r><w:t xml:space="preserve">{html.escape(text)}</w:t></w:r>'

