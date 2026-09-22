"""Aba e componente 'Sobre' (About) com a identidade oficial CJRDOOM."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from book_translator.ui.theme import (
    COLOR_ACCENT,
    COLOR_BACKGROUND,
    COLOR_BORDER_STRONG,
    COLOR_BORDER_SUBTLE,
    COLOR_SURFACE,
    COLOR_SURFACE_ACTIVE,
    COLOR_TEXT_DISABLED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    RADIUS_DEFAULT,
)


class AboutWidget(QWidget):
    """Componente responsivo da aba 'Sobre' contendo créditos, versão e a logo oficial CJRDOOM."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ScrollArea responsiva para garantir que nunca haja sobreposição em janelas pequenas
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(8)
        content_layout.setAlignment(Qt.AlignCenter)

        # Card Central Elevado
        card = QFrame(content_container)
        card.setObjectName("aboutCard")
        card.setStyleSheet(f"""
            QFrame#aboutCard {{
                background-color: {COLOR_SURFACE};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: {RADIUS_DEFAULT};
                max-width: 560px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 12, 20, 12)
        card_layout.setSpacing(6)
        card_layout.setAlignment(Qt.AlignCenter)

        # 1. Logo Oficial CJRDOOM com Contraste Garantido
        logo_label = QLabel(card)
        logo_label.setAlignment(Qt.AlignCenter)

        assets_dir = Path(__file__).resolve().parent.parent / "assets"
        # Prioriza o logo oficial enviado pelo desenvolvedor
        logo_path = assets_dir / "cjr_doom_logo.jpg"
        if not logo_path.exists():
            logo_path = assets_dir / "cjr_doom_logo.png"
        if not logo_path.exists():
            logo_path = assets_dir / "logo_transparent_light.png"
        if not logo_path.exists():
            logo_path = assets_dir / "logo.png"

        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                logo_label.setPixmap(scaled_pixmap)

        # Moldura com fundo branco/claro para garantir que a arte e a tipografia da logo apareçam perfeitamente
        logo_frame = QFrame(card)
        logo_frame.setStyleSheet(f"""
            background-color: #FFFFFF;
            border: 2px solid {COLOR_BORDER_STRONG};
            border-radius: 6px;
            padding: 8px;
        """)
        logo_frame_layout = QVBoxLayout(logo_frame)
        logo_frame_layout.setContentsMargins(6, 6, 6, 6)
        logo_frame_layout.addWidget(logo_label)
        card_layout.addWidget(logo_frame)

        # 2. Nome do Programa
        lbl_app_name = QLabel("Translate Book CJrTools", card)
        lbl_app_name.setAlignment(Qt.AlignCenter)
        lbl_app_name.setStyleSheet(f"""
            font-size: 19px;
            font-weight: 700;
            color: {COLOR_ACCENT};
            letter-spacing: 0.5px;
        """)
        card_layout.addWidget(lbl_app_name)

        # 3. Versão Oficial
        lbl_version = QLabel("Version 1.0.1", card)
        lbl_version.setAlignment(Qt.AlignCenter)
        lbl_version.setStyleSheet(f"""
            font-size: 13px;
            font-weight: 500;
            color: {COLOR_TEXT_SECONDARY};
        """)
        card_layout.addWidget(lbl_version)

        # Linha divisória sutil
        divider = QFrame(card)
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Plain)
        divider.setStyleSheet(f"color: {COLOR_BORDER_SUBTLE}; background-color: {COLOR_BORDER_SUBTLE}; max-width: 240px;")
        card_layout.addWidget(divider)

        # 4. Desenvolvido por CJRDOOM
        lbl_dev_intro = QLabel("Designed and developed by", card)
        lbl_dev_intro.setAlignment(Qt.AlignCenter)
        lbl_dev_intro.setStyleSheet(f"""
            font-size: 11px;
            color: {COLOR_BORDER_STRONG};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        card_layout.addWidget(lbl_dev_intro)

        lbl_developer = QLabel("CJRDOOM", card)
        lbl_developer.setAlignment(Qt.AlignCenter)
        lbl_developer.setStyleSheet(f"""
            font-size: 17px;
            font-weight: 800;
            color: {COLOR_TEXT_PRIMARY};
            letter-spacing: 2px;
        """)
        card_layout.addWidget(lbl_developer)

        # 5. Copyright
        lbl_copyright = QLabel("© 2026 Carlos Junior", card)
        lbl_copyright.setAlignment(Qt.AlignCenter)
        lbl_copyright.setStyleSheet(f"""
            font-size: 11px;
            color: {COLOR_TEXT_DISABLED};
        """)
        card_layout.addWidget(lbl_copyright)

        # 6. Badges Técnicas de Garantia de Privacidade e Arquitetura
        badges_row = QHBoxLayout()
        badges_row.setSpacing(6)
        badges_row.setAlignment(Qt.AlignCenter)

        for text in [
            "100% Offline & Local",
            "Zero Telemetria",
            "MADLAD-400 INT8",
            "Editorial Quality",
        ]:
            badge = QLabel(text, card)
            badge.setStyleSheet(f"""
                background-color: {COLOR_SURFACE_ACTIVE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: {RADIUS_DEFAULT};
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
            """)
            badges_row.addWidget(badge)

        card_layout.addLayout(badges_row)

        content_layout.addWidget(card)
        scroll.setWidget(content_container)
        root_layout.addWidget(scroll)
