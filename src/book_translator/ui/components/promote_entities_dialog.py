"""Diálogo modal para promoção rápida de entidades detectadas para o Glossário Travado."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from book_translator.memory.models import GlossaryEntry
from book_translator.ui.theme import (
    COLOR_ACCENT,
    COLOR_BORDER_SUBTLE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_PRIMARY,
    RADIUS_DEFAULT,
)


class PromoteEntitiesDialog(QDialog):
    """Permite selecionar e definir traduções para entidades promovidas ao glossário."""

    def __init__(
        self,
        entities: list[Any],
        project_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entities = list(entities)
        self.project_id = project_id

        self.setWindowTitle("Promover Entidades para o Glossário Travado")
        self.resize(750, 480)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Cabeçalho explicativo
        lbl_info = QLabel(
            "Selecione as entidades detectadas na análise que devem ser travadas no Glossário. "
            "Termos travados mantêm rigorosa consistência de tradução e não sofrem variações artificiais.",
            self,
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-family: {FONT_PRIMARY};")
        layout.addWidget(lbl_info)

        # Barra de seleção rápida
        sel_row = QHBoxLayout()
        btn_sel_all = QPushButton("Selecionar Todos", self)
        btn_sel_all.setStyleSheet(f"font-size: 11px; padding: 4px 10px; border-radius: {RADIUS_DEFAULT};")
        btn_sel_all.clicked.connect(lambda: self._toggle_all(True))
        sel_row.addWidget(btn_sel_all)

        btn_desel_all = QPushButton("Desmarcar Todos", self)
        btn_desel_all.setStyleSheet(f"font-size: 11px; padding: 4px 10px; border-radius: {RADIUS_DEFAULT};")
        btn_desel_all.clicked.connect(lambda: self._toggle_all(False))
        sel_row.addWidget(btn_desel_all)

        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Tabela de Entidades
        self.tbl_entities = QTableWidget(self)
        self.tbl_entities.setColumnCount(5)
        self.tbl_entities.setHorizontalHeaderLabels([
            "Incluir",
            "Termo Original (EN)",
            "Tipo",
            "Ocorrências",
            "Tradução / Termo Travado em PT-BR (Editável)",
        ])
        self.tbl_entities.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tbl_entities.setAlternatingRowColors(True)

        self._populate_table()
        layout.addWidget(self.tbl_entities)

        # Barra de Botões
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; color: {COLOR_TEXT_PRIMARY}; "
            f"border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 7px 16px; border-radius: {RADIUS_DEFAULT};"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_promote = QPushButton("Promover Selecionadas para o Glossário", self)
        self.btn_promote.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: #ffffff; font-weight: bold; "
            f"padding: 7px 20px; border-radius: {RADIUS_DEFAULT};"
        )
        self.btn_promote.clicked.connect(self._on_promote_clicked)
        btn_box.addWidget(self.btn_promote)

        layout.addLayout(btn_box)

    def _populate_table(self) -> None:
        self.tbl_entities.setRowCount(0)
        for entity in self.entities:
            row = self.tbl_entities.rowCount()
            self.tbl_entities.insertRow(row)

            # Checkbox na coluna 0
            chk = QCheckBox(self)
            chk.setChecked(True)
            chk_widget = QWidget(self)
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.tbl_entities.setCellWidget(row, 0, chk_widget)

            # Termo Original
            name = getattr(entity, "canonical_name", str(entity))
            it_name = QTableWidgetItem(name)
            it_name.setFlags(it_name.flags() & ~Qt.ItemIsEditable)
            self.tbl_entities.setItem(row, 1, it_name)

            # Tipo
            e_type = getattr(entity, "entity_type", "term")
            type_str = e_type.value if hasattr(e_type, "value") else str(e_type)
            it_type = QTableWidgetItem(type_str.capitalize())
            it_type.setFlags(it_type.flags() & ~Qt.ItemIsEditable)
            self.tbl_entities.setItem(row, 2, it_type)

            # Ocorrências
            occ = getattr(entity, "occurrences_count", 1)
            it_occ = QTableWidgetItem(str(occ))
            it_occ.setTextAlignment(Qt.AlignCenter)
            it_occ.setFlags(it_occ.flags() & ~Qt.ItemIsEditable)
            self.tbl_entities.setItem(row, 3, it_occ)

            # Tradução em PT-BR (Editável, pré-preenchido com o próprio termo canônico)
            it_target = QTableWidgetItem(name)
            self.tbl_entities.setItem(row, 4, it_target)

    def _toggle_all(self, checked: bool) -> None:
        for row in range(self.tbl_entities.rowCount()):
            widget = self.tbl_entities.cellWidget(row, 0)
            if widget:
                chk = widget.findChild(QCheckBox)
                if chk:
                    chk.setChecked(checked)

    def _on_promote_clicked(self) -> None:
        promoted = self.get_promoted_entries()
        if not promoted:
            QMessageBox.warning(self, "Aviso", "Nenhuma entidade selecionada para promoção.")
            return
        self.accept()

    def get_promoted_entries(self) -> list[GlossaryEntry]:
        """Extrai as entradas selecionadas com as respectivas traduções definidas pelo usuário."""
        results: list[GlossaryEntry] = []
        for row in range(self.tbl_entities.rowCount()):
            widget = self.tbl_entities.cellWidget(row, 0)
            if not widget:
                continue
            chk = widget.findChild(QCheckBox)
            if not chk or not chk.isChecked():
                continue

            it_name = self.tbl_entities.item(row, 1)
            it_type = self.tbl_entities.item(row, 2)
            it_target = self.tbl_entities.item(row, 4)

            source = it_name.text().strip() if it_name else ""
            e_type = it_type.text().lower().strip() if it_type else "term"
            target = it_target.text().strip() if it_target else source

            if source and target:
                results.append(
                    GlossaryEntry(
                        source_term=source,
                        target_term=target,
                        entry_type=e_type,
                        locked=True,
                        project_id=self.project_id,
                    )
                )
        return results
