"""Interface de linha de comando (CLI) para diagnósticos e versão."""

from __future__ import annotations

import argparse
import platform
import sys

from book_translator import __version__
from book_translator.config import get_config
from book_translator.logging import get_logger, setup_logging

logger = get_logger("cli")


def build_parser() -> argparse.ArgumentParser:
    """Constrói o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="book-translator",
        description="Tradutor Inteligente de Livros e Documentos EN -> PT-BR",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Exibe a versão instalada do BookTranslator.",
    )
    parser.add_argument(
        "-d",
        "--diagnostics",
        action="store_true",
        help="Executa verificação diagnóstica do ambiente e exibe configurações ativas.",
    )
    return parser


def run_diagnostics() -> int:
    """Gera e exibe relatório de diagnóstico do ambiente de execução."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    config = get_config()
    print("=" * 60)
    print(f"BookTranslator - Diagnostico do Sistema (v{__version__})")
    print("=" * 60)
    print(f"Python:             {platform.python_version()} ({sys.executable})")
    print(f"Sistema Operacional:{platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Diretório Base:     {config.base_dir}")
    print(f"Diretório Projetos: {config.projects_dir}")
    print(f"Diretório Modelos:  {config.models_dir}")
    print(f"Diretório Cache:    {config.cache_dir}")
    print(f"Diretório Logs:     {config.logs_dir}")
    print(f"Perfil de Hardware: {config.hardware_profile}")
    print(f"Dispositivo Padrão: {config.device}")
    print(f"QA Determinístico:  {'Ativado' if config.enable_deterministic_qa else 'Desativado'}")
    print(f"QA Semântico:       {'Ativado' if config.enable_semantic_qa else 'Desativado'}")
    print("-" * 60)

    # Verificação de diretórios
    for name, directory in [
        ("Projetos", config.projects_dir),
        ("Modelos", config.models_dir),
        ("Cache", config.cache_dir),
        ("Logs", config.logs_dir),
    ]:
        exists = directory.exists()
        status = "Existente" if exists else "Não criado (será inicializado sob demanda)"
        print(f"Status [{name}]: {status} ({directory})")

    print("=" * 60)
    print("Diagnóstico concluído com sucesso.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada principal da CLI."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.diagnostics:
        return run_diagnostics()

    # Se nenhum argumento for passado, exibe ajuda
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
