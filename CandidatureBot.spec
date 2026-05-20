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
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve()

# ─── Scrapling et ses dépendances : collect_all force PyInstaller
#     à inclure TOUS les sous-modules + data files (les imports lazy
#     via __getattr__ ne sont pas suivis automatiquement).
def _collect(name):
    try:
        return collect_all(name)
    except Exception as e:
        print(f"[spec] collect_all({name}) failed: {e}")
        return ([], [], [])

_scrap_d, _scrap_b, _scrap_h = _collect("scrapling")
_brwf_d,  _brwf_b,  _brwf_h  = _collect("browserforge")
_curl_d,  _curl_b,  _curl_h  = _collect("curl_cffi")
_fuag_d,  _fuag_b,  _fuag_h  = _collect("fake_useragent")
_plw_d,   _plw_b,   _plw_h   = _collect("playwright")

# ─── Données embarquées (read-only dans le bundle) ─────────────
datas = [
    (str(ROOT / "config.template.json"), "."),
] + _scrap_d + _brwf_d + _curl_d + _fuag_d + _plw_d

binaries = _scrap_b + _brwf_b + _curl_b + _fuag_b + _plw_b

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
    "theme",
    "ai_engine",
    "scraper",
    "tracker",
    "mail_sender",
    "pdf_generator",
    "cv_parser",
    "ollama_installer",
    "profile_manager",
    # Scrapling + dépendances (les noms statiques en complément de collect_all)
    "scrapling",
    "scrapling.fetchers",
    "scrapling.fetchers.requests",
    "scrapling.engines",
    "scrapling.engines.static",
    "scrapling.engines.toolbelt",
    "scrapling.engines.toolbelt.fingerprints",
    "scrapling.engines._browsers",
    "scrapling.engines._browsers._types",
    "scrapling.parser",
    "curl_cffi",
    "curl_cffi.requests",
    "browserforge",
    "browserforge.headers",
    "fake_useragent",
    "w3lib",
    "tldextract",
    "playwright",
    "playwright._impl._errors",
    "pyee",
] + _scrap_h + _brwf_h + _curl_h + _fuag_h + _plw_h

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
    binaries=binaries,
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
