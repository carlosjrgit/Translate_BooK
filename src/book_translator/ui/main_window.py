"""Janela Principal (MainWindow) da Interface Gráfica do Translate_BooK."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from book_translator.core.models import Document
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.logging import get_logger
from book_translator.ocr.engine import MockOcrEngine, OcrService, TesseractOcrEngine
from book_translator.parsers.factory import create_parser
from book_translator.projects.manager import Project, ProjectManager
from book_translator.system.hardware import HardwareProfile, HardwareProfiler
from book_translator.translation import (
    MadladTranslationEngine,
    MockMadladBackend,
    TranslationPipeline,
    TranslationPipelineConfig,
)
from book_translator.ui.components.about_widget import AboutWidget
from book_translator.ui.components.advanced_panel import AdvancedSettingsPanel
from book_translator.ui.components.analysis_summary_widget import AnalysisSummaryWidget
from book_translator.ui.components.metrics_bar import MetricsBar
from book_translator.ui.components.qa_alerts_widget import QAAlertsWidget
from book_translator.ui.theme import (
    APP_STYLESHEET,
    COLOR_ACCENT,
    COLOR_BORDER_SUBTLE,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_PRIMARY,
    COLOR_WARNING,
    FONT_MONOSPACE,
    RADIUS_DEFAULT,
)
from book_translator.ui.worker import PipelineWorker

logger = get_logger("ui.main_window")


class MainWindow(QMainWindow):
    """Interface Gráfica do Translate Book CJrTools cobrindo as 11 etapas do fluxo editorial."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Translate Book CJrTools — Tradução Editorial Profissional (EN -> PT-BR)")
        self.resize(1150, 800)
        self.setMinimumSize(850, 600)
        self.setStyleSheet(APP_STYLESHEET)

        # Estado do Projeto e Pipeline
        self.project_manager = ProjectManager(base_projects_dir=Path(".projects"))
        self.hardware_profiler = HardwareProfiler()
        self.current_project: Project | None = None
        self.current_db: SQLiteDatabase | None = None
        self.current_document: Document | None = None
        self.hardware_profile: HardwareProfile = self.hardware_profiler.profile()
        self.active_worker: PipelineWorker | None = None

        self._setup_ui()
        self._update_hardware_info()

    def _setup_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. Header com Status do Idioma e Hardware
        header_row = QHBoxLayout()
        title_label = QLabel("Translate Book CJrTools", self)
        title_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR_ACCENT}; letter-spacing: 0.5px;")
        header_row.addWidget(title_label)

        header_row.addSpacing(12)
        lang_badge = QLabel("EN ➔ PT-BR", self)
        lang_badge.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: #1A1A1A; font-weight: 600; border-radius: {RADIUS_DEFAULT}; padding: 3px 10px;"
        )
        header_row.addWidget(lang_badge)

        header_row.addStretch()

        self.lbl_hw_badge = QLabel("Hardware: Detectando...", self)
        self.lbl_hw_badge.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; color: {COLOR_SUCCESS}; border: 1px solid {COLOR_BORDER_SUBTLE}; font-weight: 600; border-radius: {RADIUS_DEFAULT}; padding: 4px 10px; font-size: 12px;"
        )
        header_row.addWidget(self.lbl_hw_badge)
        main_layout.addLayout(header_row)

        # 2. Barra Visual de Métricas em Tempo Real
        self.metrics_bar = MetricsBar(self)
        self.metrics_bar.sig_pause_clicked.connect(self._on_pause_requested)
        self.metrics_bar.sig_resume_clicked.connect(self._on_resume_requested)
        self.metrics_bar.sig_cancel_clicked.connect(self._on_cancel_requested)
        main_layout.addWidget(self.metrics_bar)

        # 3. Abas Principais do Fluxo Editorial (Fluxo, Avançado, Sobre)
        self.tabs = QTabWidget(self)

        # Aba 1: Fluxo Principal da Obra
        tab_main = QWidget()
        tab_main_layout = QVBoxLayout(tab_main)
        tab_main_layout.setContentsMargins(8, 8, 8, 8)
        tab_main_layout.setSpacing(10)

        # Seção de Ações das Etapas
        actions_card = QWidget()
        actions_layout = QHBoxLayout(actions_card)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self.btn_select_file = QPushButton("1. Selecionar Arquivo", self)
        self.btn_select_file.setObjectName("primaryAction")
        self.btn_select_file.clicked.connect(self._on_select_file)
        actions_layout.addWidget(self.btn_select_file)

        self.btn_analyze = QPushButton("2. Analisar Obra", self)
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._on_start_analysis)
        actions_layout.addWidget(self.btn_analyze)

        self.btn_translate = QPushButton("3. Traduzir Obra", self)
        self.btn_translate.setObjectName("primaryAction")
        self.btn_translate.setEnabled(False)
        self.btn_translate.clicked.connect(self._on_start_translation)
        actions_layout.addWidget(self.btn_translate)

        self.btn_qa = QPushButton("4. Revisar (QA)", self)
        self.btn_qa.setEnabled(False)
        self.btn_qa.clicked.connect(self._on_start_qa)
        actions_layout.addWidget(self.btn_qa)

        self.btn_export = QPushButton("5. Exportar", self)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export)
        actions_layout.addWidget(self.btn_export)

        tab_main_layout.addWidget(actions_card)

        # Stack de Telas de Conteúdo (Resumo Analítico, Alertas QA, Log)
        self.stacked_views = QStackedWidget(self)

        # View 1: Resumo Analítico da Obra
        self.view_analysis = AnalysisSummaryWidget(self)
        self.stacked_views.addWidget(self.view_analysis)

        # View 2: Tabela de Alertas de QA
        self.view_qa = QAAlertsWidget(self)
        self.stacked_views.addWidget(self.view_qa)

        tab_main_layout.addWidget(self.stacked_views)
        self.tabs.addTab(tab_main, "Fluxo Editorial")

        # Aba 2: Modo Avançado
        self.advanced_panel = AdvancedSettingsPanel(self)
        self.tabs.addTab(self.advanced_panel, "Modo Avançado")

        # Aba 3: Sobre (About) com Logo Oficial CJRDOOM
        self.about_view = AboutWidget(self)
        self.tabs.addTab(self.about_view, "Sobre")

        main_layout.addWidget(self.tabs, stretch=1)

        # 4. Log em Tempo Real Técnico e Monospaçado
        self.log_view = QTextEdit(self)
        self.log_view.setObjectName("logView")
        self.log_view.setMaximumHeight(110)
        self.log_view.setReadOnly(True)
        main_layout.addWidget(self.log_view)

    def _log(self, message: str, level: str = "info") -> None:
        prefix = "[INFO]"
        color = COLOR_TEXT_PRIMARY
        if level == "warning":
            prefix = "[AVISO]"
            color = COLOR_WARNING
        elif level == "error":
            prefix = "[ERRO]"
            color = COLOR_ERROR

        line = f'<span style="color:{color}; font-family:{FONT_MONOSPACE};">{prefix} {message}</span>'
        self.log_view.append(line)

    def _update_hardware_info(self) -> None:
        prof = self.hardware_profile
        rec = prof.recommended_profile.upper()
        gpu_str = f"GPU: {prof.gpu.name}" if prof.gpu.available else "CPU"
        self.lbl_hw_badge.setText(f"Perfil: {rec} ({gpu_str} | RAM {prof.ram.total_gb:.0f}GB)")
        self._log(f"Perfil de hardware detectado: {rec} (Execução local={prof.can_run_local_models})", "info")
        for w in prof.warnings:
            self._log(w, "warning")

    # -------------------------------------------------------------------------
    # Fluxo das 11 Etapas
    # -------------------------------------------------------------------------

    def _on_select_file(self) -> None:
        """Etapas 1-4: Selecionar arquivo, Ingestão, Criar projeto e destino PT-BR."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Obra para Tradução",
            "",
            "Documentos Suportados (*.epub *.docx *.pdf *.txt *.html *.md)",
        )
        if not file_path:
            return

        source = Path(file_path)
        self._log(f"Arquivo selecionado: '{source.name}'", "info")

        try:
            # 2. Criar ou abrir projeto
            proj_title = source.stem.replace("_", " ").title()
            self.current_project, self.current_db = self.project_manager.create_project(
                book_title=proj_title,
                source_file_path=source,
            )
            self._log(f"Projeto criado em '{self.current_project.project_dir.name}' (ID: {self.current_project.metadata.project_id})", "info")

            # 3. Detectar formato e parser
            adv = self.advanced_panel.get_settings()
            ocr_service = None
            if adv.get("ocr_enabled"):
                engine_name = adv.get("ocr_engine", "mock")
                engine = TesseractOcrEngine() if engine_name == "tesseract" else MockOcrEngine()
                ocr_service = OcrService(engine=engine)

            parser = create_parser(source, ocr_service=ocr_service)
            self.current_document = parser.parse(source, title=proj_title)
            self.current_db.save_document(self.current_document)

            self.view_analysis.populate(self.current_document)
            self.stacked_views.setCurrentIndex(0)

            self.btn_analyze.setEnabled(True)
            self.btn_translate.setEnabled(True)
            self.btn_export.setEnabled(True)
            self._log(f"Obra '{self.current_document.title}' carregada: {len(self.current_document.chapters)} capítulos.", "info")

        except Exception as exc:
            logger.error(f"Erro na ingestão do arquivo: {exc}", exc_info=True)
            QMessageBox.critical(self, "Erro na Ingestão", f"Falha ao carregar o arquivo:\n{exc}")
            self._log(f"Falha na seleção: {exc}", "error")

    def _on_start_analysis(self) -> None:
        """Etapas 5-6: Analisar obra e mostrar resumo."""
        if not self.current_document:
            return

        self._start_worker(
            task_name="analyze",
            task_kwargs={"document": self.current_document},
        )

    def _on_start_translation(self) -> None:
        """Etapas 7-8: Escolher perfil e Traduzir com MADLAD-400."""
        if not self.current_project or not self.current_db:
            return

        _adv = self.advanced_panel.get_settings()
        engine = MadladTranslationEngine(backend=MockMadladBackend())

        pipeline = TranslationPipeline(
            db=self.current_db,
            translation_engine=engine,
            config=TranslationPipelineConfig(),
        )

        self._start_worker(
            task_name="translate",
            task_kwargs={
                "db": self.current_db,
                "pipeline": pipeline,
                "project_id": self.current_project.metadata.project_id,
            },
        )

    def _on_start_qa(self) -> None:
        """Etapas 9-10: Revisar automaticamente e mostrar alertas."""
        if not self.current_project or not self.current_db:
            return

        self._start_worker(
            task_name="qa",
            task_kwargs={
                "db": self.current_db,
                "project_id": self.current_project.metadata.project_id,
            },
        )

    def _on_export(self) -> None:
        """Etapa 11: Exportar TXT, DOCX e EPUB de forma segura e determinística."""
        if not self.current_project or not self.current_db:
            return

        doc = self.current_db.load_document(self.current_project.metadata.project_id)
        if not doc:
            doc = self.current_document

        out_dir = self.current_project.project_dir / "output"
        out_dir.mkdir(exist_ok=True)

        self._start_worker(
            task_name="export",
            task_kwargs={
                "document": doc,
                "output_dir": out_dir,
                "formats": ["txt", "docx", "epub"],
            },
        )

    def _start_worker(self, task_name: str, task_kwargs: dict[str, Any]) -> None:
        if self.active_worker and self.active_worker.isRunning():
            QMessageBox.warning(self, "Aguarde", "Uma tarefa já está em execução.")
            return

        self.metrics_bar.reset()
        self.active_worker = PipelineWorker(task_name, task_kwargs, self)

        # Conexão de sinais com a interface
        self.active_worker.signals.sig_phase_changed.connect(self.metrics_bar.update_phase)
        self.active_worker.signals.sig_progress.connect(self.metrics_bar.update_progress)
        self.active_worker.signals.sig_metrics.connect(self.metrics_bar.update_metrics)
        self.active_worker.signals.sig_counters.connect(self.metrics_bar.update_counters)
        self.active_worker.signals.sig_log.connect(self._log)
        self.active_worker.signals.sig_error.connect(self._on_worker_error)

        if task_name == "analyze":
            self.active_worker.signals.sig_analysis_finished.connect(self._on_analysis_finished)
        elif task_name == "translate":
            self.active_worker.signals.sig_translation_finished.connect(self._on_translation_finished)
        elif task_name == "qa":
            self.active_worker.signals.sig_qa_finished.connect(self._on_qa_finished)
        elif task_name == "export":
            self.active_worker.signals.sig_export_finished.connect(self._on_export_finished)

        self.active_worker.start()

    def _on_analysis_finished(self, report: Any) -> None:
        if self.current_document:
            self.view_analysis.populate(self.current_document, report)
            self.stacked_views.setCurrentIndex(0)
        self.btn_translate.setEnabled(True)

    def _on_translation_finished(self, result: Any) -> None:
        self.btn_qa.setEnabled(True)
        QMessageBox.information(
            self,
            "Tradução Concluída",
            f"Tradução concluída com sucesso!\nTotal de segmentos: {result.get('total_segments')}",
        )

    def _on_qa_finished(self, alerts: list) -> None:
        self.view_qa.set_alerts(alerts)
        self.stacked_views.setCurrentIndex(1)
        self.btn_export.setEnabled(True)

    def _on_export_finished(self, results: dict) -> None:
        msg = "Arquivos exportados com sucesso:\n" + "\n".join(
            f"• {fmt.upper()}: {path.name}" for fmt, path in results.items()
        )
        QMessageBox.information(self, "Exportação Concluída", msg)

    def _on_worker_error(self, err_msg: str) -> None:
        QMessageBox.critical(self, "Erro no Pipeline", f"Ocorreu um erro:\n{err_msg}")

    def _on_pause_requested(self) -> None:
        if self.active_worker:
            self.active_worker.pause()

    def _on_resume_requested(self) -> None:
        if self.active_worker:
            self.active_worker.resume()

    def _on_cancel_requested(self) -> None:
        if self.active_worker:
            self.active_worker.cancel()
