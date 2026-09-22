"""Assistente de inicialização e gerenciador de download de modelos neurais (MADLAD-400)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from book_translator.logging import get_logger
from book_translator.system import HardwareProfile, HardwareProfiler, ModelManager
from book_translator.ui.theme import (
    APP_STYLESHEET,
    COLOR_ACCENT,
    COLOR_BORDER_SUBTLE,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_MONOSPACE,
    RADIUS_DEFAULT,
)

logger = get_logger("ui.model_setup_dialog")


class ModelDownloadWorker(QThread):
    """Thread assíncrona para download de modelos com telemetria em tempo real."""

    sig_progress = Signal(object, object, float, float, float)  # downloaded, total, percent, speed, eta
    sig_finished = Signal(bool, str)

    def __init__(self, model_manager: ModelManager, model_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model_manager = model_manager
        self.model_id = model_id
        self._is_cancelled = False

    def run(self) -> None:
        def _on_progress(downloaded: int, total: int, percent: float, speed: float, eta: float) -> None:
            self.sig_progress.emit(downloaded, total, percent, speed, eta)

        try:
            logger.info(f"Iniciando download assíncrono do modelo '{self.model_id}'...")
            success = self.model_manager.download_model(self.model_id, on_progress=_on_progress)
            if success:
                self.sig_finished.emit(True, f"Modelo '{self.model_id}' baixado e verificado com sucesso!")
            else:
                self.sig_finished.emit(False, "Download cancelado pelo usuário.")
        except Exception as exc:
            logger.error(f"Falha durante o download do modelo '{self.model_id}': {exc}", exc_info=True)
            self.sig_finished.emit(False, str(exc))

    def cancel(self) -> None:
        self._is_cancelled = True
        self.model_manager.cancel_download()


class ModelSetupDialog(QDialog):
    """Diálogo modal de primeiro uso e gerenciamento de modelos MADLAD-400."""

    sig_model_ready = Signal(str)

    def __init__(
        self,
        model_manager: ModelManager | None = None,
        profiler: HardwareProfiler | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuração Inicial — Modelo de Tradução Neural (MADLAD-400)")
        self.resize(760, 600)
        self.setMinimumSize(680, 520)
        self.setStyleSheet(APP_STYLESHEET)

        self.model_manager = model_manager or ModelManager()
        self.profiler = profiler or self.model_manager.profiler
        self.hardware_profile: HardwareProfile = self.profiler.profile()
        self.download_worker: ModelDownloadWorker | None = None

        self._selected_model_id: str = self.model_manager.get_recommended_model_id()

        self._setup_ui()
        self._populate_hardware_info()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        # Cabeçalho
        header_layout = QHBoxLayout()
        title_label = QLabel("Assistente de Instalação de Modelo", self)
        title_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {COLOR_ACCENT};"
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        badge_privacy = QLabel("100% Offline / Local", self)
        badge_privacy.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; color: {COLOR_SUCCESS}; "
            f"border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 4px 10px; border-radius: {RADIUS_DEFAULT}; font-size: 11px;"
        )
        header_layout.addWidget(badge_privacy)
        root_layout.addLayout(header_layout)

        # Stack de Páginas (Página 0: Seleção & Diagnóstico, Página 1: Progresso do Download)
        self.stacked_widget = QStackedWidget(self)

        # --- PÁGINA 0: SELEÇÃO ---
        self.page_selection = QWidget()
        page_sel_layout = QVBoxLayout(self.page_selection)
        page_sel_layout.setContentsMargins(0, 0, 0, 0)
        page_sel_layout.setSpacing(14)

        desc_label = QLabel(
            "Para realizar traduções editoriais de alta fidelidade de forma 100% local, "
            "o sistema necessita dos pesos da IA MADLAD-400. Avaliamos a capacidade da sua máquina "
            "para sugerir a versão mais eficiente, mas você tem total liberdade para escolher:",
            self,
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; line-height: 1.4;")
        page_sel_layout.addWidget(desc_label)

        # Card de Diagnóstico de Hardware
        self.hw_group = QGroupBox("Diagnóstico de Hardware Detectado", self)
        hw_layout = QVBoxLayout(self.hw_group)
        hw_layout.setSpacing(6)

        self.lbl_cpu = QLabel("CPU: Detectando...", self)
        self.lbl_ram = QLabel("Memória RAM: Detectando...", self)
        self.lbl_gpu = QLabel("Placa de Vídeo (GPU): Detectando...", self)
        self.lbl_disk = QLabel("Espaço Livre em Disco: Detectando...", self)

        for lbl in (self.lbl_cpu, self.lbl_ram, self.lbl_gpu, self.lbl_disk):
            lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; font-family: {FONT_MONOSPACE};")
            hw_layout.addWidget(lbl)

        page_sel_layout.addWidget(self.hw_group)

        # Banner de Recomendação
        self.banner_recommendation = QFrame(self)
        self.banner_recommendation.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; border-left: 4px solid {COLOR_ACCENT}; "
            f"border-radius: {RADIUS_DEFAULT}; padding: 8px 12px;"
        )
        banner_layout = QVBoxLayout(self.banner_recommendation)
        banner_layout.setContentsMargins(6, 6, 6, 6)
        self.lbl_rec_title = QLabel("Recomendação para seu sistema:", self)
        self.lbl_rec_title.setStyleSheet(f"font-weight: 700; color: {COLOR_ACCENT}; font-size: 13px;")
        banner_layout.addWidget(self.lbl_rec_title)

        self.lbl_rec_desc = QLabel("", self)
        self.lbl_rec_desc.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        self.lbl_rec_desc.setWordWrap(True)
        banner_layout.addWidget(self.lbl_rec_desc)
        page_sel_layout.addWidget(self.banner_recommendation)

        # Grupo de Escolha de Versão
        models_group = QGroupBox("Selecione a Versão do MADLAD-400 para Baixar", self)
        models_layout = QVBoxLayout(models_group)
        models_layout.setSpacing(10)

        self.btn_group = QButtonGroup(self)

        # Opção 3B (Economy)
        self.rb_3b = QRadioButton("MADLAD-400 3B (Economy) — ~2.95 GB", self)
        self.rb_3b.setProperty("model_id", "madlad400-3b-mt-ct2-int8")
        self.lbl_desc_3b = QLabel(
            "   Ideal para computadores sem placa de vídeo dedicada (execução em CPU) ou com até 8 GB de RAM. Rápido e leve.",
            self,
        )
        self.lbl_desc_3b.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_desc_3b.setWordWrap(True)
        models_layout.addWidget(self.rb_3b)
        models_layout.addWidget(self.lbl_desc_3b)
        self.btn_group.addButton(self.rb_3b)

        # Opção 7B (Balanced)
        self.rb_7b = QRadioButton("MADLAD-400 7.2B (Balanced) — ~8.31 GB", self)
        self.rb_7b.setProperty("model_id", "madlad400-7b-mt-ct2-int8")
        self.lbl_desc_7b = QLabel(
            "   Excelente equilíbrio entre rica fidelidade literária e tempo de inferência. Recomendado para GPUs com 6+ GB VRAM ou 16+ GB RAM.",
            self,
        )
        self.lbl_desc_7b.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_desc_7b.setWordWrap(True)
        models_layout.addWidget(self.rb_7b)
        models_layout.addWidget(self.lbl_desc_7b)
        self.btn_group.addButton(self.rb_7b)

        # Opção 10B (Quality)
        self.rb_10b = QRadioButton("MADLAD-400 10.7B (Quality) — ~10.73 GB", self)
        self.rb_10b.setProperty("model_id", "madlad400-10b-mt-ct2-int8")
        self.lbl_desc_10b = QLabel(
            "   Máxima nuance literária, sintaxe apurada e refinamento editorial. Requer GPU potente com 10+ GB VRAM ou 24+ GB RAM.",
            self,
        )
        self.lbl_desc_10b.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_desc_10b.setWordWrap(True)
        models_layout.addWidget(self.rb_10b)
        models_layout.addWidget(self.lbl_desc_10b)
        self.btn_group.addButton(self.rb_10b)

        self.btn_group.buttonClicked.connect(self._on_model_selection_changed)
        page_sel_layout.addWidget(models_group)

        # Botões de Ação na Página de Seleção
        actions_layout = QHBoxLayout()
        self.btn_skip = QPushButton("Pular por Enquanto (Modo Mock/Teste)", self)
        self.btn_skip.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; color: {COLOR_TEXT_SECONDARY}; border: 1px solid {COLOR_BORDER_SUBTLE};"
        )
        self.btn_skip.clicked.connect(self._on_skip)
        actions_layout.addWidget(self.btn_skip)

        actions_layout.addStretch()

        self.btn_start_download = QPushButton("Baixar e Instalar Modelo", self)
        self.btn_start_download.setObjectName("primaryAction")
        self.btn_start_download.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: #1A1A1A; font-weight: 700; "
            f"padding: 8px 18px; border-radius: {RADIUS_DEFAULT};"
        )
        self.btn_start_download.clicked.connect(self._on_start_download)
        actions_layout.addWidget(self.btn_start_download)

        page_sel_layout.addLayout(actions_layout)
        self.stacked_widget.addWidget(self.page_selection)

        # --- PÁGINA 1: DOWNLOAD EM ANDAMENTO ---
        self.page_download = QWidget()
        page_down_layout = QVBoxLayout(self.page_download)
        page_down_layout.setContentsMargins(0, 0, 0, 0)
        page_down_layout.setSpacing(16)

        page_down_layout.addStretch(1)

        self.lbl_down_title = QLabel("Baixando Modelo de Tradução...", self)
        self.lbl_down_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR_ACCENT};")
        page_down_layout.addWidget(self.lbl_down_title)

        self.lbl_down_status = QLabel("Preparando conexão segura HTTPS e alocando espaço...", self)
        self.lbl_down_status.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        page_down_layout.addWidget(self.lbl_down_status)

        # Barra de Progresso
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER_SUBTLE}; "
            f"border-radius: {RADIUS_DEFAULT}; text-align: center; color: {COLOR_TEXT_PRIMARY}; font-weight: 600; height: 26px; }} "
            f"QProgressBar::chunk {{ background-color: {COLOR_ACCENT}; border-radius: {RADIUS_DEFAULT}; }}"
        )
        page_down_layout.addWidget(self.progress_bar)

        # Métricas de Telemetria (Grid/Colunas)
        metrics_box = QFrame(self)
        metrics_box.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border-radius: {RADIUS_DEFAULT}; padding: 12px;"
        )
        metrics_layout = QHBoxLayout(metrics_box)

        self.lbl_metric_size = QLabel("Baixado: 0.00 GB / 0.00 GB", self)
        self.lbl_metric_speed = QLabel("Velocidade: 0.0 MB/s", self)
        self.lbl_metric_eta = QLabel("Tempo Restante: Calculando...", self)

        for m_lbl in (self.lbl_metric_size, self.lbl_metric_speed, self.lbl_metric_eta):
            m_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-family: {FONT_MONOSPACE}; font-size: 12px;")
            metrics_layout.addWidget(m_lbl)

        page_down_layout.addWidget(metrics_box)

        # Botão Cancelar Download
        down_actions = QHBoxLayout()
        down_actions.addStretch()
        self.btn_cancel_download = QPushButton("Cancelar Download", self)
        self.btn_cancel_download.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; color: {COLOR_ERROR}; border: 1px solid {COLOR_ERROR}; "
            f"padding: 6px 16px; border-radius: {RADIUS_DEFAULT}; font-weight: 600;"
        )
        self.btn_cancel_download.clicked.connect(self._on_cancel_download)
        down_actions.addWidget(self.btn_cancel_download)
        down_actions.addStretch()

        page_down_layout.addLayout(down_actions)
        page_down_layout.addStretch(2)

        self.stacked_widget.addWidget(self.page_download)

        root_layout.addWidget(self.stacked_widget)

    def _populate_hardware_info(self) -> None:
        p = self.hardware_profile
        self.lbl_cpu.setText(f"• CPU: {p.cpu.brand} ({p.cpu.logical_cores} núcleos lógicos)")
        self.lbl_ram.setText(f"• Memória RAM Total: {p.ram.total_gb:.1f} GB (Livre: {p.ram.available_gb:.1f} GB)")

        gpu_txt = f"{p.gpu.name} ({p.gpu.vram_total_gb:.1f} GB VRAM)" if p.gpu.available else "Nenhuma GPU dedicada detectada (Uso de CPU)"
        self.lbl_gpu.setText(f"• Placa de Vídeo: {gpu_txt}")
        self.lbl_disk.setText(f"• Espaço Livre em Disco: {p.disk.free_gb:.1f} GB livres em {p.disk.path}")

        rec = p.recommended_profile
        if rec == "quality":
            self.lbl_rec_desc.setText(
                "Sua máquina possui excelente poder computacional (GPU/RAM de alta performance). "
                "Recomendamos o MADLAD-400 10.7B (Quality) para a melhor fidelidade literária possível."
            )
            self.rb_10b.setChecked(True)
            self._selected_model_id = "madlad400-10b-mt-ct2-int8"
        elif rec == "balanced":
            self.lbl_rec_desc.setText(
                "Seu computador possui recursos intermediários confortáveis. "
                "Recomendamos o MADLAD-400 7.2B (Balanced) para um equilíbrio ideal entre velocidade e qualidade."
            )
            self.rb_7b.setChecked(True)
            self._selected_model_id = "madlad400-7b-mt-ct2-int8"
        else:
            self.lbl_rec_desc.setText(
                "Configuração modesta ou CPU-only detectada. "
                "Recomendamos o MADLAD-400 3B (Economy) para execução estável sem travamentos do sistema."
            )
            self.rb_3b.setChecked(True)
            self._selected_model_id = "madlad400-3b-mt-ct2-int8"

    def _on_model_selection_changed(self, button: QRadioButton) -> None:
        model_id = button.property("model_id")
        if model_id:
            self._selected_model_id = model_id
            logger.info(f"Usuário selecionou modelo: {model_id}")

    def _on_start_download(self) -> None:
        entry = self.model_manager.get_model_entry(self._selected_model_id)

        # Checagem preventiva de espaço
        p = self.profiler.profile()
        if p.disk.free_gb < entry.total_size_gb:
            QMessageBox.critical(
                self,
                "Espaço em Disco Insuficiente",
                f"O modelo '{entry.name}' necessita de pelo menos {entry.total_size_gb:.2f} GB livres, "
                f"mas há apenas {p.disk.free_gb:.2f} GB disponíveis no disco.",
            )
            return

        self.lbl_down_title.setText(f"Baixando {entry.name}...")
        self.progress_bar.setValue(0)
        self.stacked_widget.setCurrentIndex(1)

        self.download_worker = ModelDownloadWorker(self.model_manager, self._selected_model_id, self)
        self.download_worker.sig_progress.connect(self._on_download_progress)
        self.download_worker.sig_finished.connect(self._on_download_finished)
        self.download_worker.start()

    def _on_download_progress(
        self, downloaded: int, total: int, percent: float, speed: float, eta: float
    ) -> None:
        self.progress_bar.setValue(int(percent))

        down_gb = downloaded / (1024**3)
        tot_gb = total / (1024**3)
        self.lbl_metric_size.setText(f"Baixado: {down_gb:.2f} GB / {tot_gb:.2f} GB ({percent:.1f}%)")
        self.lbl_metric_speed.setText(f"Velocidade: {speed:.1f} MB/s")

        if eta > 0:
            minutes = int(eta // 60)
            seconds = int(eta % 60)
            self.lbl_metric_eta.setText(f"Tempo Restante: {minutes:02d}m {seconds:02d}s")
        else:
            self.lbl_metric_eta.setText("Tempo Restante: Concluindo...")

    def _on_download_finished(self, success: bool, message: str) -> None:
        if success:
            try:
                self.model_manager.select_active_model(self._selected_model_id)
            except Exception as e:
                logger.warning(f"Não foi possível definir modelo ativo automaticamente: {e}")

            QMessageBox.information(
                self,
                "Download Concluído",
                f"O modelo {self._selected_model_id} foi baixado e verificado com sucesso!\n"
                "Seu ambiente de tradução local está pronto para uso.",
            )
            self.sig_model_ready.emit(self._selected_model_id)
            self.accept()
        else:
            QMessageBox.warning(self, "Download Não Concluído", f"Aviso:\n{message}")
            self.stacked_widget.setCurrentIndex(0)

    def _on_cancel_download(self) -> None:
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirmar Cancelamento",
                "Deseja realmente pausar/cancelar o download? O progresso já baixado será preservado em arquivos temporários.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.download_worker.cancel()
                self.stacked_widget.setCurrentIndex(0)

    def _on_skip(self) -> None:
        reply = QMessageBox.question(
            self,
            "Pular Download de IA",
            "Sem baixar o modelo MADLAD-400 local, o programa operará em modo de simulação (Mock Engine). "
            "Você poderá baixar o modelo a qualquer momento pela aba 'Modo Avançado'. Deseja prosseguir?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self.reject()
