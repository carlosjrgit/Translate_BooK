"""Contrato base e classe abstrata para analisadores de formatos de entrada (parsers)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from book_translator.core.document import Document, DocumentMetadata
from book_translator.core.ids import generate_document_id
from book_translator.errors import ParsingError
from book_translator.logging import get_logger

logger = get_logger("parsers.base")

# 100 MB por padrão como salvaguarda contra consumo descontrolado de memória
DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024

DIALOGUE_MARKERS = ("—", "–", "―", "“", "”", "\"", "«", "»")
DASH_REGEX = re.compile(r"^[\s]*[—–―\-]\s*(.*)$")
QUOTE_REGEX = re.compile(r"^[\s]*[\"“«](.*)[\"”»][\s]*$")


@runtime_checkable
class ParserInterface(Protocol):
    """Protocolo formal para conversores de formato bruto em Document canônico."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        """Extensões suportadas pelo parser (ex: ('.epub',))."""
        ...

    def can_parse(self, file_path: Path | str) -> bool:
        """Verifica se o arquivo fornecido pode ser processado por este parser."""
        ...

    def parse(self, file_path: Path | str, title: str | None = None) -> Document:
        """Executa a extração e converte para a representação canônica Document."""
        ...


class BaseParser:
    """Classe base contendo salvaguardas, validações e utilitários comuns a todos os parsers."""

    def __init__(self, max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE) -> None:
        self.max_file_size_bytes = max_file_size_bytes

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        """Subclasses devem sobrescrever com as extensões suportadas."""
        return ()

    def can_parse(self, file_path: Path | str) -> bool:
        """Verifica se a extensão do arquivo corresponde às suportadas."""
        p = Path(file_path)
        return p.suffix.lower() in self.supported_extensions

    def validate_source_file(self, file_path: Path | str) -> Path:
        """Valida a existência, tipo, integridade de tamanho e permissão de leitura do arquivo."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Arquivo fonte não encontrado: {path}")
            raise ParsingError(f"Arquivo fonte não encontrado: '{path}'")
        if path.is_dir():
            logger.error(f"Caminho informado é um diretório: {path}")
            raise ParsingError(f"O caminho informado é um diretório, não um arquivo: '{path}'")

        try:
            size = path.stat().st_size
        except OSError as e:
            logger.error(f"Falha de acesso ao arquivo: {path} - {e}")
            raise ParsingError(f"Erro de acesso ao arquivo '{path}': {e}") from e

        if size == 0:
            logger.error(f"Arquivo vazio: {path}")
            raise ParsingError(f"O arquivo de entrada está vazio: '{path.name}'")

        if size > self.max_file_size_bytes:
            max_mb = self.max_file_size_bytes / (1024 * 1024)
            size_mb = size / (1024 * 1024)
            logger.error(f"Arquivo excede limite: {size_mb:.2f}MB > {max_mb:.2f}MB")
            raise ParsingError(
                f"O arquivo '{path.name}' possui {size_mb:.2f}MB e excede o limite "
                f"máximo suportado de {max_mb:.2f}MB."
            )

        return path

    @staticmethod
    def compute_sha256(path: Path) -> str:
        """Calcula o hash SHA-256 do arquivo fonte sem alterar seus metadados."""
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def create_base_document(
        self,
        file_path: Path,
        source_format: str,
        title: str | None = None,
        author: str = "Desconhecido",
    ) -> Document:
        """Instancia um Document raiz pré-configurado com metadados do arquivo."""
        resolved_title = title or file_path.stem.replace("_", " ").title()
        sha256_hash = self.compute_sha256(file_path)
        doc_id = generate_document_id(resolved_title)

        metadata = DocumentMetadata(
            title=resolved_title,
            author=author,
            source_format=source_format,
            source_file_path=str(file_path.resolve()),
            source_file_sha256=sha256_hash,
        )

        return Document(id=doc_id, metadata=metadata)

    @staticmethod
    def identify_dialogue(text: str) -> tuple[bool, str, str]:
        """Identifica se uma linha é um bloco explícito de diálogo.

        Retorna:
            (is_dialogue, marker, clean_text)
        """
        trimmed = text.strip()
        if not trimmed:
            return False, "", ""

        # Verifica travessão inicial
        dash_match = DASH_REGEX.match(trimmed)
        if dash_match:
            marker = trimmed[0]
            if marker in ("—", "–", "―", "-"):
                clean = dash_match.group(1).strip()
                return True, marker, clean

        # Verifica citação envolta por aspas
        quote_match = QUOTE_REGEX.match(trimmed)
        if quote_match and len(trimmed) >= 2:
            marker = trimmed[0]
            clean = quote_match.group(1).strip()
            return True, marker, clean

        return False, "", trimmed
