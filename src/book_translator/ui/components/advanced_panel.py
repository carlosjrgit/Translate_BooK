"""Painel colapsável de configurações para o Modo Avançado, isolado do fluxo comum."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class AdvancedSettingsPanel(QWidget):
    """Configurações avançadas para usuários técnicos e editores seniores."""

    sig_settings_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        group = QGroupBox("Configurações do Modo Avançado", self)
        form = QFormLayout(group)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        # 1. Diretório de Modelos
        dir_row = QHBoxLayout()
        self.txt_model_dir = QLineEdit(".models", self)
        self.txt_model_dir.setReadOnly(True)
        dir_row.addWidget(self.txt_model_dir)

        btn_browse_model = QPushButton("Alterar Pasta...", self)
        btn_browse_model.clicked.connect(self._select_models_dir)
        dir_row.addWidget(btn_browse_model)
        form.addRow("Diretório de Pesos:", dir_row)

        # 2. Orçamento de Contexto (Context Budget Tokens)
        self.spin_context_tokens = QSpinBox(self)
        self.spin_context_tokens.setRange(256, 4096)
        self.spin_context_tokens.setValue(1024)
        self.spin_context_tokens.setSingleStep(128)
        form.addRow("Orçamento de Contexto (Tokens):", self.spin_context_tokens)

        # 3. Beam Size para decodificação
        self.spin_beam_size = QSpinBox(self)
        self.spin_beam_size.setRange(1, 8)
        self.spin_beam_size.setValue(4)
        form.addRow("Beam Size (Largura de Feixe):", self.spin_beam_size)

        # 4. Número de Candidatos N-Best
        self.spin_nbest = QSpinBox(self)
        self.spin_nbest.setRange(1, 5)
        self.spin_nbest.setValue(1)
        form.addRow("Candidatos N-Best Gerados:", self.spin_nbest)

        # 5. Módulo OCR
        ocr_row = QHBoxLayout()
        self.chk_ocr_enabled = QCheckBox("Habilitar OCR para PDFs escaneados", self)
        self.chk_ocr_enabled.setChecked(True)
        ocr_row.addWidget(self.chk_ocr_enabled)

        self.combo_ocr_engine = QComboBox(self)
        self.combo_ocr_engine.addItems(["mock", "tesseract"])
        ocr_row.addWidget(self.combo_ocr_engine)
        form.addRow("Módulo de OCR:", ocr_row)

        # 6. Forçar Perfil Específico
        self.combo_profile_override = QComboBox(self)
        self.combo_profile_override.addItems([
            "Automático (Recomendado pelo Hardware Profiler)",
            "Economy (INT8 / CPU)",
            "Balanced (Equilibrado / GPU Média)",
            "Quality (Máxima Fidelidade / GPU Alta)",
        ])
        form.addRow("Substituir Perfil de Hardware:", self.combo_profile_override)

        layout.addWidget(group)

    def _select_models_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar Diretório de Armazenamento de Modelos")
        if folder:
            self.txt_model_dir.setText(folder)

    def get_settings(self) -> dict:
        return {
            "model_dir": self.txt_model_dir.text(),
            "context_tokens": self.spin_context_tokens.value(),
            "beam_size": self.spin_beam_size.value(),
            "nbest": self.spin_nbest.value(),
            "ocr_enabled": self.chk_ocr_enabled.isChecked(),
            "ocr_engine": self.combo_ocr_engine.currentText(),
            "profile_override": self.combo_profile_override.currentText(),
        }
