"""Gerenciamento de configurações e caminhos da aplicação."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

HardwareProfile = Literal["economy", "balanced", "quality", "custom"]


@dataclass
class DataDirs:
    """Diretórios canônicos de armazenamento da aplicação."""

    projects_dir: Path
    models_dir: Path
    cache_dir: Path
    logs_dir: Path
    app_dir: Path | None = None

    def __iter__(self):
        return iter((self.projects_dir, self.models_dir, self.cache_dir, self.logs_dir))

    def __getitem__(self, idx):
        return (self.projects_dir, self.models_dir, self.cache_dir, self.logs_dir)[idx]


def get_default_data_dirs() -> DataDirs:
    """Retorna os caminhos canônicos padrão separando executável, dados do usuário e modelos.

    Regra de isolamento Windows:
    - Executável: Diretório de instalação do programa (app_dir).
    - Projetos do usuário: %APPDATA%/Translate_BooK/projects (preservados em desinstalações/upgrades).
    - Modelos e Pesos: %LOCALAPPDATA%/Translate_BooK/models (separados do binário, pesados).
    - Cache e Logs: %LOCALAPPDATA%/Translate_BooK/cache e logs.
    - Portátil: se houver 'portable.txt' ou flag de ambiente, tudo reside junto do executável.
    """
    is_frozen = getattr(sys, "frozen", False)
    app_dir = Path(sys.executable).parent if is_frozen else Path.cwd()
    portable_marker = app_dir / "portable.txt"

    if portable_marker.exists() or os.environ.get("TRANSLATE_BOOK_PORTABLE") == "1":
        base = app_dir
        return DataDirs(
            projects_dir=base / "projects",
            models_dir=base / "models",
            cache_dir=base / "cache",
            logs_dir=base / "logs",
            app_dir=app_dir,
        )

    if is_frozen and sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        localappdata = os.environ.get("LOCALAPPDATA")
        if appdata and localappdata:
            # Novo diretório oficial com compatibilidade transparente a versões anteriores
            roaming = Path(appdata) / "Translate_Book_CJrTools"
            if not roaming.exists() and (Path(appdata) / "Translate_BooK").exists():
                roaming = Path(appdata) / "Translate_BooK"

            local = Path(localappdata) / "Translate_Book_CJrTools"
            if not local.exists() and (Path(localappdata) / "Translate_BooK").exists():
                local = Path(localappdata) / "Translate_BooK"

            return DataDirs(
                projects_dir=roaming / "projects",
                models_dir=local / "models",
                cache_dir=local / "cache",
                logs_dir=local / "logs",
                app_dir=app_dir,
            )

    base = Path.cwd()
    return DataDirs(
        projects_dir=base / "projects",
        models_dir=base / "models",
        cache_dir=base / "cache",
        logs_dir=base / "logs",
        app_dir=app_dir,
    )


@dataclass
class AppConfig:
    """Configurações centrais do BookTranslator."""

    base_dir: Path = field(default_factory=lambda: Path.cwd())
    projects_dir: Path = field(default_factory=lambda: get_default_data_dirs()[0])
    models_dir: Path = field(default_factory=lambda: get_default_data_dirs()[1])
    cache_dir: Path = field(default_factory=lambda: get_default_data_dirs()[2])
    logs_dir: Path = field(default_factory=lambda: get_default_data_dirs()[3])

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
