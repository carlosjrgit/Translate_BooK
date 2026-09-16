"""Subpacote de pré-processamento editorial, normalização e segmentação inicial."""

from __future__ import annotations

from book_translator.preprocessing.config import PreprocessingConfig
from book_translator.preprocessing.dehyphenator import Dehyphenator
from book_translator.preprocessing.dialogue_detector import DialogueDetector
from book_translator.preprocessing.normalizer import UnicodeNormalizer
from book_translator.preprocessing.paragraph_reconstructor import (
    ParagraphReconstructor,
    ReconstructedBlock,
)
from book_translator.preprocessing.pipeline import PreprocessingPipeline
from book_translator.preprocessing.repetition_detector import RepetitionDetector
from book_translator.preprocessing.segmenter import InitialSegmenter, SegmentType
from book_translator.preprocessing.structure_analyzer import StructureAnalyzer

__all__ = [
    "PreprocessingConfig",
    "PreprocessingPipeline",
    "UnicodeNormalizer",
    "Dehyphenator",
    "ParagraphReconstructor",
    "ReconstructedBlock",
    "StructureAnalyzer",
    "DialogueDetector",
    "RepetitionDetector",
    "InitialSegmenter",
    "SegmentType",
]
