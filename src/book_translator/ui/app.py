"""Inicializador da aplicação de interface gráfica (GUI)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from book_translator.logging import get_logger
from book_translator.ui.main_window import MainWindow

logger = get_logger("ui.app")


def launch_gui(argv: list[str] | None = None) -> int:
    """Inicia a aplicação gráfica PySide6 configurada com tema escuro e DPI responsivo."""
    args = argv if argv is not None else sys.argv
    app = QApplication.instance()
    if app is None:
        app = QApplication(args)

    app.setApplicationName("Translate Book CJrTools")
    app.setOrganizationName("CJrTools")

    # Varredura preventiva: se nenhum modelo homologado estiver instalado localmente,
    # executa o assistente inicial (ModelSetupDialog) com diagnóstico e recomendação
    from book_translator.system.model_manager import ModelManager
    from book_translator.ui.components.model_setup_dialog import ModelSetupDialog

    model_manager = ModelManager()
    if not model_manager.is_any_model_installed():
        logger.info("Nenhum modelo neural instalado localmente. Exibindo assistente de download...")
        dialog = ModelSetupDialog(model_manager=model_manager)
        dialog.exec()

    window = MainWindow(model_manager=model_manager)
    window.show()

    logger.info("Interface Gráfica PySide6 iniciada com sucesso.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(launch_gui())
