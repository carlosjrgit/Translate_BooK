"""Inspetor e detector de formato para arquivos de entrada."""

from __future__ import annotations

import zipfile
from pathlib import Path

from book_translator.errors import IngestionError
from book_translator.ingestion.base import IngestionInspection, IngestionInspectorInterface
from book_translator.logging import get_logger

logger = get_logger("ingestion.inspector")

SUPPORTED_EXTENSIONS_MAP: dict[str, str] = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".docx": "docx",
    ".epub": "epub",
    ".pdf": "pdf",
}


class IngestionInspector(IngestionInspectorInterface):
    """Implementação padrão do inspetor de arquivos para triagem e detecção de formato."""

    def detect_format(self, file_path: Path | str) -> str:
        """Detecta o formato do arquivo combinando extensão e inspeção de conteúdo."""
        path = Path(file_path)
        if not path.exists():
            raise IngestionError(f"Arquivo de entrada não encontrado: {path}")
        if path.is_dir():
            raise IngestionError(
                f"O caminho informado é um diretório, não um arquivo: {path}"
            )

        # 1. Detecção inicial por extensão
        ext = path.suffix.lower()
        detected = SUPPORTED_EXTENSIONS_MAP.get(ext)

        # 2. Inspeção de conteúdo / Magic Bytes
        try:
            with path.open("rb") as f:
                header = f.read(4096)
        except PermissionError as e:
            raise IngestionError(f"Permissão negada para ler arquivo: {path}") from e
        except OSError as e:
            raise IngestionError(f"Erro de sistema ao ler arquivo: {path}") from e

        # Validação específica de DOCX (arquivo ZIP contendo word/document.xml)
        if header.startswith(b"PK\x03\x04") or ext == ".docx":
            if zipfile.is_zipfile(path):
                try:
                    with zipfile.ZipFile(path, "r") as zf:
                        if "word/document.xml" in zf.namelist():
                            return "docx"
                except Exception:
                    # Pode ser docx corrompido, mas o formato pretendido é docx
                    return "docx"
            elif ext == ".docx":
                return "docx"

        # Validação específica de EPUB (arquivo ZIP contendo META-INF/container.xml)
        if header.startswith(b"PK\x03\x04") or ext == ".epub":
            if zipfile.is_zipfile(path):
                try:
                    with zipfile.ZipFile(path, "r") as zf:
                        nl = zf.namelist()
                        if "META-INF/container.xml" in nl:
                            return "epub"
                        if "mimetype" in nl and b"application/epub+zip" in zf.read("mimetype"):
                            return "epub"
                except Exception:
                    if ext == ".epub":
                        return "epub"
            elif ext == ".epub":
                return "epub"

        # Validação específica de HTML
        header_lower = header.lower()
        if (
            b"<!doctype html" in header_lower
            or b"<html" in header_lower
            or b"<head" in header_lower
            or b"<body" in header_lower
        ):
            return "html"

        if detected:
            return detected

        # Se tem extensão não suportada (ex: .xyz, .bin), rejeita
        if ext and ext not in SUPPORTED_EXTENSIONS_MAP:
            raise IngestionError(
                f"Formato ou extensão não suportada para o arquivo: '{path.name}'"
            )

        # Fallback se não tiver extensão conhecida mas for texto plano sem bytes nulos
        if b"\x00" not in header:
            try:
                header.decode("utf-8")
                return "txt"
            except UnicodeDecodeError:
                pass

        raise IngestionError(
            f"Formato não suportado ou não identificado para o arquivo: '{path.name}'"
        )

    def inspect(self, file_path: Path | str) -> IngestionInspection:
        """Inspeciona detalhadamente o arquivo gerando o relatório IngestionInspection."""
        path = Path(file_path)
        format_detected = self.detect_format(path)
        file_size = path.stat().st_size

        logger.info(
            f"Inspeção concluída: {path.name} | Formato: {format_detected} | "
            f"Tamanho: {file_size} bytes"
        )

        return IngestionInspection(
            file_path=path,
            detected_format=format_detected,
            file_size_bytes=file_size,
            has_text_layer=True,
            requires_ocr=False,
            estimated_pages_or_chapters=1,
        )
