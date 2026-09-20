"""Gerenciador central de exportação multiformato."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from book_translator.core.models import Document
from book_translator.export.base import ExporterInterface, ExportOptions
from book_translator.export.docx import DocxExporter
from book_translator.export.epub import EpubExporter
from book_translator.export.naming import generate_safe_output_path, validate_safe_output_path
from book_translator.export.txt import TxtExporter


class ExportManager:
    """Orquestrador de exportação para múltiplos formatos (TXT, DOCX, EPUB)."""

    def __init__(self, exporters: Sequence[ExporterInterface] | None = None) -> None:
        if exporters is None:
            self._exporters: list[ExporterInterface] = [
                TxtExporter(),
                DocxExporter(),
                EpubExporter(),
            ]
        else:
            self._exporters = list(exporters)

    def register_exporter(self, exporter: ExporterInterface) -> None:
        """Registra um exportador adicional ou customizado."""
        self._exporters.append(exporter)

    @property
    def supported_formats(self) -> tuple[str, ...]:
        """Retorna todos os formatos suportados atualmente."""
        formats: list[str] = []
        for exp in self._exporters:
            for fmt in exp.supported_formats:
                fmt_lower = fmt.lower()
                if fmt_lower not in formats:
                    formats.append(fmt_lower)
        return tuple(formats)

    def get_exporter_for_format(self, format_name: str) -> ExporterInterface:
        """Localiza o exportador adequado para a extensão/formato solicitado."""
        normalized = format_name.strip().lstrip(".").lower()
        for exporter in self._exporters:
            if exporter.can_export(normalized):
                return exporter
        raise ValueError(f"Formato não suportado para exportação: '{format_name}'. Suportados: {self.supported_formats}")

    def export(
        self,
        document: Document,
        output_path_or_dir: Path | str,
        format_name: str,
        options: ExportOptions | None = None,
    ) -> Path:
        """Exporta o documento para o formato especificado de forma segura."""
        exporter = self.get_exporter_for_format(format_name)
        target = Path(output_path_or_dir)

        # Se o caminho for um diretório existente ou sem extensão, gera nome seguro
        if target.is_dir() or target.suffix == "":
            target = generate_safe_output_path(
                source_reference=document,
                output_dir=target,
                format_name=format_name,
                suffix="PT-BR",
            )
        else:
            original_path = getattr(getattr(document, "metadata", None), "source_file_path", None) or getattr(document, "original_path", None)
            validate_safe_output_path(target, original_path)

        return exporter.export(document, target, options)

    def export_all(
        self,
        document: Document,
        output_dir: Path | str,
        formats: Sequence[str] = ("txt", "docx", "epub"),
        options: ExportOptions | None = None,
    ) -> dict[str, Path]:
        """Exporta simultaneamente para múltiplos formatos com nomes seguros."""
        results: dict[str, Path] = {}
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for fmt in formats:
            path = self.export(document, out_dir, fmt, options)
            results[fmt.lower()] = path

        return results
