"""Testes de configuração da aplicação e logging."""

from __future__ import annotations

import logging
from pathlib import Path

from book_translator.config import AppConfig
from book_translator.logging import get_logger, setup_logging


def test_app_config_defaults() -> None:
    """Verifica os valores padrão da configuração."""
    config = AppConfig()
    assert config.hardware_profile == "balanced"
    assert config.device == "auto"
    assert config.source_language == "en"
    assert config.target_language == "pt-BR"
    assert config.enable_deterministic_qa is True
    assert config.enable_semantic_qa is True


def test_app_config_directory_creation(tmp_path: Path) -> None:
    """Valida a criação automática dos diretórios essenciais."""
    config = AppConfig(
        base_dir=tmp_path,
        projects_dir=tmp_path / "p",
        models_dir=tmp_path / "m",
        cache_dir=tmp_path / "c",
        logs_dir=tmp_path / "l",
    )
    config.ensure_directories()
    assert config.projects_dir.exists()
    assert config.models_dir.exists()
    assert config.cache_dir.exists()
    assert config.logs_dir.exists()


def test_logging_setup_and_handlers(tmp_path: Path) -> None:
    """Verifica a inicialização do logging em console e em arquivo."""
    log_file = tmp_path / "test.log"
    logger = setup_logging(level=logging.DEBUG, log_file=log_file)

    assert logger.level == logging.DEBUG
    assert len(logger.handlers) >= 2  # StreamHandler + FileHandler

    sub_logger = get_logger("unit_test")
    sub_logger.info("Mensagem de teste de logging")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Mensagem de teste de logging" in content
