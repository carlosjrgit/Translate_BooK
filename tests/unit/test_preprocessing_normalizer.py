"""Testes unitários para o normalizador Unicode e sanitização de espaços e controle."""

from __future__ import annotations

from book_translator.preprocessing.config import PreprocessingConfig
from book_translator.preprocessing.normalizer import UnicodeNormalizer


def test_unicode_nfkc_normalization() -> None:
    normalizer = UnicodeNormalizer()

    # Ligatura 'fi' (\ufb01) deve ser decomposta em 'fi'
    text_with_ligature = "The \ufb01nal chapter."
    result = normalizer.normalize(text_with_ligature)
    assert result == "The final chapter."

    # Caracteres acentuados compostos
    decomposed = "e\u0301"  # 'e' + combining acute accent
    assert normalizer.normalize(decomposed) == "é"


def test_control_character_stripping() -> None:
    normalizer = UnicodeNormalizer()

    # Zero-width space (\u200b) e byte order mark (\ufeff)
    text_with_invisibles = "Hello\u200b world!\ufeff\x00\x07"
    result = normalizer.normalize(text_with_invisibles)
    assert result == "Hello world!"


def test_special_spaces_standardization() -> None:
    normalizer = UnicodeNormalizer()

    # Non-breaking space (\u00a0), thin space (\u2009), em space (\u2003)
    text_with_spaces = "Word1\u00a0Word2\u2009Word3\u2003Word4."
    result = normalizer.normalize(text_with_spaces)
    assert result == "Word1 Word2 Word3 Word4."


def test_trailing_whitespace_cleaning() -> None:
    normalizer = UnicodeNormalizer()

    text = "Line 1   \nLine 2\t\t\nLine 3"
    result = normalizer.normalize(text)
    assert result == "Line 1\nLine 2\nLine 3"


def test_quote_standardization_optional() -> None:
    # Por padrão quotes curvas são preservadas
    normalizer_default = UnicodeNormalizer()
    text = "“Hello,” she said, ‘Wait.’"
    assert normalizer_default.normalize(text) == "“Hello,” she said, ‘Wait.’"

    # Se ativado, converte em aspas editoriais ASCII
    cfg = PreprocessingConfig(standardize_quotes=True)
    normalizer_quotes = UnicodeNormalizer(cfg)
    assert normalizer_quotes.normalize(text) == "\"Hello,\" she said, 'Wait.'"


def test_normalize_with_offsets() -> None:
    normalizer = UnicodeNormalizer()
    raw = "Sample text\u00a0here."
    normalized, mapping = normalizer.normalize_with_offsets(raw)

    assert normalized == "Sample text here."
    assert len(mapping) == 1
    assert mapping[0]["raw_end"] == len(raw)
    assert mapping[0]["norm_end"] == len(normalized)
