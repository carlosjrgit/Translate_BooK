"""Gerenciamento de configurações e caminhos da aplicação."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

HardwareProfile = Literal["economy", "balanced", "quality", "custom"]


@dataclass
class AppConfig:
    """Configurações centrais do BookTranslator."""

    base_dir: Path = field(default_factory=lambda: Path.cwd())
    projects_dir: Path = field(default_factory=lambda: Path.cwd() / "projects")
    models_dir: Path = field(default_factory=lambda: Path.cwd() / "models")
    cache_dir: Path = field(default_factory=lambda: Path.cwd() / "cache")
    logs_dir: Path = field(default_factory=lambda: Path.cwd() / "logs")

    # Hardware & Performance
    hardware_profile: HardwareProfile = "balanced"
    max_workers: int = 2
    device: Literal["auto", "cuda", "cpu", "rocm"] = "auto"

    # Idiomas padrão
    source_language: str = "en"
    target_language: str = "pt-BR"

    # QA & Revisão
    enable_deterministic_qa: bool = True
    enable_semantic_qa: bool = True
    enable_backtranslation: bool = False
    enable_n_best: bool = False
    n_best_candidates: int = 3

    def ensure_directories(self) -> None:
        """Garante que os diretórios necessários existam."""
        for directory in [self.projects_dir, self.models_dir, self.cache_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)


_global_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Retorna ou inicializa a instância global de configuração."""
    global _global_config
    if _global_config is None:
        _global_config = AppConfig()
    return _global_config


def set_config(config: AppConfig) -> None:
    """Atualiza a configuração global da aplicação."""
    global _global_config
    _global_config = config
