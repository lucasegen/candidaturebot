# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour Candidature Bot.

Build local :
    ./venv/bin/pyinstaller --noconfirm CandidatureBot.spec

Sortie :
    dist/CandidatureBot.app   (macOS)
    dist/CandidatureBot/      (onedir Windows/Linux)
"""
import json
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve()

# ─── Lecture dynamique de la version depuis version.json ────────
# Évite la dérive entre version.json et les métadonnées macOS
# (Get Info / "À propos") qui restaient figées à 1.0.0.
try:
    _vjson = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    APP_VERSION = _vjson.get("version", "1.0.0")
except Exception as e:
    print(f"[spec] Lecture version.json impossible : {e}")
    APP_VERSION = "1.0.0"

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
_patch_d, _patch_b, _patch_h = _collect("patchright")
_w3l_d,   _w3l_b,   _w3l_h   = _collect("w3lib")
_tldx_d,  _tldx_b,  _tldx_h  = _collect("tldextract")
_pyee_d,  _pyee_b,  _pyee_h  = _collect("pyee")
# Data files browserforge depuis v1.2.4 — package séparé contenant
# fingerprint-network-definition.zip, headers-order.json, etc.
_apfd_d,  _apfd_b,  _apfd_h  = _collect("apify_fingerprint_datapoints")


def _drop_drivers(coll):
    """Filtre les drivers Node.js/browsers Playwright (~115 Mo chacun) que
    Scrapling n'utilise PAS en mode Fetcher HTTP. On garde seulement le
    code Python qui satisfait les imports au chargement."""
    out = []
    for src, dst in coll:
        d = str(dst).replace("\\", "/")
        # Tout ce qui est dans driver/ → exclu (drivers natifs lourds)
        if "/driver/" in d or d.endswith("/driver"):
            continue
        if "/node/" in d or "/browsers/" in d:
            continue
        out.append((src, dst))
    return out


_scrap_d = _drop_drivers(_scrap_d)
_brwf_d  = _drop_drivers(_brwf_d)
_plw_d   = _drop_drivers(_plw_d)
_patch_d = _drop_drivers(_patch_d)
_scrap_b = _drop_drivers(_scrap_b)
_brwf_b  = _drop_drivers(_brwf_b)
_plw_b   = _drop_drivers(_plw_b)
_patch_b = _drop_drivers(_patch_b)

# ─── Données embarquées (read-only dans le bundle) ─────────────
datas = [
    (str(ROOT / "config.template.json"), "."),
    (str(ROOT / "assets" / "icons"), "assets/icons"),
] + _scrap_d + _brwf_d + _curl_d + _fuag_d + _plw_d + _patch_d \
  + _w3l_d + _tldx_d + _pyee_d + _apfd_d

binaries = _scrap_b + _brwf_b + _curl_b + _fuag_b + _plw_b + _patch_b \
         + _w3l_b + _tldx_b + _pyee_b + _apfd_b

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
    "mail_sender",
    "pdf_generator",
    "cv_parser",
    "ollama_installer",
    "tones",
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
    "apify_fingerprint_datapoints",
] + _scrap_h + _brwf_h + _curl_h + _fuag_h + _plw_h \
  + _w3l_h + _tldx_h + _pyee_h + _apfd_h

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
            "CFBundleVersion": APP_VERSION,
            "CFBundleShortVersionString": APP_VERSION,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "LSMinimumSystemVersion": "10.13.0",
        },
    )

    # ─── Post-bundle cleanup : drivers Node.js Playwright/Patchright ──
    # Ces dossiers (~115 Mo) sont automatiquement ajoutés par PyInstaller
    # mais inutiles puisqu'on utilise uniquement le mode Fetcher HTTP de
    # Scrapling — pas de browser controller en runtime.
    import shutil
    _app_path = ROOT / "dist" / "CandidatureBot.app"
    for sub in ("Contents/Frameworks", "Contents/Resources"):
        for pkg in ("patchright", "playwright"):
            driver_dir = _app_path / sub / pkg / "driver"
            if driver_dir.is_dir():
                try:
                    shutil.rmtree(driver_dir)
                    print(f"[spec] Removed {driver_dir.relative_to(ROOT)}")
                except Exception as e:
                    print(f"[spec] Cleanup failed for {driver_dir}: {e}")
