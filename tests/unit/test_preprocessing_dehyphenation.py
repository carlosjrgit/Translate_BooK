"""Testes para correção controlada de hifenização de quebra de linha."""

from __future__ import annotations

from book_translator.preprocessing.config import PreprocessingConfig
from book_translator.preprocessing.dehyphenator import Dehyphenator


def test_standard_word_dehyphenation() -> None:
    dehyphenator = Dehyphenator()

    text = "This is an extraor-\ndinary trans-\nlation engine."
    result = dehyphenator.dehyphenate(text)
    assert result == "This is an extraordinary translation engine."


def test_preserve_compound_words() -> None:
    dehyphenator = Dehyphenator()

    # Compostos legítimos com prefixos conhecidos (well-, self-, co-, etc.)
    text = "He is a well-\nknown author with high self-\nesteem and a co-\nauthor."
    result = dehyphenator.dehyphenate(text)
    assert result == "He is a well-known author with high self-esteem and a co-author."


def test_preserve_capitalized_compounds() -> None:
    dehyphenator = Dehyphenator()

    text = "The Anglo-\nAmerican treaty was signed."
    result = dehyphenator.dehyphenate(text)
    assert result == "The Anglo-American treaty was signed."


def test_soft_hyphen_cleaning() -> None:
    dehyphenator = Dehyphenator()

    # Soft hyphen (\u00ad) no meio do texto
    text = "dis\u00adcov\u00adery of new lands."
    result = dehyphenator.dehyphenate(text)
    assert result == "discovery of new lands."


def test_disabled_dehyphenation() -> None:
    cfg = PreprocessingConfig(fix_hyphenation=False)
    dehyphenator = Dehyphenator(cfg)

    text = "extraor-\ndinary"
    assert dehyphenator.dehyphenate(text) == "extraor-\ndinary"
