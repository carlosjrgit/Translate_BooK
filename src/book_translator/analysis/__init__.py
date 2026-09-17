"""Subpacote de análise global da obra, extração de entidades e memórias preliminares."""

from __future__ import annotations

from book_translator.analysis.alias_resolver import AliasResolver
from book_translator.analysis.base import AnalysisReport, AnalyzerInterface
from book_translator.analysis.book_analyzer import BookAnalyzer
from book_translator.analysis.models import (
    AnalyzedEntity,
    EntityInference,
    EntityOccurrence,
    EntityType,
    Relationship,
)
from book_translator.analysis.ner import (
    HeuristicNER,
    NERInterface,
    RawEntityMention,
    get_ner_engine,
)
from book_translator.analysis.relation_extractor import RelationExtractor

__all__ = [
    "AnalysisReport",
    "AnalyzerInterface",
    "BookAnalyzer",
    "AnalyzedEntity",
    "EntityOccurrence",
    "EntityInference",
    "EntityType",
    "Relationship",
    "AliasResolver",
    "RelationExtractor",
    "NERInterface",
    "RawEntityMention",
    "HeuristicNER",
    "get_ner_engine",
]
