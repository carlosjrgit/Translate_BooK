"""Worker em segundo plano (QThread) para orquestração assíncrona do pipeline sem travar a UI."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from book_translator.analysis.book_analyzer import BookAnalyzer
from book_translator.core.models import Document, Segment, SegmentStatus
from book_translator.database.sqlite import SQLiteDatabase
from book_translator.export.manager import ExportManager
from book_translator.logging import get_logger
from book_translator.qa.deterministic import DeterministicQAEngine
from book_translator.translation.pipeline import (
    CancellationToken,
    TranslationPipeline,
)

logger = get_logger("ui.worker")


class PipelineWorkerSignals(QObject):
    """Sinais Qt emitidos de forma thread-safe pelo PipelineWorker para a interface."""

    sig_phase_changed = Signal(str)
    sig_progress = Signal(int, int, float, str, str)  # current, total, percentage, chapter_info, segment_info
    sig_metrics = Signal(float, str, str)  # elapsed_s, eta_str, model_usage_str
    sig_counters = Signal(int, int)  # errors_count, warnings_count
    sig_log = Signal(str, str)  # message, level ('info', 'warning', 'error')

    sig_analysis_finished = Signal(object)  # AnalysisReport
    sig_translation_finished = Signal(object)  # PipelineResult
    sig_qa_finished = Signal(list)  # list of QAIssue or dict
    sig_export_finished = Signal(dict)  # dict[format, Path]
    sig_error = Signal(str)

    sig_paused = Signal()
    sig_resumed = Signal()
    sig_cancelled = Signal()
    sig_finished = Signal()


class PipelineWorker(QThread):
    """Thread de execução isolada para garantir que a UI permaneça sempre responsiva e fluida."""

    def __init__(
        self,
        task_name: str,
        task_kwargs: dict[str, Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.task_name = task_name
        self.task_kwargs = task_kwargs or {}
        self.signals = PipelineWorkerSignals()

        self._cancellation_token = CancellationToken()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Começa não-pausado
        self._is_paused = False

    def pause(self) -> None:
        """Solicita pausa cooperativa na execução."""
        self._pause_event.clear()
        self._is_paused = True
        self.signals.sig_paused.emit()
        self.signals.sig_log.emit("Processamento pausado pelo usuário.", "warning")

    def resume(self) -> None:
        """Retoma a execução previamente pausada."""
        self._pause_event.set()
        self._is_paused = False
        self.signals.sig_resumed.emit()
        self.signals.sig_log.emit("Processamento retomado.", "info")

    def cancel(self) -> None:
        """Solicita cancelamento cooperativo imediato."""
        self._cancellation_token.cancel()
        self._pause_event.set()  # Destrava se estiver pausado para permitir saída limpa
        self.signals.sig_cancelled.emit()
        self.signals.sig_log.emit("Cancelamento solicitado pelo usuário.", "warning")

    def run(self) -> None:
        """Ponto de entrada da thread de processamento."""
        try:
            if self.task_name == "analyze":
                self._run_analyze()
            elif self.task_name == "translate":
                self._run_translate()
            elif self.task_name == "qa":
                self._run_qa()
            elif self.task_name == "export":
                self._run_export()
            else:
                raise ValueError(f"Tarefa desconhecida para PipelineWorker: '{self.task_name}'")
        except Exception as exc:
            logger.error(f"Erro no worker ({self.task_name}): {exc}", exc_info=True)
            self.signals.sig_error.emit(str(exc))
        finally:
            self.signals.sig_finished.emit()

    def _wait_if_paused_or_cancelled(self) -> bool:
        """Retorna False se o cancelamento foi requisitado."""
        if self._cancellation_token.is_cancelled:
            return False
        self._pause_event.wait()
        return not self._cancellation_token.is_cancelled

    def _run_analyze(self) -> None:
        self.signals.sig_phase_changed.emit("Analisando obra")
        self.signals.sig_log.emit("Iniciando varredura e análise estrutural da obra...", "info")

        document: Document = self.task_kwargs["document"]
        analyzer = BookAnalyzer()
        report = analyzer.analyze(document)

        self.signals.sig_analysis_finished.emit(report)
        self.signals.sig_log.emit(
            f"Análise concluída: {len(report.entities)} entidades, "
            f"{len(report.recurrent_concepts)} conceitos-chave identificados.",
            "info",
        )

    def _run_translate(self) -> None:
        self.signals.sig_phase_changed.emit("Traduzindo obra")
        self.signals.sig_log.emit("Iniciando pipeline de tradução com MADLAD-400...", "info")

        db: SQLiteDatabase = self.task_kwargs["db"]
        pipeline: TranslationPipeline = self.task_kwargs["pipeline"]
        project_id: str = self.task_kwargs["project_id"]
        model_name: str = getattr(pipeline.translation_engine, "model_name", "MADLAD-400")

        doc = db.load_document(project_id)
        if not doc or not doc.chapters:
            self.signals.sig_error.emit("Nenhum capítulo encontrado no projeto para tradução.")
            return

        all_segments: list[tuple[str, Segment]] = []
        for ch in sorted(doc.chapters, key=lambda c: c.order):
            segs = db.get_segments_by_chapter(ch.id)
            for s in sorted(segs, key=lambda x: x.sequence_order):
                all_segments.append((ch.title or f"Capítulo {ch.order}", s))

        total_segments = len(all_segments)
        start_time = time.perf_counter()
        completed_count = sum(1 for _, s in all_segments if s.is_translated)
        recent_durations: list[float] = []
        errors_count = 0
        warnings_count = 0

        model_usage_str = f"{model_name} | Runtime: INT8"

        for idx, (ch_title, seg) in enumerate(all_segments, start=1):
            if not self._wait_if_paused_or_cancelled():
                self.signals.sig_log.emit("Tradução cancelada cooperativamente.", "warning")
                return

            seg_t0 = time.perf_counter()

            if not seg.is_translated:
                try:
                    # Executa tradução do segmento
                    target_text = pipeline.translation_engine.translate_segment(
                        seg.original_text,
                        source_language="en",
                        target_language="pt-BR",
                    )
                    seg.translated_text = target_text
                    seg.status = SegmentStatus.TRANSLATED
                    db.save_segment(seg)
                    completed_count += 1
                except Exception as exc:
                    errors_count += 1
                    self.signals.sig_log.emit(f"Erro no segmento {seg.id}: {exc}", "error")
                    self.signals.sig_counters.emit(errors_count, warnings_count)

            seg_duration = time.perf_counter() - seg_t0
            recent_durations.append(seg_duration)
            if len(recent_durations) > 15:
                recent_durations.pop(0)

            elapsed_s = time.perf_counter() - start_time
            percent = (idx / total_segments) * 100.0 if total_segments > 0 else 0.0

            # Cálculo de ETA embasado
            if len(recent_durations) >= 5 and elapsed_s >= 2.0:
                avg_sec_per_seg = sum(recent_durations) / len(recent_durations)
                remaining_segs = total_segments - idx
                eta_s = remaining_segs * avg_sec_per_seg
                eta_mins = int(eta_s // 60)
                eta_secs = int(eta_s % 60)
                eta_str = f"{eta_mins:02d}:{eta_secs:02d}"
            else:
                eta_str = "Calculando..."

            chapter_info = ch_title
            segment_info = f"Segmento {idx} de {total_segments}"

            self.signals.sig_progress.emit(idx, total_segments, percent, chapter_info, segment_info)
            self.signals.sig_metrics.emit(elapsed_s, eta_str, model_usage_str)
            self.signals.sig_counters.emit(errors_count, warnings_count)

        self.signals.sig_translation_finished.emit({
            "status": "completed",
            "total_segments": total_segments,
            "completed_segments": completed_count,
            "elapsed_s": time.perf_counter() - start_time,
        })
        self.signals.sig_log.emit("Tradução de todos os capítulos finalizada com sucesso.", "info")

    def _run_qa(self) -> None:
        self.signals.sig_phase_changed.emit("Revisão automática (QA)")
        self.signals.sig_log.emit("Iniciando controle de qualidade determinístico e semântico...", "info")

        db: SQLiteDatabase = self.task_kwargs["db"]
        project_id: str = self.task_kwargs["project_id"]

        doc = db.load_document(project_id)
        if not doc:
            self.signals.sig_error.emit("Documento não encontrado para QA.")
            return

        validator = DeterministicQAEngine()
        all_issues: list[dict[str, Any]] = []
        errors_count = 0
        warnings_count = 0

        for ch in doc.chapters:
            segs = db.get_segments_by_chapter(ch.id)
            for seg in segs:
                if not self._wait_if_paused_or_cancelled():
                    return
                if seg.translated_text:
                    report = validator.validate(seg)
                    if not report.passed:

                        for issue in report.issues:
                            if issue.severity.value == "review_required":
                                errors_count += 1
                            else:
                                warnings_count += 1

                            all_issues.append({
                                "chapter": ch.title or ch.id,
                                "segment_id": seg.id,
                                "check_type": issue.check_type,
                                "severity": issue.severity.value,
                                "description": issue.description,
                                "original": issue.original_snippet or seg.original_text,
                                "translated": issue.translated_snippet or seg.translated_text,
                                "suggested_fix": issue.suggested_fix,
                            })

        self.signals.sig_counters.emit(errors_count, warnings_count)
        self.signals.sig_qa_finished.emit(all_issues)
        self.signals.sig_log.emit(
            f"Revisão QA concluída: {len(all_issues)} alertas identificados.",
            "info" if not all_issues else "warning",
        )

    def _run_export(self) -> None:
        self.signals.sig_phase_changed.emit("Exportando documento")
        self.signals.sig_log.emit("Iniciando exportação determinística...", "info")

        document: Document = self.task_kwargs["document"]
        output_dir: Path = Path(self.task_kwargs["output_dir"])
        formats: list[str] = self.task_kwargs.get("formats", ["txt", "docx", "epub"])

        manager = ExportManager()
        results = manager.export_all(document, output_dir, formats=formats)

        self.signals.sig_export_finished.emit(results)
        self.signals.sig_log.emit(
            f"Exportação concluída com sucesso para os formatos: {list(results.keys())}.",
            "info",
        )
