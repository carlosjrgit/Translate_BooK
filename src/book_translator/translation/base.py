"""Contratos e modelos fundamentais do motor de tradução (Translation Engine)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from book_translator.context.base import TranslationContext
from book_translator.core.models import Segment


@dataclass
class TranslationCandidate:
    """Hipótese de tradução gerada pelo motor (usada quando N-best está ativado)."""

    text: str
    score: float = 0.0
    rank: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranslationDraft:
    """Rascunho de tradução gerado para um segmento, contendo alternativas e metadados."""

    segment_id: str
    selected_text: str
    candidates: list[TranslationCandidate] = field(default_factory=list)
    engine_name: str = "madlad-400-10b-mt"
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TranslationEngine(Protocol):
    """Protocolo formal desacoplado para qualquer motor de tradução linguística."""

    @property
    def engine_name(self) -> str:
        """Nome ou identificador do modelo/adaptador em uso."""
        ...

    def is_ready(self) -> bool:
        """Indica se o modelo/runtime está carregado e pronto para inferência."""
        ...

    def translate_segment(
        self,
        segment: Segment,
        context: TranslationContext | None = None,
    ) -> TranslationDraft:
        """Traduz um segmento de texto aplicando o contexto fornecido."""
        ...


@runtime_checkable
class CandidateRankerInterface(Protocol):
    """Protocolo formal para comparadores e ranqueadores de múltiplos candidatos N-best."""

    def rank(
        self,
        candidates: list[TranslationCandidate],
        context: TranslationContext | None = None,
    ) -> TranslationCandidate:
        """Seleciona o candidato com maior fidelidade, naturalidade e coerência."""
        ...
