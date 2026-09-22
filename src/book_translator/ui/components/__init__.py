"""Componentes de interface gráfica reutilizáveis do Translate Book CJrTools."""

from book_translator.ui.components.about_widget import AboutWidget
from book_translator.ui.components.advanced_panel import AdvancedSettingsPanel
from book_translator.ui.components.analysis_summary_widget import AnalysisSummaryWidget
from book_translator.ui.components.metrics_bar import MetricsBar
from book_translator.ui.components.model_setup_dialog import ModelSetupDialog
from book_translator.ui.components.promote_entities_dialog import PromoteEntitiesDialog
from book_translator.ui.components.qa_alerts_widget import QAAlertsWidget
from book_translator.ui.components.segment_edit_dialog import SegmentEditDialog

__all__ = [
    "AboutWidget",
    "AdvancedSettingsPanel",
    "AnalysisSummaryWidget",
    "MetricsBar",
    "ModelSetupDialog",
    "PromoteEntitiesDialog",
    "QAAlertsWidget",
    "SegmentEditDialog",
]


