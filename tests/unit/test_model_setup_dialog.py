"""Testes unitários para o assistente de instalação de modelos (ModelSetupDialog e CLI)."""

import os
from pathlib import Path

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox

from book_translator.cli import interactive_setup_models
from book_translator.system import (
    DiskInfo,
    HardwareProfiler,
    ModelManager,
)
from book_translator.ui.components.model_setup_dialog import ModelSetupDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_model_setup_dialog_initialization(qapp, tmp_path: Path):
    """Garante inicialização correta do diálogo com diagnóstico e seleção de modelo."""
    models_dir = tmp_path / "models"
    manager = ModelManager(models_dir=models_dir)
    dialog = ModelSetupDialog(model_manager=manager)

    assert dialog.windowTitle() != ""
    assert dialog.stacked_widget.currentIndex() == 0
    assert dialog._selected_model_id in (
        "madlad400-3b-mt-ct2-int8",
        "madlad400-7b-mt-ct2-int8",
        "madlad400-10b-mt-ct2-int8",
    )

    # Verifica que os radio buttons existem
    assert dialog.rb_3b.text().startswith("MADLAD-400 3B")
    assert dialog.rb_7b.text().startswith("MADLAD-400 7.2B")
    assert dialog.rb_10b.text().startswith("MADLAD-400 10.7B")

    # Testa alternância de seleção
    dialog.rb_3b.click()
    assert dialog._selected_model_id == "madlad400-3b-mt-ct2-int8"

    dialog.rb_10b.click()
    assert dialog._selected_model_id == "madlad400-10b-mt-ct2-int8"


def test_model_setup_dialog_progress_update(qapp, tmp_path: Path):
    """Testa atualização dos elementos de telemetria durante o download."""
    manager = ModelManager(models_dir=tmp_path / "models")
    dialog = ModelSetupDialog(model_manager=manager)

    # Simula evento de progresso: 500 MB de 1 GB, 50%, 15 MB/s, 30s ETA
    downloaded = 524288000
    total = 1048576000
    dialog._on_download_progress(downloaded, total, 50.0, 15.0, 30.0)

    assert dialog.progress_bar.value() == 50
    assert "50.0%" in dialog.lbl_metric_size.text()
    assert "15.0 MB/s" in dialog.lbl_metric_speed.text()
    assert "30s" in dialog.lbl_metric_eta.text()


def test_model_setup_dialog_skip_option(qapp, tmp_path: Path, monkeypatch):
    """Testa opção de pular download com confirmação."""
    manager = ModelManager(models_dir=tmp_path / "models")
    dialog = ModelSetupDialog(model_manager=manager)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    dialog._on_skip()
    assert dialog.result() == 0  # QDialog.Rejected


def test_cli_interactive_setup_cancel(monkeypatch, capsys):
    """Testa cancelamento na CLI interativa."""
    monkeypatch.setattr("builtins.input", lambda prompt: "0")
    code = interactive_setup_models()
    assert code == 0
    captured = capsys.readouterr()
    assert "Assistente de Modelos de IA" in captured.out
    assert "Operação cancelada." in captured.out


def test_cli_interactive_setup_insufficient_disk(monkeypatch, tmp_path, capsys):
    """Testa validação de espaço em disco insuficiente na CLI."""
    monkeypatch.setattr("builtins.input", lambda prompt: "1")

    # Força detecção de disco com apenas 0.5 GB livres
    fake_disk = DiskInfo(path=str(tmp_path), total_gb=100.0, used_gb=99.5, free_gb=0.5)
    monkeypatch.setattr(HardwareProfiler, "detect_disk", lambda self, p: fake_disk)

    code = interactive_setup_models()
    assert code == 1
    captured = capsys.readouterr()
    assert "Espaço em disco insuficiente" in captured.out
