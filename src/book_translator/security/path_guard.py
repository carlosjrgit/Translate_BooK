"""Guarda de segurança para validação e sanitização estrita de caminhos de arquivos."""

from __future__ import annotations

import os
from pathlib import Path


class SecurityError(Exception):
    """Exceção levantada quando uma violação de segurança ou integridade é detectada."""


def sanitize_filename_strict(name: str, max_length: int = 120) -> str:
    """Higieniza o nome de arquivo rejeitando terminantemente caracteres perigosos e separadores.

    Remove barras, contrabarras, dois-pontos, caracteres de controle e sequências nulas.
    """
    if "\x00" in name:
        raise SecurityError("Tentativa de injeção de byte nulo detectada no nome do arquivo.")

    # Remove qualquer tentativa de caminho relativo ou absoluto
    clean_name = os.path.basename(name.replace("\\", "/"))
    # Remove caracteres reservados em sistemas de arquivos
    clean_name = "".join(c for c in clean_name if c.isalnum() or c in ("-", "_", ".", " "))
    clean_name = clean_name.strip(". ")
    if not clean_name:
        clean_name = "documento_seguro"
    return clean_name[:max_length]


def validate_safe_path(
    target_path: Path | str,
    base_dir: Path | str | None = None,
    must_exist: bool = False,
) -> Path:
    """Valida se o caminho informado é seguro contra ataques de Directory Traversal (Path Traversal).

    Se base_dir for informado, garante rigorosamente que o caminho resolvido resida dentro de base_dir.
    """
    raw_str = str(target_path)
    if "\x00" in raw_str:
        raise SecurityError(f"Caminho inseguro com byte nulo: '{raw_str}'")

    path = Path(target_path)

    # Detecção preventiva de tentativa de traversal explícito
    parts = path.parts
    if ".." in parts:
        # Se ultrapassar o diretório base pretendido
        if base_dir is not None:
            resolved_base = Path(base_dir).resolve()
            try:
                resolved_target = (resolved_base / path).resolve()
                if not resolved_target.is_relative_to(resolved_base):
                    raise SecurityError(
                        f"Ataque de Directory Traversal detectado: '{raw_str}' "
                        f"escapa do diretório base '{resolved_base}'"
                    )
            except ValueError:
                raise SecurityError(
                    f"Ataque de Directory Traversal detectado: '{raw_str}' tenta escapar da raiz permitida."
                )

    resolved = path.resolve()

    if base_dir is not None:
        resolved_base = Path(base_dir).resolve()
        try:
            if not resolved.is_relative_to(resolved_base):
                raise SecurityError(
                    f"Acesso negado: o caminho '{resolved}' está fora do diretório autorizado '{resolved_base}'."
                )
        except ValueError:
            raise SecurityError(
                f"Acesso negado: o caminho '{resolved}' não pertence à árvore '{resolved_base}'."
            )

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Arquivo ou diretório validado não existe: {resolved}")

    return resolved
