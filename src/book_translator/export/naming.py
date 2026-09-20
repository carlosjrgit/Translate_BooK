"""Utilitários para nomeação segura e proteção contra sobrescrita de arquivos originais."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


class OutputOverwriteError(Exception):
    """Exceção levantada quando o destino pretendido sobrescreveria o arquivo original."""


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Higieniza uma string para uso seguro como nome de arquivo em Windows, Linux e macOS.

    Remove caracteres proibidos: < > : " / \\ | ? * e caracteres de controle.
    """
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = re.sub(r"\.{2,}", ".", sanitized)
    sanitized = sanitized.strip(". ")
    if not sanitized:
        sanitized = "documento"
    return sanitized[:max_length]


def validate_safe_output_path(
    output_path: str | Path,
    original_source_path: str | Path | None = None,
) -> None:
    """Garante que o caminho de saída nunca coincida com o caminho do arquivo original."""
    if not original_source_path:
        return

    out_p = Path(output_path).resolve()
    orig_p = Path(original_source_path).resolve()

    if out_p == orig_p:
        raise OutputOverwriteError(
            f"Violação de segurança: O caminho de exportação '{out_p}' coincide exatamente com o arquivo original."
        )


def generate_safe_output_path(
    source_reference: str | Path,
    output_dir: str | Path,
    format_name: str,
    suffix: str = "PT-BR",
) -> Path:
    """Gera um caminho seguro para o arquivo exportado sem jamais sobrescrever o original.

    Formato padrão: <base_name>_<suffix>.<ext>
    Caso o arquivo de destino já exista, inclui timestamp/contador para evitar colisão.
    """
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if hasattr(source_reference, "title"):
        # Se for um objeto Document
        title = getattr(source_reference, "title", "documento")
        raw_name = title or "documento"
        src_file = getattr(getattr(source_reference, "metadata", None), "source_file_path", None)
        source_path = Path(src_file).resolve() if src_file else None
    elif isinstance(source_reference, Path):
        raw_name = source_reference.stem
        source_path = source_reference.resolve()
    else:
        ref_str = str(source_reference)
        raw_name = Path(ref_str).stem if "." in ref_str else ref_str
        source_path = None

    clean_base = sanitize_filename(raw_name)
    clean_ext = format_name.lower().lstrip(".")

    target_candidate = out_dir / f"{clean_base}_{suffix}.{clean_ext}"

    # Regra Fundamental: NUNCA sobrescrever o arquivo de entrada original
    is_same_as_original = source_path is not None and target_candidate.resolve() == source_path

    if not target_candidate.exists() and not is_same_as_original:
        return target_candidate

    # Se colidir com arquivo original ou com exportação anterior, adiciona timestamp e contador
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamp_candidate = out_dir / f"{clean_base}_{suffix}_{timestamp}.{clean_ext}"
    if not timestamp_candidate.exists() and (source_path is None or timestamp_candidate.resolve() != source_path):
        return timestamp_candidate

    counter = 1
    while True:
        candidate = out_dir / f"{clean_base}_{suffix}_{timestamp}_{counter:02d}.{clean_ext}"
        if not candidate.exists() and (source_path is None or candidate.resolve() != source_path):
            return candidate
        counter += 1
