"""Design System Oficial — Translate Book CJrTools.

Diretrizes Estéticas:
- Estética geral: Dark, Minimal, Flat, Geometric e Technical.
- Princípio visual: "Flat, not plain". Sem gradientes, sem glassmorphism, sem 3D, sem sombras excessivas.
- Cores de Superfície:
    Background: #2E2D2D
    Surface: #363535
    Surface Elevated: #3D3C3C
    Surface Active: #454444
    Surface Disabled: #303030
- Cores de Texto:
    Text Primary: #F0F0F0
    Text Secondary: #BDBDBD
    Text Disabled: #666666
- Destaque / Identidade:
    Accent: #FFAC2B
- Bordas e Linhas:
    Border Strong: #9E9E9E
    Border Subtle: #4A4949
- Semânticas:
    Success: #4CAF50
    Warning: #FFC107
    Error: #F44336
    Information: #2196F3
- Tipografia:
    Primary: Inter, Segoe UI, Arial, sans-serif
    Monospace: JetBrains Mono, Consolas, monospace
- Raio:
    Default: 4px
    Secundário: 2px
"""

from __future__ import annotations

# Tokens de Design
COLOR_BACKGROUND = "#2E2D2D"
COLOR_SURFACE = "#363535"
COLOR_SURFACE_ELEVATED = "#3D3C3C"
COLOR_SURFACE_ACTIVE = "#454444"
COLOR_SURFACE_DISABLED = "#303030"

COLOR_ACCENT = "#FFAC2B"
COLOR_BORDER_STRONG = "#9E9E9E"
COLOR_BORDER_SUBTLE = "#4A4949"

COLOR_TEXT_PRIMARY = "#F0F0F0"
COLOR_TEXT_SECONDARY = "#BDBDBD"
COLOR_TEXT_DISABLED = "#666666"

COLOR_SUCCESS = "#4CAF50"
COLOR_WARNING = "#FFC107"
COLOR_ERROR = "#F44336"
COLOR_INFO = "#2196F3"

FONT_PRIMARY = "'Inter', 'Segoe UI', Arial, sans-serif"
FONT_MONOSPACE = "'JetBrains Mono', 'Consolas', monospace"

RADIUS_DEFAULT = "4px"
RADIUS_SECONDARY = "2px"

APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT_PRIMARY};
    font-family: {FONT_PRIMARY};
    font-size: 13px;
}}

/* Barra de Rolagem Minimalista e Geométrica */
QScrollBar:vertical {{
    background-color: {COLOR_BACKGROUND};
    width: 8px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {COLOR_SURFACE_ACTIVE};
    min-height: 24px;
    border-radius: {RADIUS_SECONDARY};
}}
QScrollBar::handle:vertical:hover {{
    background-color: {COLOR_BORDER_STRONG};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
}}
QScrollBar:horizontal {{
    background-color: {COLOR_BACKGROUND};
    height: 8px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background-color: {COLOR_SURFACE_ACTIVE};
    min-width: 24px;
    border-radius: {RADIUS_SECONDARY};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
}}

/* Containers e Agrupamentos */
QGroupBox {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
    color: {COLOR_ACCENT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: {COLOR_SURFACE};
}}

QFrame#metricsCard, QFrame#cardElevated {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
}}

/* Botões com hierarquia clara e raio de 4px */
QPushButton {{
    background-color: {COLOR_SURFACE_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
    padding: 6px 14px;
    min-height: 20px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLOR_SURFACE_ACTIVE};
    border: 1px solid {COLOR_BORDER_STRONG};
}}
QPushButton:pressed {{
    background-color: {COLOR_BACKGROUND};
    border: 1px solid {COLOR_ACCENT};
}}
QPushButton:focus {{
    border: 1px solid {COLOR_ACCENT};
}}
QPushButton:disabled {{
    background-color: {COLOR_SURFACE_DISABLED};
    color: {COLOR_TEXT_DISABLED};
    border: 1px solid {COLOR_SURFACE_DISABLED};
}}

