"""Barra e painel visual de métricas de processamento em tempo real."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from book_translator.ui.theme import (
    COLOR_ACCENT,
    COLOR_BACKGROUND,
    COLOR_BORDER_STRONG,
    COLOR_BORDER_SUBTLE,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_SURFACE_ACTIVE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    RADIUS_DEFAULT,
    RADIUS_SECONDARY,
)


class MetricsBar(QWidget):
    """Componente que exibe fase, capítulo, segmento, barra de progresso, ETA e botões de controle."""

    sig_pause_clicked = Signal()
    sig_resume_clicked = Signal()
    sig_cancel_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_paused = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # Card container técnico com estilo flat
        card = QFrame(self)
        card.setObjectName("metricsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        # Linha 1: Fase atual e Badges de Alertas
        top_row = QHBoxLayout()
        self.lbl_phase = QLabel("Fase: Aguardando início...", self)
        self.lbl_phase.setObjectName("phaseLabel")
        self.lbl_phase.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {COLOR_ACCENT};")
        top_row.addWidget(self.lbl_phase)

        top_row.addStretch()

        self.badge_errors = QLabel("Erros: 0", self)
        self.badge_errors.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ACTIVE}; color: {COLOR_ERROR}; border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 3px 8px; border-radius: {RADIUS_SECONDARY}; font-weight: 600;"
        )
        top_row.addWidget(self.badge_errors)

        self.badge_warnings = QLabel("Avisos: 0", self)
        self.badge_warnings.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ACTIVE}; color: {COLOR_WARNING}; border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 3px 8px; border-radius: {RADIUS_SECONDARY}; font-weight: 600;"
        )
        top_row.addWidget(self.badge_warnings)

        card_layout.addLayout(top_row)

        # Linha 2: Barra de Progresso Flat e Geométrica
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLOR_BACKGROUND};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: {RADIUS_SECONDARY};
                text-align: center;
                color: {COLOR_TEXT_PRIMARY};
                font-weight: 600;
                height: 18px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT};
                border-radius: {RADIUS_SECONDARY};
            }}
        """)
        card_layout.addWidget(self.progress_bar)

        # Linha 3: Informações de Capítulo e Segmento
        mid_row = QHBoxLayout()
        self.lbl_chapter = QLabel("Capítulo: —", self)
        self.lbl_chapter.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px;")
        mid_row.addWidget(self.lbl_chapter)

        mid_row.addStretch()

        self.lbl_segment = QLabel("Segmento: —", self)
        self.lbl_segment.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px;")
        mid_row.addWidget(self.lbl_segment)
        card_layout.addLayout(mid_row)

        # Linha 4: Métricas Temporais, Modelo e Controles
        bottom_row = QHBoxLayout()
        self.lbl_elapsed = QLabel("Tempo decorrido: 00:00", self)
        self.lbl_elapsed.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        bottom_row.addWidget(self.lbl_elapsed)

        bottom_row.addSpacing(16)

        self.lbl_eta = QLabel("Estimativa restante: Calculando...", self)
        self.lbl_eta.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        bottom_row.addWidget(self.lbl_eta)

        bottom_row.addSpacing(16)

        self.lbl_model_usage = QLabel("Modelo: Aguardando", self)
        self.lbl_model_usage.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        bottom_row.addWidget(self.lbl_model_usage)

        bottom_row.addStretch()

        # Botão Pausar/Continuar
        self.btn_pause = QPushButton("Pausar", self)
        self.btn_pause.setFixedWidth(90)
        self.btn_pause.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                font-weight: 500;
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: {RADIUS_DEFAULT};
                padding: 4px 10px;
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_ACTIVE};
                border: 1px solid {COLOR_BORDER_STRONG};
            }}
        """)
        self.btn_pause.clicked.connect(self._toggle_pause)
        bottom_row.addWidget(self.btn_pause)

        # Botão Cancelar
        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE_ELEVATED};
                color: {COLOR_ERROR};
                font-weight: 500;
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: {RADIUS_DEFAULT};
                padding: 4px 10px;
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_ACTIVE};
                border: 1px solid {COLOR_ERROR};
            }}
        """)
        self.btn_cancel.clicked.connect(self.sig_cancel_clicked.emit)
        bottom_row.addWidget(self.btn_cancel)

        card_layout.addLayout(bottom_row)
        main_layout.addWidget(card)

    def _toggle_pause(self) -> None:
        if not self._is_paused:
            self._is_paused = True
            self.btn_pause.setText("Retomar")
            self.btn_pause.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_SURFACE_ELEVATED};
                    color: {COLOR_SUCCESS};
                    font-weight: 600;
                    border: 1px solid {COLOR_SUCCESS};
                    border-radius: {RADIUS_DEFAULT};
                    padding: 4px 10px;
                    min-height: 22px;
                }}
            """)
            self.sig_pause_clicked.emit()
        else:
            self._is_paused = False
            self.btn_pause.setText("Pausar")
            self.btn_pause.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_SURFACE_ELEVATED};
                    color: {COLOR_TEXT_PRIMARY};
                    font-weight: 500;
                    border: 1px solid {COLOR_BORDER_SUBTLE};
                    border-radius: {RADIUS_DEFAULT};
                    padding: 4px 10px;
                    min-height: 22px;
                }}
            """)
            self.sig_resume_clicked.emit()

    def update_phase(self, phase_text: str) -> None:
        self.lbl_phase.setText(f"Fase: {phase_text}")

    def update_progress(
        self,
        current: int,
        total: int,
        percentage: float,
        chapter_info: str,
        segment_info: str,
    ) -> None:
        self.progress_bar.setValue(int(percentage))
        self.progress_bar.setFormat(f"{percentage:.1f}% ({current}/{total})")
        self.lbl_chapter.setText(f"Capítulo: {chapter_info}")
        self.lbl_segment.setText(f"Segmento: {segment_info}")

    def update_metrics(self, elapsed_s: float, eta_str: str, model_usage_str: str) -> None:
        mins = int(elapsed_s // 60)
        secs = int(elapsed_s % 60)
        self.lbl_elapsed.setText(f"Tempo decorrido: {mins:02d}:{secs:02d}")
        self.lbl_eta.setText(f"Estimativa restante: {eta_str}")
        self.lbl_model_usage.setText(f"Uso: {model_usage_str}")

    def update_counters(self, errors: int, warnings: int) -> None:
        self.badge_errors.setText(f"Erros: {errors}")
        self.badge_warnings.setText(f"Avisos: {warnings}")

    def reset(self) -> None:
        self.progress_bar.setValue(0)
        self.lbl_phase.setText("Fase: Aguardando início...")
        self.lbl_chapter.setText("Capítulo: —")
        self.lbl_segment.setText("Segmento: —")
        self.lbl_elapsed.setText("Tempo decorrido: 00:00")
        self.lbl_eta.setText("Estimativa restante: Calculando...")
        self.badge_errors.setText("Erros: 0")
        self.badge_warnings.setText("Avisos: 0")
        self._is_paused = False
        self.btn_pause.setText("Pausar")
