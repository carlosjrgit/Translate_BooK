"""Módulo de ciclo de vida e gerenciamento de projetos."""

from __future__ import annotations

from book_translator.projects.manager import ProjectManager, compute_file_sha256

__all__ = ["ProjectManager", "compute_file_sha256"]
