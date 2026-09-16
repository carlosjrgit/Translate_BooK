"""Configuração e utilitários de logging centralizado para o BookTranslator."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int | str = logging.INFO,
    log_file: Path | str | None = None,
    log_format: str = DEFAULT_LOG_FORMAT,
) -> logging.Logger:
    """Configura e retorna o logger raiz da aplicação."""
    root_logger = logging.getLogger("book_translator")
    root_logger.setLevel(level)

    # Evita duplicação de handlers se chamada múltiplas vezes
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = logging.Formatter(fmt=log_format, datefmt=DEFAULT_DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Arquivo de log opcional
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Obtém um logger nomeado sob o namespace book_translator."""
    if name.startswith("book_translator."):
        return logging.getLogger(name)
    return logging.getLogger(f"book_translator.{name}")
