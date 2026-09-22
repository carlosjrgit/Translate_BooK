"""Card de resumo da análise prévia da obra."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from book_translator.analysis.base import AnalysisReport
from book_translator.core.models import Document
from book_translator.ui.theme import COLOR_ACCENT, RADIUS_DEFAULT


class AnalysisSummaryWidget(QWidget):
    """Exibe o diagnóstico e o resumo analítico da obra antes da tradução."""

    sig_promote_entities = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.last_report: AnalysisReport | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Card de Metadados e Estatísticas
        stats_group = QGroupBox("Diagnóstico Geral da Obra", self)
        stats_layout = QGridLayout(stats_group)
        stats_layout.setContentsMargins(12, 12, 12, 12)
        stats_layout.setSpacing(10)

        self.lbl_title = QLabel("Título: —", self)
        self.lbl_author = QLabel("Autor: —", self)
        self.lbl_lang = QLabel("Idiomas: Detectado EN -> Destino PT-BR", self)
        self.lbl_chapters = QLabel("Capítulos: —", self)
        self.lbl_words = QLabel("Total de Palavras: —", self)
        self.lbl_tone = QLabel("Tom / Formalidade: —", self)

        stats_layout.addWidget(self.lbl_title, 0, 0)
        stats_layout.addWidget(self.lbl_author, 0, 1)
        stats_layout.addWidget(self.lbl_lang, 1, 0)
        stats_layout.addWidget(self.lbl_chapters, 1, 1)
        stats_layout.addWidget(self.lbl_words, 2, 0)
        stats_layout.addWidget(self.lbl_tone, 2, 1)

        layout.addWidget(stats_group)

        # Tabela de Personagens e Entidades Principais
        entities_group = QGroupBox("Personagens e Entidades Chave Detectadas", self)
        entities_layout = QVBoxLayout(entities_group)

        self.tbl_entities = QTableWidget(self)
        self.tbl_entities.setColumnCount(4)
        self.tbl_entities.setHorizontalHeaderLabels([
            "Nome Canônico",
            "Tipo",
            "Gênero / Papel",
            "Ocorrências",
        ])
        self.tbl_entities.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_entities.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_entities.setAlternatingRowColors(True)
        entities_layout.addWidget(self.tbl_entities)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_promote = QPushButton("Promover Entidades para o Glossário Travado", self)
        self.btn_promote.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: #ffffff; font-weight: bold; "
            f"padding: 6px 16px; border-radius: {RADIUS_DEFAULT}px;"
        )
        self.btn_promote.setEnabled(False)
        self.btn_promote.clicked.connect(self.sig_promote_entities.emit)
        btn_row.addWidget(self.btn_promote)
        entities_layout.addLayout(btn_row)

        layout.addWidget(entities_group)

    def populate(self, document: Document, report: AnalysisReport | None = None) -> None:
        """Preenche o componente com os dados da obra e do relatório analítico."""
        self.last_report = report
        self.lbl_title.setText(f"Título: {document.title or 'Sem Título'}")
        self.lbl_author.setText(f"Autor: {document.author or 'Desconhecido'}")
        self.lbl_chapters.setText(f"Capítulos: {len(document.chapters)}")

        total_words = sum(ch.total_words() for ch in document.chapters)
        self.lbl_words.setText(f"Total de Palavras: {total_words:,}")

        if report:
            self.lbl_tone.setText(
                f"Tom: {report.estimated_tone.capitalize()} | "
                f"Formalidade: {report.formality_level.capitalize()}"
            )

            # Preenche tabela de entidades
            self.tbl_entities.setRowCount(0)
            for entity in report.entities[:30]:  # Top 30 entidades
                row = self.tbl_entities.rowCount()
                self.tbl_entities.insertRow(row)

                item_name = QTableWidgetItem(entity.canonical_name)
                item_type = QTableWidgetItem(entity.entity_type.value.capitalize())
                item_gender = QTableWidgetItem(entity.gender.capitalize())
                item_count = QTableWidgetItem(str(entity.occurrences_count))
                item_count.setTextAlignment(Qt.AlignCenter)

                self.tbl_entities.setItem(row, 0, item_name)
                self.tbl_entities.setItem(row, 1, item_type)
                self.tbl_entities.setItem(row, 2, item_gender)
                self.tbl_entities.setItem(row, 3, item_count)

            self.btn_promote.setEnabled(bool(report.entities))
        else:
            self.lbl_tone.setText("Tom: Neutro | Formalidade: Padrão")
            self.btn_promote.setEnabled(False)

