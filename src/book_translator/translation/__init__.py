"""Módulo do motor de tradução e adaptadores de inferência."""

from __future__ import annotations

from book_translator.translation.base import (
    CandidateRankerInterface,
    TranslationCandidate,
    TranslationDraft,
    TranslationEngine,
)
from book_translator.translation.madlad import (
    BackendProtocol,
    CTranslate2Backend,
    DeviceType,
    MadladTranslationEngine,
    MissingModelWeightsError,
    MockMadladBackend,
    QuantizationType,
    RuntimeType,
    TransformersBackend,
)
from book_translator.translation.pipeline import (
    CancellationToken,
    PipelineResult,
    TranslationPipeline,
    TranslationPipelineConfig,
)
from book_translator.translation.ranker import (
    CandidateScoreBreakdown,
    LiteraryCandidateRanker,
    RankingFeatureWeights,
)

__all__ = [
    "TranslationCandidate",
    "TranslationDraft",
    "TranslationEngine",
    "CandidateRankerInterface",
    "BackendProtocol",
    "MadladTranslationEngine",
    "QuantizationType",
    "DeviceType",
    "RuntimeType",
    "MockMadladBackend",
    "CTranslate2Backend",
    "TransformersBackend",
    "MissingModelWeightsError",
    "CancellationToken",
    "TranslationPipelineConfig",
    "PipelineResult",
    "TranslationPipeline",
    "RankingFeatureWeights",
    "CandidateScoreBreakdown",
    "LiteraryCandidateRanker",
]
