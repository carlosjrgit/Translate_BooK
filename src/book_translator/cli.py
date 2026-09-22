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
    parser.add_argument(
        "--setup-models",
        action="store_true",
        help="Executa o assistente de varredura de hardware e download guiado do MADLAD-400.",
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


def interactive_setup_models() -> int:
    """Assistente CLI interativo para varredura e download do modelo MADLAD-400."""
    from book_translator.system import HardwareProfiler, ModelManager

    print("=" * 65)
    print("Translate Book CJrTools — Assistente de Modelos de IA")
    print("=" * 65)

    manager = ModelManager()
    profiler = HardwareProfiler()
    profile = profiler.profile()

    print("\n[Diagnostico do Hardware]")
    print(f"• CPU:         {profile.cpu.brand} ({profile.cpu.logical_cores} núcleos)")
    print(f"• RAM:         {profile.ram.total_gb:.1f} GB total ({profile.ram.available_gb:.1f} GB livre)")
    gpu_desc = f"{profile.gpu.name} ({profile.gpu.vram_total_gb:.1f} GB VRAM)" if profile.gpu.available else "CPU Only (Sem GPU dedicada)"
    print(f"• GPU:         {gpu_desc}")
    print(f"• Disco:       {profile.disk.free_gb:.1f} GB livres em '{profile.disk.path}'")

    installed = manager.list_installed_models()
    if installed:
        print(f"\n[Status Local] Modelos já instalados: {', '.join(installed)}")
    else:
        print("\n[Status Local] Nenhum modelo neural instalado localmente.")

    rec_id = manager.get_recommended_model_id()
    rec_name = "7.2B (Balanced)" if "7b" in rec_id else ("10.7B (Quality)" if "10b" in rec_id else "3B (Economy)")
    print(f"\n>> RECOMENDAÇÃO DO SISTEMA: MADLAD-400 {rec_name}")

    print("\nVersões disponíveis:")
    print("  [1] MADLAD-400 3B (Economy)    ~2.95 GB — Rápido, ideal para CPU/RAM modesta.")
    print("  [2] MADLAD-400 7.2B (Balanced)  ~8.31 GB — Equilíbrio ideal de fidelidade literária.")
    print("  [3] MADLAD-400 10.7B (Quality)  ~10.73 GB — Máxima nuance (requer GPU >=10GB VRAM).")
    print("  [0] Cancelar / Sair")

    default_choice = "2" if "7b" in rec_id else ("3" if "10b" in rec_id else "1")
    prompt_str = f"\nEscolha a versão desejada [1/2/3/0] (Padrão: {default_choice}): "

    try:
        choice = input(prompt_str).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada pelo usuário.")
        return 0

    if not choice:
        choice = default_choice

    if choice == "0":
        print("Operação cancelada.")
        return 0

    model_map = {
        "1": "madlad400-3b-mt-ct2-int8",
        "2": "madlad400-7b-mt-ct2-int8",
        "3": "madlad400-10b-mt-ct2-int8",
    }

    selected_id = model_map.get(choice)
    if not selected_id:
        print(f"Opção inválida '{choice}'.")
        return 1

    entry = manager.get_model_entry(selected_id)
    if profile.disk.free_gb < entry.total_size_gb:
        print(f"\nERRO: Espaço em disco insuficiente! Requer {entry.total_size_gb:.2f} GB livres.")
        return 1

    print(f"\nIniciando download de {entry.name} ({entry.total_size_gb:.2f} GB)...")

    def _cli_progress(downloaded: int, total: int, percent: float, speed: float, eta: float) -> None:
        bar_len = 30
        filled = int(bar_len * percent // 100)
        bar = "=" * filled + (">" if filled < bar_len else "") + " " * (bar_len - filled - 1)
        down_gb = downloaded / (1024**3)
        tot_gb = total / (1024**3)
        eta_str = f"{int(eta // 60):02d}m{int(eta % 60):02d}s" if eta > 0 else "00m00s"
        sys.stdout.write(
            f"\r[{bar}] {percent:5.1f}% | {down_gb:5.2f}/{tot_gb:5.2f} GB | {speed:5.1f} MB/s | ETA: {eta_str}  "
        )
        sys.stdout.flush()

    try:
        success = manager.download_model(selected_id, on_progress=_cli_progress)
        print()
        if success:
            manager.select_active_model(selected_id)
            print(f"\n[SUCESSO] Modelo '{selected_id}' instalado e verificado com sucesso em '{manager.get_model_dir(selected_id)}'!")
            return 0
        else:
            print("\nDownload cancelado.")
            return 1
    except Exception as exc:
        print(f"\n[ERRO] Falha no download: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada principal da CLI."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.diagnostics:
        return run_diagnostics()

    if args.setup_models:
        return interactive_setup_models()

    # Se nenhum argumento for passado, exibe ajuda
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

