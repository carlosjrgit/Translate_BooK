"""Guarda de segurança contra ataques de Zip Slip e Zip Bomb em arquivos EPUB e DOCX."""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path

from book_translator.security.path_guard import SecurityError

# Limites defensivos de segurança
MAX_TOTAL_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_SINGLE_ENTRY_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_ENTRIES_COUNT = 10_000
MAX_COMPRESSION_RATIO = 100.0  # Limite de taxa de expansão (descompressão)


def is_safe_zip_entry_path(entry_name: str) -> bool:
    """Verifica se o nome de entrada dentro do ZIP é estritamente seguro contra Zip Slip."""
    if not entry_name or "\x00" in entry_name:
        return False

    # Converte separadores Windows para padrão POSIX do ZIP
    clean = entry_name.replace("\\", "/")

    # Não pode começar com barra absoluta ou referências a drives Windows
    if clean.startswith("/") or (len(clean) >= 2 and clean[1] == ":"):
        return False

    # Normalização posixpath
    normalized = posixpath.normpath(clean)

    # Não pode escapar do diretório raiz
    if normalized.startswith("../") or normalized == "..":
        return False

    # Não pode conter componentes '..'
    parts = normalized.split("/")
    if ".." in parts:
        return False

    return True


def validate_zip_archive(
    archive_path: Path | str,
    max_total_uncompressed: int = MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_single_entry: int = MAX_SINGLE_ENTRY_UNCOMPRESSED_BYTES,
    max_entries: int = MAX_ENTRIES_COUNT,
) -> None:
    """Inspeciona um arquivo ZIP validando contra ataques de Zip Slip e Decompression Bomb.

    Lança SecurityError se qualquer entrada for maliciosa ou se os limites de recursos forem violados.
    """
    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de arquivo não encontrado: {path}")

    if not zipfile.is_zipfile(path):
        raise SecurityError(f"Arquivo corrompido ou formato inválido (não é um pacote ZIP válido): '{path.name}'")

    try:
        with zipfile.ZipFile(path, "r") as zf:
            infolist = zf.infolist()

            if len(infolist) > max_entries:
                raise SecurityError(
                    f"Ataque de negação de serviço detectado: O arquivo ZIP contém {len(infolist)} entradas, "
                    f"excedendo o limite máximo de segurança de {max_entries}."
                )

            total_uncompressed = 0

            for info in infolist:
                # 1. Defesa contra Zip Slip (Directory Traversal)
                if not is_safe_zip_entry_path(info.filename):
                    raise SecurityError(
                        f"Ataque de Zip Slip detectado no arquivo '{path.name}': "
                        f"Entrada maliciosa '{info.filename}' tenta escapar do diretório permitido."
                    )

                # 2. Defesa contra Zip Bomb (Tamanho por arquivo)
                if info.file_size > max_single_entry:
                    raise SecurityError(
                        f"Ataque de Zip Bomb detectado: Entrada '{info.filename}' possui "
                        f"{info.file_size / (1024**2):.1f} MB não comprimidos, "
                        f"excedendo o limite individual de {max_single_entry / (1024**2):.1f} MB."
                    )

                total_uncompressed += info.file_size

                # 3. Defesa contra Taxa de Compressão Abusiva (Bilion Laughs equivalente em ZIP)
                if info.compress_size > 0 and info.file_size > 1024:
                    ratio = info.file_size / info.compress_size
                    if ratio > MAX_COMPRESSION_RATIO:
                        raise SecurityError(
                            f"Ataque de Zip Bomb detectado: Entrada '{info.filename}' possui taxa de "
                            f"expansão abusiva ({ratio:.1f}:1), excedendo o limite de {MAX_COMPRESSION_RATIO}:1."
                        )

            # 4. Defesa contra tamanho total não comprimido
            if total_uncompressed > max_total_uncompressed:
                raise SecurityError(
                    f"Ataque de Decompression Bomb detectado: Tamanho total descompactado de "
                    f"{total_uncompressed / (1024**2):.1f} MB excede o limite permitido de "
                    f"{max_total_uncompressed / (1024**2):.1f} MB."
                )

    except zipfile.BadZipFile as e:
        raise SecurityError(f"Arquivo ZIP corrompido ou malformado: {e}") from e
