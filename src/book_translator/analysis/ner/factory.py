"""Fábrica para obtenção de instâncias de motores de NER."""

from __future__ import annotations

from book_translator.analysis.ner.heuristic_ner import HeuristicNER
from book_translator.analysis.ner.interface import NERInterface
from book_translator.errors import ConfigurationError


def get_ner_engine(engine_name: str = "heuristic") -> NERInterface:
    """Retorna uma instância do motor de NER configurado."""
    normalized = engine_name.lower().strip()
    if normalized == "heuristic":
        return HeuristicNER()

    raise ConfigurationError(
        f"Motor de NER '{engine_name}' não suportado ou ainda não configurado."
    )
