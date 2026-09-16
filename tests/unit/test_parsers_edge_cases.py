"""Testes de casos limítrofes, imutabilidade de arquivos e salvaguardas dos parsers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from book_translator.errors import IngestionError, ParsingError
from book_translator.ingestion.inspector import IngestionInspector
from book_translator.parsers.factory import get_parser_for_file, parse_document
from book_translator.parsers.txt import TxtParser


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_parsers_never_modify_original_file(tmp_path: Path) -> None:
    """Garante o critério de aceitação: Nenhum parser altera o original."""
    sample_path = tmp_path / "original_book.txt"
    sample_content = "CHAPTER 1\n\nThis is untouched original content.\n"
    sample_path.write_text(sample_content, encoding="utf-8")

    stat_before = sample_path.stat()
    hash_before = compute_sha256(sample_path)

    # Executa o parse
    doc = parse_document(sample_path)
    assert doc is not None

    stat_after = sample_path.stat()
    hash_after = compute_sha256(sample_path)

    assert stat_before.st_mtime == stat_after.st_mtime
    assert stat_before.st_size == stat_after.st_size
    assert hash_before == hash_after
    assert sample_path.read_text(encoding="utf-8") == sample_content


def test_nonexistent_file_error() -> None:
    fake_path = Path("this/file/does_not_exist.txt")
    with pytest.raises((ParsingError, IngestionError)):
        parse_document(fake_path)


def test_directory_as_file_error(tmp_path: Path) -> None:
    with pytest.raises((ParsingError, IngestionError)):
        parse_document(tmp_path)


def test_max_file_size_safety_limit(tmp_path: Path) -> None:
    large_file = tmp_path / "large.txt"
    large_file.write_text("A" * 500, encoding="utf-8")

    # Limita a 100 bytes
    parser = TxtParser(max_file_size_bytes=100)
    with pytest.raises(ParsingError, match="excede o limite"):
        parser.parse(large_file)


def test_unsupported_file_extension(tmp_path: Path) -> None:
    unknown_file = tmp_path / "data.xyz"
    unknown_file.write_bytes(b"\x00\x01\x02\x03")

    with pytest.raises(IngestionError, match="não suportad"):
        get_parser_for_file(unknown_file)


def test_inspector_detect_formats(tmp_path: Path) -> None:
    inspector = IngestionInspector()

    txt_f = tmp_path / "a.txt"
    txt_f.write_text("Hello", encoding="utf-8")
    assert inspector.detect_format(txt_f) == "txt"

    md_f = tmp_path / "b.md"
    md_f.write_text("# Title", encoding="utf-8")
    assert inspector.detect_format(md_f) == "markdown"

    html_f = tmp_path / "c.html"
    html_f.write_text("<html></html>", encoding="utf-8")
    assert inspector.detect_format(html_f) == "html"