/* Botão de Ação Primária com Accent #FFAC2B */
QPushButton#primaryAction, QPushButton[primary="true"] {{
    background-color: {COLOR_ACCENT};
    color: #1A1A1A;
    border: 1px solid {COLOR_ACCENT};
    font-weight: 600;
}}
QPushButton#primaryAction:hover, QPushButton[primary="true"]:hover {{
    background-color: #FFB84D;
    border: 1px solid #FFB84D;
}}
QPushButton#primaryAction:pressed, QPushButton[primary="true"]:pressed {{
    background-color: #E6951A;
    border: 1px solid #E6951A;
}}
QPushButton#primaryAction:disabled, QPushButton[primary="true"]:disabled {{
    background-color: {COLOR_SURFACE_DISABLED};
    color: {COLOR_TEXT_DISABLED};
    border: 1px solid {COLOR_SURFACE_DISABLED};
}}

/* Entradas de Texto e Seletores */
QLineEdit, QComboBox, QSpinBox {{
    background-color: {COLOR_BACKGROUND};
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
    padding: 5px 8px;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_ACCENT};
    selection-color: #1A1A1A;
    min-height: 20px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {COLOR_ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background-color: {COLOR_SURFACE_DISABLED};
    color: {COLOR_TEXT_DISABLED};
    border: 1px solid {COLOR_SURFACE_DISABLED};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_SURFACE_ELEVATED};
    border: 1px solid {COLOR_BORDER_STRONG};
    selection-background-color: {COLOR_SURFACE_ACTIVE};
    selection-color: {COLOR_ACCENT};
    color: {COLOR_TEXT_PRIMARY};
    outline: none;
}}

/* Tabelas Minimalistas e Geométricas */
QTableWidget {{
    background-color: {COLOR_BACKGROUND};
    alternate-background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
    gridline-color: {COLOR_BORDER_SUBTLE};
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: {COLOR_SURFACE_ACTIVE};
    selection-color: {COLOR_ACCENT};
}}
QHeaderView::section {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT_PRIMARY};
    padding: 6px 8px;
    font-weight: 600;
    border: none;
    border-right: 1px solid {COLOR_BORDER_SUBTLE};
    border-bottom: 1px solid {COLOR_BORDER_SUBTLE};
}}
QTableCornerButton::section {{
    background-color: {COLOR_SURFACE};
    border: none;
    border-right: 1px solid {COLOR_BORDER_SUBTLE};
    border-bottom: 1px solid {COLOR_BORDER_SUBTLE};
}}

/* Abas (QTabWidget) */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
    background-color: {COLOR_SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT_SECONDARY};
    padding: 8px 18px;
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-bottom: none;
    border-top-left-radius: {RADIUS_DEFAULT};
    border-top-right-radius: {RADIUS_DEFAULT};
    margin-right: 2px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background-color: {COLOR_SURFACE_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_ACCENT};
    font-weight: 600;
    border-top: 2px solid {COLOR_ACCENT};
}}

/* Visualizador de Logs e Terminal Técnico */
QTextEdit#logView, QTextEdit {{
    background-color: #242323;
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: {RADIUS_DEFAULT};
    color: {COLOR_TEXT_PRIMARY};
    font-family: {FONT_MONOSPACE};
    font-size: 11px;
    padding: 6px;
}}

/* Barra de Progresso Geométrica */
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

/* Checkboxes e RadioButtons */
QCheckBox, QRadioButton {{
    color: {COLOR_TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: {RADIUS_SECONDARY};
    background-color: {COLOR_BACKGROUND};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {COLOR_ACCENT};
    border: 1px solid {COLOR_ACCENT};
}}

/* Tooltips */
QToolTip {{
    background-color: {COLOR_SURFACE_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: {RADIUS_SECONDARY};
    padding: 4px 8px;
    font-size: 11px;
}}
"""
