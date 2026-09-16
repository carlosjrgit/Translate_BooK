"""Configurações e fixtures globais de teste."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_translator.config import AppConfig, set_config


@pytest.fixture
def tmp_app_config(tmp_path: Path) -> AppConfig:
    """Fixture que fornece uma configuração isolada em diretório temporário."""
    cfg = AppConfig(
        base_dir=tmp_path,
        projects_dir=tmp_path / "projects",
        models_dir=tmp_path / "models",
        cache_dir=tmp_path / "cache",
        logs_dir=tmp_path / "logs",
    )
    set_config(cfg)
    return cfg
