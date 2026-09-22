"""Testes unitários automatizados para a Interface Gráfica e Worker (Prompt 25)."""

import os

import pytest

# Forçar backend offscreen do Qt para execução de testes em ambiente headless/CI
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from book_translator.core.models import (
    Chapter,
    Document,
    DocumentMetadata,
    Paragraph,
)
from book_translator.ui import (
    AdvancedSettingsPanel,
    AnalysisSummaryWidget,
    MainWindow,
    MetricsBar,
    PipelineWorker,
    QAAlertsWidget,
)


@pytest.fixture(scope="session")
def qapp():
    """Garante uma única instância de QApplication para os testes da suíte."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_document() -> Document:
    meta = DocumentMetadata(
        title="O Ateneu",
        author="Raul Pompeia",
        language="en",
    )
    ch1 = Chapter(id="ch_01", title="Capítulo I", order=1)
    ch1.paragraphs = [
        Paragraph(
            id="p_01",
            chapter_id="ch_01",
            raw_text="Vais encontrar o mundo, disse-me meu pai, à porta do colégio.",
            reading_order=1,
        )
    ]
    return Document(id="doc_ui_test", metadata=meta, chapters=[ch1])


def test_main_window_initial_state(qapp):
    """Verifica a inicialização da MainWindow e o estado padrão dos componentes."""
    window = MainWindow()
    assert window.windowTitle().startswith("Translate Book CJrTools")
    assert window.hardware_profile is not None
    assert window.btn_select_file.isEnabled() is True
    assert window.btn_translate.isEnabled() is False  # Desabilitado até carregar obra
    assert window.tabs.count() == 3  # Fluxo Editorial, Modo Avançado e Sobre


def test_metrics_bar_updates_and_signals(qapp):
    """Testa a barra de métricas com atualização de fase, progresso, ETA e sinais."""
    bar = MetricsBar()

    bar.update_phase("Traduzindo capítulo 1")
    assert "Traduzindo capítulo 1" in bar.lbl_phase.text()

    bar.update_progress(
        current=25,
        total=100,
        percentage=25.0,
        chapter_info="Capítulo 1",
        segment_info="Segmento 25 de 100",
    )
    assert bar.progress_bar.value() == 25
    assert "Capítulo 1" in bar.lbl_chapter.text()
    assert "25 de 100" in bar.lbl_segment.text()

    bar.update_metrics(elapsed_s=125.0, eta_str="03:45", model_usage_str="MADLAD-400 (INT8)")
    assert "02:05" in bar.lbl_elapsed.text()
    assert "03:45" in bar.lbl_eta.text()
    assert "MADLAD-400 (INT8)" in bar.lbl_model_usage.text()

    bar.update_counters(errors=1, warnings=2)
    assert "1" in bar.badge_errors.text()
    assert "2" in bar.badge_warnings.text()

    # Sinais de pausa e cancelamento
    paused_events = []
    resumed_events = []
    cancelled_events = []

    bar.sig_pause_clicked.connect(lambda: paused_events.append(True))
    bar.sig_resume_clicked.connect(lambda: resumed_events.append(True))
    bar.sig_cancel_clicked.connect(lambda: cancelled_events.append(True))

    bar.btn_pause.click()
    assert len(paused_events) == 1
    assert bar.btn_pause.text() == "Retomar"

    bar.btn_pause.click()
    assert len(resumed_events) == 1
    assert bar.btn_pause.text() == "Pausar"

    bar.btn_cancel.click()
    assert len(cancelled_events) == 1


def test_analysis_summary_widget_populate(qapp, sample_document: Document):
    """Valida o preenchimento do card de diagnóstico com os dados do livro."""
    widget = AnalysisSummaryWidget()
    widget.populate(sample_document)

    assert "O Ateneu" in widget.lbl_title.text()
    assert "Raul Pompeia" in widget.lbl_author.text()
    assert "Capítulos: 1" in widget.lbl_chapters.text()


def test_qa_alerts_widget_filtering(qapp):
    """Testa a tabela de alertas de QA e a filtragem por severidade."""
    widget = QAAlertsWidget()
    alerts = [
        {
            "chapter": "Capítulo 1",
            "segment_id": "seg_001",
            "severity": "review_required",
            "check_type": "omission",
            "description": "Possível omissão de trecho",
            "suggested_fix": "Verificar original",
        },
        {
            "chapter": "Capítulo 1",
            "segment_id": "seg_002",
            "severity": "suggested_fix",
            "check_type": "spelling",
            "description": "Ortografia duvidosa",
            "suggested_fix": "corrigir",
        },
    ]
    widget.set_alerts(alerts)
    assert widget.tbl_alerts.rowCount() == 2

    # Filtrar por "Revisão Necessária (Crítico)"
    widget.combo_filter.setCurrentText("Revisão Necessária (Crítico)")
    assert widget.tbl_alerts.rowCount() == 1
    assert widget.tbl_alerts.item(0, 1).text() == "seg_001"

    # Filtrar por "Todos os Níveis"
    widget.combo_filter.setCurrentText("Todos os Níveis")
    assert widget.tbl_alerts.rowCount() == 2


def test_advanced_settings_panel(qapp):
    """Verifica a leitura dos parâmetros de feixe, contexto e OCR no painel avançado."""
    panel = AdvancedSettingsPanel()
    settings = panel.get_settings()

    assert settings["context_tokens"] == 1024
    assert settings["beam_size"] == 4
    assert settings["nbest"] == 1
    assert settings["ocr_enabled"] is True
    assert settings["ocr_engine"] in ("mock", "tesseract")


def test_pipeline_worker_cancel(qapp):
    """Garante que o worker cooperativo responde imediatamente ao sinal de cancelamento."""
    worker = PipelineWorker(task_name="invalid_task")
    assert worker._cancellation_token.is_cancelled is False

    worker.cancel()
    assert worker._cancellation_token.is_cancelled is True


def test_main_window_file_ingestion(qapp, tmp_path, monkeypatch):
    """Verifica que a ingestão de arquivo cria o projeto e salva no banco sem erros."""
    from PySide6.QtWidgets import QFileDialog

    sample_txt = tmp_path / "livro_teste.txt"
    sample_txt.write_text("Capítulo 1\nEste é um parágrafo de teste para ingestão.", encoding="utf-8")

    window = MainWindow()
    window.project_manager.base_projects_dir = tmp_path / ".projects"

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(sample_txt), "Documentos Suportados (*.txt)"),
    )

    window._on_select_file()

    assert window.current_project is not None
    assert window.current_document is not None
    assert len(window.current_document.chapters) >= 1
    assert window.btn_analyze.isEnabled() is True
    assert window.btn_translate.isEnabled() is True
    assert window.btn_export.isEnabled() is True

    # Valida que o documento foi persistido no banco com project_id
    saved_doc = window.current_db.load_document(window.current_project.metadata.project_id)
    assert saved_doc is not None
    assert saved_doc.id == window.current_document.id


def test_ingestion_creates_segments(qapp, tmp_path, monkeypatch):
    """Bug #1 — verifica que segmentos sao criados e persistidos no banco durante a ingestao.
    Antes da correcao, count_total_segments retornava 0 porque PreprocessingPipeline
    nunca era chamado em _on_select_file."""
    from PySide6.QtWidgets import QFileDialog

    sample_txt = tmp_path / "sample.txt"
    sample_txt.write_text(
        "Call me Ishmael. Some years ago I thought I would sail about a little.",
        encoding="utf-8",
    )

    window = MainWindow()
    window.project_manager.base_projects_dir = tmp_path / ".projects"

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(sample_txt), "*.txt"),
    )

    window._on_select_file()

    assert window.current_project is not None
    project_id = window.current_project.metadata.project_id

    total = window.current_db.count_total_segments(project_id)
    assert total > 0, (
        f"Bug #1 nao corrigido: nenhum segmento no banco apos ingestao. Total={total}"
    )


def test_translate_segment_uses_correct_api():
    """Bug #2 — translate_segment deve receber Segment e retornar TranslationDraft.
    Antes da correcao, o worker passava seg.original_text (str) com kwargs invalidos."""
    from book_translator.core.models import Segment, SegmentStatus
    from book_translator.translation import MadladTranslationEngine, MockMadladBackend
    from book_translator.translation.base import TranslationDraft

    engine = MadladTranslationEngine(backend=MockMadladBackend())

    seg = Segment(
        id="seg_bug2_test",
        chapter_id="ch_01",
        paragraph_id="p_01",
        sequence_order=1,
        original_text=(
            "dr. john watson sat near the fireplace at 221b baker street, "
            "listening carefully."
        ),
        status=SegmentStatus.PENDING,
    )

    draft = engine.translate_segment(seg)

    assert isinstance(draft, TranslationDraft), (
        f"Esperado TranslationDraft, recebeu {type(draft).__name__}"
    )
    assert draft.selected_text.strip(), "O texto traduzido nao pode estar vazio"
    assert draft.segment_id == seg.id


def test_worker_qa_execution(tmp_path):
    """Garante que o worker executa a etapa de QA sem erro de API ('validate' / 'evaluate')."""
    from book_translator.core.models import (
        Chapter,
        Document,
        Project,
        ProjectMetadata,
        Segment,
        SegmentStatus,
    )
    from book_translator.database import SQLiteDatabase
    from book_translator.ui.worker import PipelineWorker

    db_path = tmp_path / "test_qa.db"
    db = SQLiteDatabase(db_path)
    db.initialize()

    project_id = "test_qa_proj"
    proj = Project(
        metadata=ProjectMetadata(
            project_id=project_id,
            book_title="QA Test Book",
            source_file_path=str(tmp_path / "source.txt"),
            source_file_sha256="1234567890abcdef",
        ),
        project_dir=tmp_path / "proj",
        db_path=db_path,
    )
    db.save_project(proj)

    ch = Chapter(id="ch_01", title="Chapter 1", order=1)
    doc = Document(
        id=project_id,
        title="QA Test Book",
        author="Author",
        source_language="en",
        target_language="pt",
        chapters=[ch],
    )
    db.save_document(doc, project_id=project_id)
    db.save_chapter(ch, document_id=project_id)

    seg = Segment(
        id="seg_qa_01",
        chapter_id="ch_01",
        paragraph_id=None,
        sequence_order=1,
        original_text="There were 42 books on the shelf.",
        translated_text="Havia 24 livros na estante.",
        status=SegmentStatus.TRANSLATED,
    )
    db.save_segment(seg)

    worker = PipelineWorker(
        task_name="qa",
        task_kwargs={"db": db, "project_id": project_id},
    )

    qa_results = []
    counters = []
    worker.signals.sig_qa_finished.connect(lambda issues: qa_results.append(issues))
    worker.signals.sig_counters.connect(lambda e, w: counters.append((e, w)))

    # Executa a rotina do worker diretamente
    worker._run_qa()

    assert len(qa_results) == 1
    issues = qa_results[0]
    # Deve detectar a divergência do número (42 vs 24)
    assert any(i["check_type"] == "number_mismatch" for i in issues)
    assert len(counters) == 1
    assert counters[0][0] >= 1  # review_required errors_count
