"""Testes da interface de linha de comando (CLI)."""

from __future__ import annotations

import pytest

from book_translator import __version__
from book_translator.cli import build_parser, main


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Valida o comportamento da flag --version."""
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out or __version__ in captured.err


def test_cli_diagnostics_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Valida a execução do comando de diagnóstico."""
    exit_code = main(["--diagnostics"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "BookTranslator - Diagnostico do Sistema" in captured.out
    assert "Python:" in captured.out
    assert "Sistema Operacional:" in captured.out
    assert "Diretório Base:" in captured.out


def test_cli_default_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Verifica se executar sem argumentos exibe a mensagem de ajuda."""
    exit_code = main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()
