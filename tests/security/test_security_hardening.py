"""Testes unitários e de integração para validação de segurança e hardening."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pytest

from book_translator.errors import ParsingError
from book_translator.parsers.docx import DocxParser
from book_translator.parsers.epub import EpubParser
from book_translator.security import (
    MAX_SEGMENT_CHARACTERS,
    PrivacySanitizingFilter,
    SecurityError,
    is_safe_zip_entry_path,
    safe_parse_xml,
    sanitize_filename_strict,
    validate_file_size_limit,
    validate_https_download_url,
    validate_safe_path,
    validate_segment_size,
    validate_xml_security,
    validate_zip_archive,
)


def test_path_guard_traversal(tmp_path: Path) -> None:
    """Verifica se tentativas de path traversal são bloqueadas."""
    base_dir = tmp_path / "allowed"
    base_dir.mkdir()

    # Caminho válido dentro da base
    safe_file = base_dir / "doc.txt"
    safe_file.touch()
    resolved = validate_safe_path(safe_file, base_dir=base_dir)
    assert resolved == safe_file.resolve()

    # Tentativa de traversal saindo da base
    outside_file = tmp_path / "secret.txt"
    outside_file.touch()
    with pytest.raises(SecurityError, match="está fora do diretório autorizado"):
        validate_safe_path(outside_file, base_dir=base_dir)

    # Nul byte injection
    with pytest.raises(SecurityError, match="byte nulo"):
        validate_safe_path("document\0.txt")


def test_sanitize_filename_strict() -> None:
    """Verifica sanitização rigorosa de nomes de arquivo."""
    unsafe = 'evil/path\\with:bad*chars?"<>|and spaces.txt'
    clean = sanitize_filename_strict(unsafe)
    assert "/" not in clean
    assert "\\" not in clean
    assert ":" not in clean
    assert "*" not in clean
    assert "?" not in clean
    assert '"' not in clean
    assert "<" not in clean
    assert ">" not in clean
    assert "|" not in clean
    assert clean == "withbadcharsand spaces.txt"


def test_zip_guard_zip_slip(tmp_path: Path) -> None:
    """Verifica rejeição de arquivos ZIP contendo Zip Slip."""
    bad_zip = tmp_path / "zip_slip.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../../evil.txt", "malicious payload")

    assert not is_safe_zip_entry_path("../../evil.txt")
    with pytest.raises(SecurityError, match="Zip Slip detectado"):
        validate_zip_archive(bad_zip)


def test_zip_guard_zip_bomb(tmp_path: Path) -> None:
    """Verifica rejeição preventiva de Zip Bombs (alta taxa de compressão / tamanho excedente)."""
    bomb_zip = tmp_path / "zip_bomb.zip"
    with zipfile.ZipFile(bomb_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 2 MB de zeros comprimem para centenas de bytes, gerando alta taxa
        zf.writestr("zero.dat", b"\0" * (2 * 1024 * 1024))

    with pytest.raises(SecurityError, match="Zip Bomb"):
        validate_zip_archive(bomb_zip)


def test_xml_guard_xxe_rejection() -> None:
    """Verifica bloqueio de DTD externa (XXE)."""
    malicious_xxe = """<?xml version="1.0"?>
    <!DOCTYPE foo [
      <!ELEMENT foo ANY >
      <!ENTITY xxe SYSTEM "file:///etc/passwd" >]>
    <foo>&xxe;</foo>"""

    with pytest.raises(SecurityError, match="Vulnerabilidade de XXE bloqueada"):
        validate_xml_security(malicious_xxe)


def test_xml_guard_billion_laughs_rejection() -> None:
    """Verifica bloqueio de Billion Laughs / expansão de entidades."""
    billion_laughs = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ELEMENT lolz (#PCDATA)>
      <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <lolz>&lol1;</lolz>"""

    with pytest.raises(SecurityError, match="Vulnerabilidade de expansão de entidades bloqueada"):
        validate_xml_security(billion_laughs)


def test_xml_guard_safe_parsing() -> None:
    """Verifica que XMLs legítimos são parseados normalmente."""
    safe_xml = "<root><title>O Pequeno Príncipe</title><author>Saint-Exupéry</author></root>"
    root = safe_parse_xml(safe_xml)
    assert root.find("title").text == "O Pequeno Príncipe"


def test_resource_guard_limits(tmp_path: Path) -> None:
    """Verifica validação de limites de tamanho de arquivos e segmentos."""
    huge_file = tmp_path / "huge.txt"
    huge_file.write_bytes(b"A" * 100)

    with pytest.raises(SecurityError, match="excede o limite"):
        validate_file_size_limit(huge_file, max_bytes=50)

    with pytest.raises(SecurityError, match="Segmento de texto excede"):
        validate_segment_size("x" * (MAX_SEGMENT_CHARACTERS + 1))


def test_resource_guard_https_enforcement() -> None:
    """Verifica que apenas HTTPS é aceito para downloads de modelos."""
    validate_https_download_url("https://huggingface.co/model.bin")

    with pytest.raises(SecurityError, match="Protocolo inseguro"):
        validate_https_download_url("http://insecure-site.com/model.bin")

    with pytest.raises(SecurityError, match="Protocolo inseguro"):
        validate_https_download_url("ftp://server.org/model.bin")


def test_privacy_log_sanitizer() -> None:
    """Verifica que caminhos de usuário e tokens são sanitizados nos logs."""
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Iniciando processamento em C:\\Users\\Carlos Jr\\OneDrive\\Área de Trabalho\\Translate_BooK com token hf_1234567890abcdef1234567890abcdef",
        args=(),
        exc_info=None,
    )
    filter_instance = PrivacySanitizingFilter()
    filter_instance.filter(record)

    assert "Carlos Jr" not in record.msg
    assert "[HOME_DIR]" in record.msg
    assert "hf_1234567890abcdef1234567890abcdef" not in record.msg
    assert "***REDACTED_SECRET***" in record.msg


def test_epub_parser_rejects_zip_slip(tmp_path: Path) -> None:
    """Verifica que o EpubParser rejeita arquivos maliciosos com Zip Slip com ParsingError."""
    bad_epub = tmp_path / "malicious.epub"
    with zipfile.ZipFile(bad_epub, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0:")
        zf.writestr("META-INF/container.xml", "<container/>")

    parser = EpubParser()
    with pytest.raises(ParsingError, match="políticas de segurança"):
        parser.parse(bad_epub)


def test_docx_parser_rejects_xxe(tmp_path: Path) -> None:
    """Verifica que o DocxParser rejeita documentos com XML malicioso (XXE)."""
    bad_docx = tmp_path / "malicious.docx"
    xxe_xml = """<?xml version="1.0"?>
    <!DOCTYPE test [ <!ENTITY xxe SYSTEM "file:///etc/hosts"> ]>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body>
    </w:document>"""

    with zipfile.ZipFile(bad_docx, "w") as zf:
        zf.writestr("word/document.xml", xxe_xml)

    parser = DocxParser()
    with pytest.raises(ParsingError, match="inseguro"):
        parser.parse(bad_docx)
