# -*- mode: python ; coding: utf-8 -*-
"""Especificação PyInstaller para empacotamento standalone do Translate_BooK no Windows.

Regras Estritas de Segurança e Distribuição:
1. NUNCA embutir pesos do modelo MADLAD (*.bin, *.safetensors, *.gguf, *.onnx, etc.).
2. Não depender de Python pré-instalado pelo usuário (runtime standalone autocontido).
3. Empacotar scripts SQL de migração e schemas do SQLite.
4. Separar o binário da aplicação dos diretórios de dados e projetos do usuário.
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Localização das fontes da aplicação
spec_dir = Path(SPECPATH)
workspace_dir = spec_dir.parent.parent
src_dir = workspace_dir / "src"

# Arquivos de dados obrigatórios (schemas SQL e migrations)
datas = [
    (str(src_dir / "book_translator" / "database" / "sql"), "book_translator/database/sql"),
]

# Hidden imports necessários para PySide6, parsers e pipeline
hiddenimports = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "sqlite3",
    "pypdf",
    "bs4",
    "book_translator",
    "book_translator.config",
    "book_translator.logging",
    "book_translator.ui",
    "book_translator.ui.app",
    "book_translator.ui.main_window",
    "book_translator.ui.worker",
    "book_translator.ui.components.project_wizard",
    "book_translator.ui.components.editor",
    "book_translator.ui.components.progress_view",
    "book_translator.ui.components.review_panel",
    "book_translator.ui.components.settings_dialog",
    "book_translator.parsers",
    "book_translator.parsers.txt",
    "book_translator.parsers.docx",
    "book_translator.parsers.epub",
    "book_translator.parsers.pdf",
    "book_translator.export",
    "book_translator.export.txt",
    "book_translator.export.docx",
    "book_translator.export.epub",
    "book_translator.security",
    "book_translator.system.hardware",
    "book_translator.system.model_manager",
]

# Exclusões para redução de tamanho e prevenção de conflitos
excludes = [
    "tkinter",
    "pytest",
    "unittest",
    "matplotlib",
    "scipy",
    "IPython",
]

a = Analysis(
    [str(src_dir / "book_translator" / "ui" / "app.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filtro estrito: Garante que NENHUM peso de IA seja incluído no executável
def is_model_weight(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in [
        ".bin", ".safetensors", ".gguf", ".pt", ".pth", ".onnx", ".part"
    ])

a.datas = [d for d in a.datas if not is_model_weight(d[0])]
a.binaries = [b for b in a.binaries if not is_model_weight(b[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Translate_BooK",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Executável GUI sem janela de console preta
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Translate_BooK",
)
