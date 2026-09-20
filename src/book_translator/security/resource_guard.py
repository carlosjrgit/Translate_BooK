"""Guarda de recursos para prevenção de exaustão de memória e validação de URLs seguras."""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from book_translator.security.path_guard import SecurityError

MAX_INPUT_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_SEGMENT_CHARACTERS = 150_000  # 150 mil caracteres por parágrafo/segmento


def validate_file_size_limit(file_path: Path | str, max_bytes: int = MAX_INPUT_FILE_SIZE_BYTES) -> None:
    """Garante que arquivos de entrada não excedam os limites de segurança de memória."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    actual_size = path.stat().st_size
    if actual_size > max_bytes:
        raise SecurityError(
            f"Arquivo '{path.name}' excede o limite máximo permitido de segurança "
            f"({actual_size / (1024**2):.1f} MB > {max_bytes / (1024**2):.1f} MB)."
        )


def validate_segment_size(text: str, max_chars: int = MAX_SEGMENT_CHARACTERS) -> None:
    """Impede que segmentos excessivamente gigantescos travem a fila de inferência."""
    if len(text) > max_chars:
        raise SecurityError(
            f"Segmento de texto excede o limite máximo suportado ({len(text)} > {max_chars} caracteres)."
        )


def validate_https_download_url(url: str) -> None:
    """Assegura estritamente que downloads utilizem o protocolo HTTPS criptografado."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise SecurityError(
            f"Protocolo inseguro '{parsed.scheme}' rejeitado. "
            "Apenas downloads autenticados via 'https://' são permitidos para modelos e recursos."
        )
    if not parsed.netloc:
        raise SecurityError(f"URL de download malformada ou sem domínio: '{url}'")


def validate_disk_space(
    target_path: Path | str,
    required_bytes: int,
    safety_margin_mb: int = 500,
) -> None:
    """Verifica se há espaço suficiente em disco antes de baixar ou alocar arquivos volumosos."""
    import shutil

    target = Path(target_path)
    target_dir = target if target.is_dir() else target.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(str(target_dir))
        needed = required_bytes + (safety_margin_mb * 1024 * 1024)
        if usage.free < needed:
            raise SecurityError(
                f"Espaço insuficiente em disco em '{target_dir}'. "
                f"Disponível: {usage.free / (1024**3):.2f} GB, "
                f"Necessário: {needed / (1024**3):.2f} GB."
            )
    except OSError:
        pass
