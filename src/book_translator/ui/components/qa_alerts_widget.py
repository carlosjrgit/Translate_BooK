"""Componente de exibição e inspeção de alertas de controle de qualidade (QA)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class QAAlertsWidget(QWidget):
    """Tabela interativa para visualização e filtragem de alertas e anomalias de QA."""

    sig_edit_segment = Signal(str, dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_alerts: list[dict[str, Any]] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        group = QGroupBox("Alertas e Anomalias de Controle de Qualidade (QA)", self)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(8)

        # Filtro de Severidade
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtrar por Severidade:", self))

        self.combo_filter = QComboBox(self)
        self.combo_filter.addItems([
            "Todos os Níveis",
            "Revisão Necessária (Crítico)",
            "Sugestão de Correção",
            "Correção Segura Automática",
        ])
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self.combo_filter)

        filter_row.addStretch()
        self.lbl_count = QLabel("Nenhum alerta encontrado.", self)
        self.lbl_count.setStyleSheet("color: #a6adc8; font-weight: bold;")
        filter_row.addWidget(self.lbl_count)

        group_layout.addLayout(filter_row)

        # Tabela de Alertas
        self.tbl_alerts = QTableWidget(self)
        self.tbl_alerts.setColumnCount(5)
        self.tbl_alerts.setHorizontalHeaderLabels([
            "Capítulo",
            "Segmento",
            "Severidade",
            "Tipo / Regra",
            "Descrição e Sugestão",
        ])
        self.tbl_alerts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_alerts.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_alerts.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_alerts.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_alerts.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tbl_alerts.setAlternatingRowColors(True)
        self.tbl_alerts.itemDoubleClicked.connect(self._on_item_double_clicked)

        group_layout.addWidget(self.tbl_alerts)

        lbl_hint = QLabel("💡 Dica: Dê um duplo clique em qualquer linha para abrir a Revisão Humana e editar o segmento.", self)
        lbl_hint.setStyleSheet("color: #a6adc8; font-style: italic; font-size: 11px;")
        group_layout.addWidget(lbl_hint)

        layout.addWidget(group)

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        seg_item = self.tbl_alerts.item(row, 1)
        if not seg_item:
            return
        segment_id = seg_item.text().strip()
        matching_alert = next((a for a in self._all_alerts if a.get("segment_id") == segment_id), {})
        self.sig_edit_segment.emit(segment_id, matching_alert)

    def set_alerts(self, alerts: list[dict[str, Any]]) -> None:
        self._all_alerts = list(alerts)
        self._apply_filter()

    def _apply_filter(self) -> None:
        selected = self.combo_filter.currentText()
        filtered = []

        for item in self._all_alerts:
            sev = item.get("severity", "")
            if selected == "Revisão Necessária (Crítico)" and sev != "review_required":
                continue
            elif selected == "Sugestão de Correção" and sev != "suggested_fix":
                continue
            elif selected == "Correção Segura Automática" and sev != "safe_fix":
                continue
            filtered.append(item)

        self.tbl_alerts.setRowCount(0)
        for item in filtered:
            row = self.tbl_alerts.rowCount()
            self.tbl_alerts.insertRow(row)

            it_chap = QTableWidgetItem(str(item.get("chapter", "")))
            it_seg = QTableWidgetItem(str(item.get("segment_id", "")))

            sev = item.get("severity", "")
            if sev == "review_required":
                sev_label = "Crítico (Revisar)"
                color = QColor("#F44336")
            elif sev == "suggested_fix":
                sev_label = "Sugestão"
                color = QColor("#FFC107")
            else:
                sev_label = "Automático"
                color = QColor("#4CAF50")

            it_sev = QTableWidgetItem(sev_label)
            it_sev.setForeground(color)
            it_sev.setTextAlignment(Qt.AlignCenter)

            it_type = QTableWidgetItem(str(item.get("check_type", "")))

            desc = item.get("description", "")
            sugg = item.get("suggested_fix", "")
            full_desc = f"{desc} | Sugestão: '{sugg}'" if sugg else desc
            it_desc = QTableWidgetItem(full_desc)

            self.tbl_alerts.setItem(row, 0, it_chap)
            self.tbl_alerts.setItem(row, 1, it_seg)
            self.tbl_alerts.setItem(row, 2, it_sev)
            self.tbl_alerts.setItem(row, 3, it_type)
            self.tbl_alerts.setItem(row, 4, it_desc)

        total = len(self._all_alerts)
        displayed = len(filtered)
        if total == 0:
            self.lbl_count.setText("Nenhum alerta encontrado. Qualidade 100% aprovada!")
            self.lbl_count.setStyleSheet("color: #4CAF50; font-weight: 600;")
        else:
            self.lbl_count.setText(f"Exibindo {displayed} de {total} alertas.")
            self.lbl_count.setStyleSheet("color: #FFC107; font-weight: 600;")
