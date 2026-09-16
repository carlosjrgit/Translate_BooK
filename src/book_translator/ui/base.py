"""Contratos e modelos para eventos de interface e acompanhamento de progresso."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ProgressUpdate:
    """Evento emitido durante o processamento para feedback ao usuário."""

    phase: str  # ex: 'Analisando obra', 'Traduzindo capítulo 17 de 42'
    current_step: int  # ex: 1483
    total_steps: int  # ex: 3921
    activity_description: str = ""  # ex: 'Validando consistência de personagens...'
    elapsed_seconds: float = 0.0
    errors_count: int = 0
    warnings_count: int = 0

    @property
    def percentage(self) -> float:
        if self.total_steps <= 0:
            return 0.0
        return min(100.0, (self.current_step / self.total_steps) * 100.0)


@runtime_checkable
class UIProgressCallback(Protocol):
    """Protocolo de callback para desacoplar o pipeline das tecnologias de interface."""

    def on_progress(self, update: ProgressUpdate) -> None:
        """Chamado quando há nova atualização de progresso na esteira."""
        ...
