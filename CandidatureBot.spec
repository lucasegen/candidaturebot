# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour Candidature Bot.

Build local :
    ./venv/bin/pyinstaller --noconfirm CandidatureBot.spec

Sortie :
    dist/CandidatureBot.app   (macOS)
    dist/CandidatureBot/      (onedir Windows/Linux)
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()

# ─── Données embarquées (read-only dans le bundle) ─────────────
datas = [
    (str(ROOT / "config.template.json"), "."),
]

# ─── Imports cachés (PyInstaller ne les détecte pas tout seul) ─
hiddenimports = [
    "pytesseract",
    "ollama",
    "pypdf",
    "docx",
    "requests",
    "dotenv",
    "openai",
    "anthropic",
    "reportlab",
    "reportlab.pdfgen",
    "reportlab.lib",
    "reportlab.platypus",
    "PIL",
    "PIL._tkinter_finder",
    "customtkinter",
    "app_paths",
    "ai_engine",
    "scraper",
    "tracker",
    "mail_sender",
    "pdf_generator",
    "cv_parser",
    "ollama_installer",
    "profile_manager",
]

# ─── Modules exclus pour réduire la taille ─────────────────────
excludes = [
    "tests", "test", "unittest",
    "matplotlib", "scipy", "numpy.tests",
    "IPython", "jupyter",
]

block_cipher = None

a = Analysis(
    ["gui.py"],
    pathex=[str(ROOT)],
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
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CandidatureBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,        # GUI app, pas de fenêtre terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    upx=False,
    upx_exclude=[],
    name="CandidatureBot",
)

# ─── Bundle .app pour macOS ────────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="CandidatureBot.app",
        icon=None,           # mettra l'icône Tk par défaut ; remplacer plus tard
        bundle_identifier="com.lucasegen.candidaturebot",
        info_plist={
            "CFBundleName": "Candidature Bot",
            "CFBundleDisplayName": "Candidature Bot",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "LSMinimumSystemVersion": "10.13.0",
        },
    )
