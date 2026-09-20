"""Módulo de interface do usuário e acompanhamento de progresso."""

from __future__ import annotations

from book_translator.ui.app import launch_gui
from book_translator.ui.base import ProgressUpdate, UIProgressCallback
from book_translator.ui.components.advanced_panel import AdvancedSettingsPanel
from book_translator.ui.components.analysis_summary_widget import AnalysisSummaryWidget
from book_translator.ui.components.metrics_bar import MetricsBar
from book_translator.ui.components.qa_alerts_widget import QAAlertsWidget
from book_translator.ui.main_window import MainWindow
from book_translator.ui.worker import PipelineWorker

__all__ = [
    "ProgressUpdate",
    "UIProgressCallback",
    "PipelineWorker",
    "MetricsBar",
    "AnalysisSummaryWidget",
    "QAAlertsWidget",
    "AdvancedSettingsPanel",
    "MainWindow",
    "launch_gui",
]
