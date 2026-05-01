"""
Chemins de l'application — cross-platform et compatible PyInstaller.

Données utilisateur (config, .env, data/) → dossier inscriptible :
- macOS  : ~/Library/Application Support/CandidatureBot
- Windows: %APPDATA%/CandidatureBot
- Linux  : ~/.config/CandidatureBot

Ressources read-only embarquées (templates, icônes) :
- Mode source : à côté de ce fichier .py
- Mode PyInstaller : dans sys._MEIPASS
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

APP_NAME = "CandidatureBot"


def is_frozen() -> bool:
    """True si on tourne dans un bundle PyInstaller / py2app."""
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """Dossier utilisateur inscriptible (config.json, .env, data/...)."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    p = base / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_dir() -> Path:
    """Dossier des ressources read-only embarquées dans le bundle."""
    if is_frozen():
        # PyInstaller --onefile  : sys._MEIPASS
        # PyInstaller --onedir   : dossier de l'exécutable
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return app_data_dir() / "config.json"


def env_path() -> Path:
    return app_data_dir() / ".env"


def data_dir() -> Path:
    p = app_data_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pdfs_dir() -> Path:
    p = data_dir() / "pdfs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def backups_dir() -> Path:
    p = data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def candidatures_path() -> Path:
    return data_dir() / "candidatures.json"


def offres_path() -> Path:
    return data_dir() / "offres.json"


def app_install_dir() -> Path:
    """Dossier où l'app est installée (où vivent les .py / le bundle).

    Utilisé par le système de mise à jour pour savoir où écrire les
    nouveaux fichiers. En mode source : dossier du script. En mode
    PyInstaller --onedir : dossier de l'exécutable. En mode --onefile :
    pas de mise à jour possible (fichier unique non modifiable proprement).
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
