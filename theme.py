"""
Thème visuel : palette dark + icônes Lucide bundlées.

Les icônes sont des PNG officiels Lucide (téléchargés via download_icons.py
et rasterisés en 96px depuis les SVG originaux). Au runtime on les charge
en blanc puis on les teinte (alpha-mask) selon la couleur demandée.

API conservée pour compat avec gui.py :
    theme.icon_search(size=20, color=...)  → PIL Image
    theme.ctk_icon(theme.icon_search, size=18, color="#fff")  → CTkImage
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from PIL import Image


# ─── PALETTE ────────────────────────────────────────────────────
class Colors:
    # Fonds
    bg            = "#15151a"   # fond le plus sombre (zones intérieures)
    bg_panel      = "#1f1f23"
    bg_panel_alt  = "#28282d"
    bg_hover      = "#33333a"
    border        = "#3a3a40"

    # Textes
    text_primary   = "#e8e8e8"
    text_secondary = "#b0b0b0"
    text_muted     = "#808080"

    # Accents (palette bleue broadcast)
    accent         = "#1f6aa5"
    accent_hover   = "#2a7ec0"
    accent_dark    = "#144870"
    green_ok       = "#4ec85a"
    green_hover    = "#5ed46a"
    red_danger     = "#dc4646"
    red_hover      = "#e85a5a"
    amber          = "#f5b041"
    blue_link      = "#5ba7d6"

    # Statuts candidatures
    statut_a_envoyer = "#7f8c8d"
    statut_envoyee   = "#5ba7d6"
    statut_relancee  = "#f5b041"
    statut_entretien = "#9b59b6"
    statut_refusee   = "#dc4646"
    statut_acceptee  = "#4ec85a"


# ─── TYPOGRAPHIE ────────────────────────────────────────────────
class Fonts:
    family = "Helvetica"
    h1 = 20
    h2 = 15
    label = 13
    body = 12
    small = 11
    micro = 10
    title_spacing = 2


# ─── CHARGEMENT DES ICÔNES LUCIDE ────────────────────────────────
def _hex_to_rgba(hex_color, alpha=255):
    h = (hex_color or "#FFFFFF").lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)


def _icons_dir() -> Path:
    """Dossier contenant les PNG des icônes (compatible PyInstaller).

    - Mode source : ./assets/icons/
    - Mode bundle : sys._MEIPASS/assets/icons/  ou  Resources/assets/icons/
    """
    candidates = []
    # PyInstaller --onefile / --onedir
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "icons")
    # À côté du script (mode source)
    candidates.append(Path(__file__).resolve().parent / "assets" / "icons")
    # Dans Contents/Resources (mode .app bundle)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent.parent
                          / "Resources" / "assets" / "icons")
    for p in candidates:
        if p.exists() and p.is_dir():
            return p
    return candidates[-1]  # fallback


# Cache : (name, size_hex_color) → PIL.Image
_ICON_CACHE: dict = {}


def _load_lucide(name: str, size: int, color: str) -> Image.Image:
    """Charge un PNG Lucide (blanc) et le teinte à la couleur demandée."""
    key = (name, size, color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = _icons_dir() / f"{name}.png"
    if not path.exists():
        # Fallback : retourne un carré transparent (évite crash UI)
        print(f"[theme] Icône manquante : {path}")
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _ICON_CACHE[key] = img
        return img
    try:
        src = Image.open(path).convert("RGBA")
        if src.size != (size, size):
            src = src.resize((size, size), Image.LANCZOS)
        # Teinte : on garde le canal alpha de la source, on remplace RGB
        r, g, b, _ = _hex_to_rgba(color)
        # Mode rapide via split + merge
        _, _, _, a = src.split()
        tinted = Image.new("RGBA", src.size, (r, g, b, 0))
        tinted.putalpha(a)
        _ICON_CACHE[key] = tinted
        return tinted
    except Exception as e:
        print(f"[theme] Erreur chargement {path} : {e}")
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))


# ─── API icon_* : conservée pour compat avec gui.py ──────────────
def _make_loader(lucide_alias: str, default_color):
    """Factory : retourne une fonction icon_<name>(size, color)."""
    def _icon(size: int = 20, color: str = None) -> Image.Image:
        return _load_lucide(lucide_alias, size, color or default_color)
    _icon.__name__ = f"icon_{lucide_alias}"
    return _icon


# Génère toutes les fonctions icon_* et les expose au module
_ICON_DEFAULTS = {
    "search":          Colors.text_secondary,
    "plus":            Colors.text_primary,
    "trash":           Colors.red_danger,
    "settings":        Colors.text_secondary,
    "user":            Colors.text_secondary,
    "list":            Colors.text_secondary,
    "refresh":         Colors.text_secondary,
    "loop":            Colors.text_secondary,
    "check":           Colors.green_ok,
    "close":           Colors.text_secondary,
    "cross":           Colors.red_danger,
    "play":            Colors.text_primary,
    "stop":            Colors.red_danger,
    "mail":            Colors.text_secondary,
    "mail_send":       Colors.text_primary,
    "link":            Colors.blue_link,
    "download":        Colors.text_secondary,
    "chevron_left":    Colors.text_secondary,
    "chevron_right":   Colors.text_secondary,
    "save":            Colors.text_primary,
    "send":            Colors.text_primary,
    "briefcase":       Colors.text_secondary,
    "pin":             Colors.text_secondary,
    "building":        Colors.text_secondary,
    "external":        Colors.blue_link,
    "folder":          Colors.text_secondary,
    "copy":            Colors.text_secondary,
    "file":            Colors.text_secondary,
    "warning":         Colors.amber,
    "import":          Colors.text_secondary,
    "info":            Colors.text_secondary,
    "book":            Colors.text_secondary,
    "bolt":            Colors.amber,
    "bulb":            Colors.amber,
    "target":          Colors.text_secondary,
    "question":        Colors.text_secondary,
}

# Injection des fonctions icon_xxx dans le namespace du module
for _alias, _default_color in _ICON_DEFAULTS.items():
    globals()[f"icon_{_alias}"] = _make_loader(_alias, _default_color)


# ─── Construction CTkImage à la demande ─────────────────────────
def ctk_icon(icon_fn, size=20, **kwargs):
    """Construit un CTkImage depuis une fonction icon_*.
    À appeler après ctk.set_appearance_mode."""
    import customtkinter as ctk
    img = icon_fn(size=size, **kwargs)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


# ─── Helpers ────────────────────────────────────────────────────
def caps(s):
    """Met en majuscules (effet letterspacing visuel)."""
    return s.upper()
