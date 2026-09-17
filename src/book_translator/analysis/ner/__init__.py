"""Subpacote de Reconhecimento de Entidades Nomeadas (NER)."""

from __future__ import annotations

from book_translator.analysis.ner.factory import get_ner_engine
from book_translator.analysis.ner.heuristic_ner import HeuristicNER
from book_translator.analysis.ner.interface import NERInterface, RawEntityMention

__all__ = [
    "NERInterface",
    "RawEntityMention",
    "HeuristicNER",
    "get_ner_engine",
]
