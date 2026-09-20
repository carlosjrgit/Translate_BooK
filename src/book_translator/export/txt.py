"""Exportador de documentos para formato TXT (texto puro estruturado UTF-8)."""

from __future__ import annotations

from pathlib import Path

from book_translator.core.models import Document
from book_translator.errors import ExportError
from book_translator.export.base import ExporterInterface, ExportOptions
from book_translator.export.naming import generate_safe_output_path
from book_translator.logging import get_logger

logger = get_logger("export.txt")


class TxtExporter(ExporterInterface):
    """Exportador para texto puro com preservação estrutural de capítulos, diálogos e notas."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return ("txt",)

    def can_export(self, format_name: str) -> bool:
        return format_name.lower().lstrip(".") in self.supported_formats

    def export(
        self,
        document: Document,
        output_path: Path | str,
        options: ExportOptions | None = None,
    ) -> Path:
        """Gera o arquivo TXT estruturado a partir do Documento traduzido."""
        opts = options or ExportOptions()
        target = Path(output_path).resolve()

        # Proteção estrita contra sobrescrita do arquivo original de entrada
        source_path_str = getattr(document.metadata, "source_file_path", "")
        if source_path_str and Path(source_path_str).resolve() == target:
            target = generate_safe_output_path(
                source_reference=source_path_str,
                output_dir=target.parent,
                format_name="txt",
            )
            logger.warning(
                f"Destino original protegido contra sobrescrita. Redirecionado para '{target.name}'"
            )

        target.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []

        # 1. Cabeçalho / Metadados da Obra
        title = opts.custom_title or document.title or "Sem Título"
        author = opts.custom_author or document.author or "Autor Desconhecido"

        if opts.include_metadata:
            lines.append("=" * 70)
            lines.append(title.upper())
            lines.append(f"Autor: {author}")
            lines.append("Tradução: Translate_BooK (EN -> PT-BR)")
            lines.append("=" * 70)
            lines.append("")
            lines.append("")

        all_footnotes: list[tuple[str, str]] = []

        # 2. Iteração de Capítulos
        for ch_idx, chapter in enumerate(document.chapters, start=1):
            ch_title = chapter.title or f"Capítulo {chapter.order or ch_idx}"
            lines.append("-" * 50)
            lines.append(ch_title)
            lines.append("-" * 50)
            lines.append("")

            # Coleta parágrafos e segmentos traduzidos
            if chapter.segments:
                for seg in sorted(chapter.segments, key=lambda s: s.sequence_order):
                    text = seg.translated_text if seg.translated_text else seg.original_text
                    if text.strip():
                        lines.append(text.strip())
                        lines.append("")
            elif chapter.paragraphs:
                for p in sorted(chapter.paragraphs, key=lambda x: getattr(x, "reading_order", 0)):
                    text = getattr(p, "normalized_text", p.raw_text)
                    if text.strip():
                        lines.append(text.strip())
                        lines.append("")

            # Notas de rodapé do capítulo
            if opts.include_footnotes and chapter.footnotes:
                lines.append("")
                lines.append("[Notas do Capítulo]")
                for fn in chapter.footnotes:
                    fn_marker = fn.marker or "*"
                    fn_text = fn.normalized_text or fn.raw_text
                    lines.append(f"[{fn_marker}] {fn_text}")
                    all_footnotes.append((fn_marker, fn_text))
                lines.append("")

            lines.append("")

        # 3. Escrita em disco com codificação segura
        try:
            target.write_text("\n".join(lines), encoding=opts.target_encoding)
            logger.info(f"Documento exportado com sucesso para TXT: '{target}' ({len(lines)} linhas)")
            return target
        except Exception as exc:
            logger.error(f"Falha ao gravar arquivo TXT '{target}': {exc}")
            raise ExportError(f"Erro ao exportar documento para TXT: {exc}") from exc
