"""Testes unitários para os componentes de interface SegmentEditDialog, PromoteEntitiesDialog, QAAlertsWidget e AnalysisSummaryWidget."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QLabel

from book_translator.analysis.base import AnalysisReport
from book_translator.analysis.models import AnalyzedEntity, EntityType
from book_translator.core.models import Document, DocumentMetadata, Segment, SegmentStatus
from book_translator.ui.components.analysis_summary_widget import AnalysisSummaryWidget
from book_translator.ui.components.promote_entities_dialog import PromoteEntitiesDialog
from book_translator.ui.components.qa_alerts_widget import QAAlertsWidget
from book_translator.ui.components.segment_edit_dialog import SegmentEditDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_segment_edit_dialog(qapp):
    """Verifica comportamento do diálogo de edição de segmento e aplicação de sugestão."""
    seg = Segment(
        id="ch_0001_seg_00005",
        chapter_id="ch_0001",
        original_text="Call me Ishmael.",
        translated_text="Chame-me Ishmael.",
        status=SegmentStatus.TRANSLATED,
        sequence_order=5,
        paragraph_id="ch_0001_p_00001",
    )
    alert = {
        "segment_id": "ch_0001_seg_00005",
        "severity": "review_required",
        "check_type": "RepetitionLoop",
        "description": "Loop de repetição detectado.",
        "suggested_fix": "Pode me chamar de Ismael.",
    }

    dlg = SegmentEditDialog(segment=seg, alert_info=alert)
    assert dlg.txt_original.toPlainText() == "Call me Ishmael."
    assert dlg.txt_translated.toPlainText() == "Chame-me Ishmael."
    assert "Palavras: 2" in dlg.lbl_stats.text()

    # Aplica sugestão
    dlg._apply_suggested_fix(alert["suggested_fix"])
    assert dlg.get_translated_text() == "Pode me chamar de Ismael."
    assert "Palavras: 5" in dlg.lbl_stats.text()


def test_promote_entities_dialog(qapp):
    """Verifica seleção e extração de termos no PromoteEntitiesDialog."""
    e1 = AnalyzedEntity(
        id="ent_1",
        canonical_name="Ishmael",
        entity_type=EntityType.CHARACTER,
        gender="male",
    )
    e2 = AnalyzedEntity(
        id="ent_2",
        canonical_name="The Fates",
        entity_type=EntityType.CONCEPT,
        gender="neutral",
    )


    dlg = PromoteEntitiesDialog(entities=[e1, e2], project_id="proj_moby")
    assert dlg.tbl_entities.rowCount() == 2

    # Altera tradução do segundo termo
    dlg.tbl_entities.item(1, 4).setText("As Parcas")

    promoted = dlg.get_promoted_entries()
    assert len(promoted) == 2
    assert promoted[0].source_term == "Ishmael"
    assert promoted[0].target_term == "Ishmael"
    assert promoted[0].locked is True

    assert promoted[1].source_term == "The Fates"
    assert promoted[1].target_term == "As Parcas"
    assert promoted[1].locked is True


def test_qa_alerts_widget_double_click_signal(qapp):
    """Verifica emissão do sinal sig_edit_segment ao dar duplo clique num alerta."""
    widget = QAAlertsWidget()
    alerts = [
        {
            "chapter": "Capítulo 1",
            "segment_id": "ch_0001_seg_00002",
            "severity": "review_required",
            "check_type": "TermConsistency",
            "description": "Termo inconsistente.",
            "suggested_fix": "Termo corrigido.",
        }
    ]
    widget.set_alerts(alerts)
    assert widget.tbl_alerts.rowCount() == 1

    received: list[tuple[str, dict]] = []
    widget.sig_edit_segment.connect(lambda s_id, a_info: received.append((s_id, a_info)))

    # Simula duplo clique na linha 0
    item = widget.tbl_alerts.item(0, 1)
    widget.tbl_alerts.itemDoubleClicked.emit(item)

    assert len(received) == 1
    assert received[0][0] == "ch_0001_seg_00002"
    assert received[0][1]["check_type"] == "TermConsistency"


def test_analysis_summary_widget_promote_signal(qapp):
    """Verifica emissão de sinal do botão de promoção de entidades na análise."""
    widget = AnalysisSummaryWidget()
    doc = Document(
        id="doc1",
        title="Moby-Dick",
        author="Herman Melville",
        metadata=DocumentMetadata(title="Moby-Dick", author="Herman Melville", source_format="txt"),
    )
    e = AnalyzedEntity(id="ent_ahab", canonical_name="Ahab", entity_type=EntityType.CHARACTER)

    report = AnalysisReport(
        entities=[e],
        predominant_narrator="first_person",
        formality_level="formal",
        estimated_tone="philosophical",
    )

    widget.populate(doc, report)
    assert widget.btn_promote.isEnabled() is True

    clicked = []
    widget.sig_promote_entities.connect(lambda: clicked.append(True))
    widget.btn_promote.click()

    assert len(clicked) == 1


def test_about_widget_display(qapp):
    """Verifica se o AboutWidget é instanciado e exibe as informações oficiais de CJRDOOM e versão."""
    from book_translator.ui.components.about_widget import AboutWidget

    about = AboutWidget()
    assert about is not None
    # Verifica presença dos textos oficiais
    labels = [child.text() for child in about.findChildren(QLabel)]
    all_text = " ".join(labels)
    assert "Translate Book CJrTools" in all_text
    assert "Version 1.0.1" in all_text
    assert "CJRDOOM" in all_text
    assert "Carlos Junior" in all_text
