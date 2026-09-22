"""Diálogo modal para revisão humana e edição direta de segmentos traduzidos."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from book_translator.core.models import Segment
from book_translator.ui.theme import (
    COLOR_ACCENT,
    COLOR_BORDER_SUBTLE,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    FONT_PRIMARY,
    RADIUS_DEFAULT,
)


class SegmentEditDialog(QDialog):
    """Diálogo para o revisor humano inspecionar e editar diretamente um segmento."""

    def __init__(
        self,
        segment: Segment,
        alert_info: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.segment = segment
        self.alert_info = alert_info or {}

        self.setWindowTitle(f"Revisão Humana — Segmento {segment.id}")
        self.resize(780, 560)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # 1. Cabeçalho com identificação do segmento
        header_row = QHBoxLayout()
        lbl_title = QLabel(f"<b>Segmento:</b> {self.segment.id}  |  <b>Capítulo:</b> {self.segment.chapter_id}")
        lbl_title.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_PRIMARY}; font-family: {FONT_PRIMARY};")
        header_row.addWidget(lbl_title)
        header_row.addStretch()

        p_id = getattr(self.segment, "paragraph_id", None)
        if p_id:
            lbl_para = QLabel(f"Parágrafo Canônico: {p_id}")
            lbl_para.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
            header_row.addWidget(lbl_para)

        layout.addLayout(header_row)

        # 2. Painel de Alerta de QA (se houver alerta associado)
        if self.alert_info:
            alert_card = QFrame(self)
            alert_card.setStyleSheet(
                f"background-color: {COLOR_SURFACE_ELEVATED}; "
                f"border: 1px solid {COLOR_BORDER_SUBTLE}; "
                f"border-radius: {RADIUS_DEFAULT}; padding: 10px;"
            )
            alert_layout = QVBoxLayout(alert_card)
            alert_layout.setContentsMargins(10, 8, 10, 8)
            alert_layout.setSpacing(6)

            sev = self.alert_info.get("severity", "review_required")
            check_type = self.alert_info.get("check_type", "QA")
            desc = self.alert_info.get("description", "")
            sugg = self.alert_info.get("suggested_fix", "")

            sev_color = COLOR_ERROR if sev == "review_required" else COLOR_WARNING
            sev_label = "Crítico (Revisão Necessária)" if sev == "review_required" else "Sugestão de Correção"

            top_line = QHBoxLayout()
            lbl_sev = QLabel(f"<b>[{sev_label}]</b> {check_type}")
            lbl_sev.setStyleSheet(f"color: {sev_color}; font-weight: bold;")
            top_line.addWidget(lbl_sev)
            top_line.addStretch()
            alert_layout.addLayout(top_line)

            lbl_desc = QLabel(f"<b>Diagnóstico:</b> {desc}")
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
            alert_layout.addWidget(lbl_desc)

            if sugg:
                sugg_row = QHBoxLayout()
                lbl_sugg = QLabel(f"<b>Sugestão Automática:</b> <i>'{sugg}'</i>")
                lbl_sugg.setWordWrap(True)
                lbl_sugg.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px;")
                sugg_row.addWidget(lbl_sugg, stretch=1)

                btn_apply_sugg = QPushButton("Aplicar Sugestão", self)
                btn_apply_sugg.setStyleSheet(
                    f"background-color: {COLOR_SUCCESS}; color: #ffffff; "
                    f"font-size: 11px; padding: 4px 10px; border-radius: 4px;"
                )
                btn_apply_sugg.clicked.connect(lambda: self._apply_suggested_fix(sugg))
                sugg_row.addWidget(btn_apply_sugg)
                alert_layout.addLayout(sugg_row)

            layout.addWidget(alert_card)

        # 3. Bloco de Texto Original (Leitura)
        lbl_orig = QLabel("Texto Original (EN):", self)
        lbl_orig.setStyleSheet(f"font-weight: bold; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(lbl_orig)

        self.txt_original = QPlainTextEdit(self)
        self.txt_original.setPlainText(self.segment.original_text)
        self.txt_original.setReadOnly(True)
        self.txt_original.setMaximumHeight(110)
        self.txt_original.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; color: {COLOR_TEXT_PRIMARY}; "
            f"border: 1px solid {COLOR_BORDER_SUBTLE}; border-radius: {RADIUS_DEFAULT}; "
            f"font-family: {FONT_PRIMARY}; font-size: 13px;"
        )
        layout.addWidget(self.txt_original)

        # 4. Bloco de Texto Traduzido (Edição)
        lbl_trans = QLabel("Tradução (PT-BR) — Editável pelo Revisor:", self)
        lbl_trans.setStyleSheet(f"font-weight: bold; color: {COLOR_ACCENT};")
        layout.addWidget(lbl_trans)

        self.txt_translated = QPlainTextEdit(self)
        initial_trans = self.segment.translated_text or self.segment.original_text
        self.txt_translated.setPlainText(initial_trans)
        self.txt_translated.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; color: {COLOR_TEXT_PRIMARY}; "
            f"border: 1px solid {COLOR_ACCENT}; border-radius: {RADIUS_DEFAULT}; "
            f"font-family: {FONT_PRIMARY}; font-size: 13px;"
        )
        self.txt_translated.textChanged.connect(self._update_counters)
        layout.addWidget(self.txt_translated, stretch=1)

        # Contador de Palavras e Caracteres
        self.lbl_stats = QLabel("", self)
        self.lbl_stats.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self.lbl_stats)
        self._update_counters()

        # 5. Barra de Ações (Salvar e Cancelar)
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; color: {COLOR_TEXT_PRIMARY}; "
            f"border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 7px 16px; border-radius: {RADIUS_DEFAULT};"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Salvar e Aplicar", self)
        self.btn_save.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: #ffffff; font-weight: bold; "
            f"padding: 7px 20px; border-radius: {RADIUS_DEFAULT};"
        )

        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _apply_suggested_fix(self, sugg: str) -> None:
        self.txt_translated.setPlainText(sugg)

    def _update_counters(self) -> None:
        text = self.txt_translated.toPlainText()
        words = len(text.split())
        chars = len(text)
        self.lbl_stats.setText(f"Palavras: {words} | Caracteres: {chars}")

    def get_translated_text(self) -> str:
        return self.txt_translated.toPlainText().strip()
