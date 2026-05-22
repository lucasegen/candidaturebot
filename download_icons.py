"""
Script de download des icônes Lucide en PNG via rasterisation locale.

Pipeline :
  1. Download SVG depuis api.iconify.design/lucide/<name>.svg
  2. Rasterisation en PNG 96px via `rsvg-convert` (Homebrew librsvg)
  3. Bundle dans assets/icons/<alias>.png

À lancer manuellement quand on veut rafraîchir le set :
    python3 download_icons.py

Pré-requis : `brew install librsvg` (pour rsvg-convert).
Le bundle PyInstaller embarque ensuite assets/icons/ via le .spec.
"""
from __future__ import annotations
import os
import ssl
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CTX = ssl.create_default_context()

# Mapping : alias interne → nom Lucide officiel
ICONS = {
    "search":          "search",
    "plus":            "plus",
    "trash":           "trash-2",
    "settings":        "settings",
    "user":            "user",
    "list":            "list",
    "refresh":         "refresh-cw",
    "loop":            "rotate-cw",
    "check":           "check",
    "close":           "x",
    "cross":           "x",
    "play":            "play",
    "stop":            "square",
    "mail":            "mail",
    "mail_send":       "send",
    "link":            "link",
    "download":        "download",
    "chevron_left":    "chevron-left",
    "chevron_right":   "chevron-right",
    "save":            "save",
    "send":            "send",
    "briefcase":       "briefcase",
    "pin":             "map-pin",
    "building":        "building",
    "external":        "external-link",
    "folder":          "folder",
    "copy":            "copy",
    "file":            "file-text",
    "warning":         "alert-triangle",
    "import":          "upload",
    "info":            "info",
    "book":            "book-open",
    "bolt":            "zap",
    "bulb":            "lightbulb",
    "target":          "target",
    "question":        "help-circle",
}


def _fetch_svg(lucide_name: str) -> bytes:
    """Télécharge le SVG en blanc."""
    url = f"https://api.iconify.design/lucide/{lucide_name}.svg?color=%23ffffff"
    req = urllib.request.Request(
        url, headers={"User-Agent": "CandidatureBot-Setup"})
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=15) as r:
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}")
        return r.read()


def _svg_to_png(svg_bytes: bytes, size: int = 96) -> bytes:
    """Rasterise un SVG en PNG via rsvg-convert."""
    if not shutil.which("rsvg-convert"):
        raise RuntimeError(
            "rsvg-convert introuvable. Installe-le via : brew install librsvg"
        )
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f_svg:
        f_svg.write(svg_bytes)
        svg_path = f_svg.name
    try:
        result = subprocess.run(
            ["rsvg-convert",
             "--width", str(size),
             "--height", str(size),
             svg_path],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(f"rsvg-convert error: {result.stderr.decode()[:200]}")
        return result.stdout
    finally:
        try:
            os.unlink(svg_path)
        except OSError:
            pass


def main():
    out = Path(__file__).resolve().parent / "assets" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    print(f"Téléchargement de {len(ICONS)} icônes Lucide → {out}\n")
    ok, fail = 0, 0
    for alias, lucide_name in ICONS.items():
        target = out / f"{alias}.png"
        try:
            svg_data = _fetch_svg(lucide_name)
            png_data = _svg_to_png(svg_data, size=96)
            if len(png_data) < 100:
                raise RuntimeError(f"PNG trop court ({len(png_data)} bytes)")
            target.write_bytes(png_data)
            print(f"  ✓ {alias:18s} → {lucide_name:18s}  ({len(png_data)} bytes)")
            ok += 1
        except Exception as e:
            print(f"  ✗ {alias:18s} → ERREUR : {str(e)[:60]}")
            fail += 1
    print(f"\n{ok}/{len(ICONS)} téléchargées. {fail} échec(s).")
    if ok > 0:
        print(f"Dossier : {out}")


if __name__ == "__main__":
    main()
