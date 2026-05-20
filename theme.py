"""
Thème visuel inspiré de Disco DAW : palette dark professionnelle,
typographie système, icônes vectorielles dessinées à la main avec PIL.

Aucun emoji — tout en couleur, texte caps + letterspacing, badges.
"""
from __future__ import annotations
from PIL import Image, ImageDraw

# ─── PALETTE ────────────────────────────────────────────────────
class Colors:
    # Fonds
    bg_panel      = "#1f1f23"   # fond principal
    bg_panel_alt  = "#28282d"   # cartes, sections
    bg_hover      = "#33333a"
    border        = "#3a3a40"

    # Textes
    text_primary   = "#e8e8e8"  # labels actifs
    text_secondary = "#b0b0b0"  # sous-titres, descriptions
    text_muted     = "#808080"  # placeholders, infos discrètes

    # Accents (palette bleue broadcast)
    accent         = "#1f6aa5"  # bleu primaire (boutons primaires, item sidebar actif)
    accent_hover   = "#2a7ec0"
    accent_dark    = "#144870"  # variante foncée (badges, états pressés)
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
    family = "Helvetica"  # CTk gère le fallback système
    # tailles
    h1 = 20    # titre de page
    h2 = 15    # titre de section
    label = 13 # label gras
    body = 12  # texte courant
    small = 11 # infos discrètes
    micro = 10 # badges

    # letterspacing pour les titres (style DAW "MASTER")
    title_spacing = 2


# ─── ICÔNES PAINT (PIL → CTkImage) ──────────────────────────────
def _new_canvas(size):
    """Canvas RGBA transparent, taille en px."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _hex_to_rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)


def icon_search(size=20, color=Colors.text_secondary):
    """Loupe — cercle + manche."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    r = int(size * 0.35)
    cx, cy = int(size * 0.40), int(size * 0.40)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=2)
    d.line([(cx + r * 0.70, cy + r * 0.70),
            (size - 3, size - 3)], fill=c, width=2)
    return img


def icon_plus(size=20, color=Colors.text_primary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    m = int(size * 0.25)
    d.line([(m, size // 2), (size - m, size // 2)], fill=c, width=2)
    d.line([(size // 2, m), (size // 2, size - m)], fill=c, width=2)
    return img


def icon_trash(size=20, color=Colors.red_danger):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    # Couvercle
    d.line([(int(size * 0.15), int(size * 0.30)),
            (int(size * 0.85), int(size * 0.30))], fill=c, width=2)
    # Poignée
    d.line([(int(size * 0.38), int(size * 0.22)),
            (int(size * 0.62), int(size * 0.22))], fill=c, width=2)
    # Corps
    d.rectangle([int(size * 0.25), int(size * 0.30),
                 int(size * 0.75), int(size * 0.85)], outline=c, width=2)
    # 2 stries verticales
    for x_frac in (0.42, 0.58):
        x = int(size * x_frac)
        d.line([(x, int(size * 0.42)), (x, int(size * 0.75))], fill=c, width=1)
    return img


def icon_settings(size=20, color=Colors.text_secondary):
    """Engrenage simplifié."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = size // 2, size // 2
    r_out = int(size * 0.38)
    r_in = int(size * 0.18)
    d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], outline=c, width=2)
    d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], outline=c, width=2)
    # 4 dents (croix sur l'extérieur)
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        x1 = cx + dx * (r_out + 1)
        y1 = cy + dy * (r_out + 1)
        x2 = cx + dx * (r_out + int(size * 0.12))
        y2 = cy + dy * (r_out + int(size * 0.12))
        d.line([(x1, y1), (x2, y2)], fill=c, width=2)
    return img


def icon_user(size=20, color=Colors.text_secondary):
    """Bonhomme silhouette."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    # Tête
    head_r = int(size * 0.16)
    cx = size // 2
    d.ellipse([cx - head_r, int(size * 0.18),
               cx + head_r, int(size * 0.18) + head_r * 2],
              outline=c, width=2)
    # Corps (arc bas)
    d.arc([int(size * 0.18), int(size * 0.50),
           int(size * 0.82), int(size * 1.05)],
          180, 360, fill=c, width=2)
    return img


def icon_list(size=20, color=Colors.text_secondary):
    """Liste — 3 lignes horizontales avec petits points."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    for i, y_frac in enumerate([0.28, 0.50, 0.72]):
        y = int(size * y_frac)
        # Point
        d.ellipse([int(size * 0.18), y - 2,
                   int(size * 0.18) + 4, y + 2], fill=c)
        # Ligne
        d.line([(int(size * 0.36), y), (int(size * 0.85), y)], fill=c, width=2)
    return img


def icon_refresh(size=20, color=Colors.text_secondary):
    """Flèche circulaire."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = size // 2, size // 2
    r = int(size * 0.32)
    # 3/4 de cercle
    d.arc([cx - r, cy - r, cx + r, cy + r], 30, 300, fill=c, width=2)
    # Petite flèche en haut-droite
    a = int(size * 0.12)
    d.polygon([
        (cx + r, cy - r + 2),
        (cx + r - a, cy - r + a),
        (cx + r + a // 2, cy - r + a + 2),
    ], fill=c)
    return img


def icon_check(size=20, color=Colors.green_ok):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    d.line([(int(size * 0.22), int(size * 0.55)),
            (int(size * 0.42), int(size * 0.75)),
            (int(size * 0.80), int(size * 0.30))],
           fill=c, width=2, joint="curve")
    return img


def icon_cross(size=20, color=Colors.red_danger):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    m = int(size * 0.25)
    d.line([(m, m), (size - m, size - m)], fill=c, width=2)
    d.line([(size - m, m), (m, size - m)], fill=c, width=2)
    return img


def icon_play(size=20, color=Colors.text_primary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    d.polygon([
        (int(size * 0.32), int(size * 0.22)),
        (int(size * 0.32), int(size * 0.78)),
        (int(size * 0.78), int(size * 0.50)),
    ], fill=c)
    return img


def icon_stop(size=20, color=Colors.red_danger):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    d.rectangle([int(size * 0.28), int(size * 0.28),
                 int(size * 0.72), int(size * 0.72)], fill=c)
    return img


def icon_loop(size=20, color=Colors.text_secondary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = size // 2, size // 2
    r = int(size * 0.32)
    d.arc([cx - r, cy - r, cx + r, cy + r], 0, 270, fill=c, width=2)
    # Flèche fin de la courbe
    a = int(size * 0.10)
    d.polygon([
        (cx + r, cy + 1),
        (cx + r - a - 1, cy - a),
        (cx + r + a, cy - a + 1),
    ], fill=c)
    return img


def icon_mail(size=20, color=Colors.text_secondary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    # Enveloppe
    box = [int(size * 0.15), int(size * 0.28),
           int(size * 0.85), int(size * 0.72)]
    d.rectangle(box, outline=c, width=2)
    # Triangle du rabat
    d.line([(box[0], box[1]), (size // 2, int(size * 0.55)), (box[2], box[1])],
           fill=c, width=2)
    return img


def icon_link(size=20, color=Colors.blue_link):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    # 2 maillons inclinés à 45°
    r = int(size * 0.20)
    # Premier maillon (en haut-gauche)
    d.arc([int(size * 0.10), int(size * 0.40),
           int(size * 0.55), int(size * 0.85)], 90, 270, fill=c, width=2)
    # Deuxième (bas-droit)
    d.arc([int(size * 0.45), int(size * 0.15),
           int(size * 0.90), int(size * 0.60)], 270, 90, fill=c, width=2)
    # Trait de connexion
    d.line([(int(size * 0.38), int(size * 0.60)),
            (int(size * 0.62), int(size * 0.40))], fill=c, width=2)
    return img


def icon_download(size=20, color=Colors.text_secondary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    cx = size // 2
    # Flèche vers le bas
    d.line([(cx, int(size * 0.20)), (cx, int(size * 0.62))], fill=c, width=2)
    d.polygon([
        (cx, int(size * 0.72)),
        (int(size * 0.32), int(size * 0.50)),
        (int(size * 0.68), int(size * 0.50)),
    ], fill=c)
    # Socle
    d.line([(int(size * 0.20), int(size * 0.80)),
            (int(size * 0.80), int(size * 0.80))], fill=c, width=2)
    return img


def icon_chevron_left(size=20, color=Colors.text_secondary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    d.line([(int(size * 0.60), int(size * 0.22)),
            (int(size * 0.36), int(size * 0.50)),
            (int(size * 0.60), int(size * 0.78))],
           fill=c, width=2, joint="curve")
    return img


def icon_chevron_right(size=20, color=Colors.text_secondary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    d.line([(int(size * 0.40), int(size * 0.22)),
            (int(size * 0.64), int(size * 0.50)),
            (int(size * 0.40), int(size * 0.78))],
           fill=c, width=2, joint="curve")
    return img


def icon_save(size=20, color=Colors.text_primary):
    """Icône disquette / save (carré avec coin coupé + label intérieur)."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    m = int(size * 0.15)
    # Contour disquette (carré avec coin haut-droit coupé)
    pts = [
        (m, m),
        (size - m - int(size * 0.15), m),
        (size - m, m + int(size * 0.15)),
        (size - m, size - m),
        (m, size - m),
    ]
    d.polygon(pts, outline=c, width=2)
    # Label haut (slot d'écriture)
    d.rectangle([int(size * 0.30), m,
                 int(size * 0.70), int(size * 0.32)], outline=c, width=2)
    # Étiquette interne en bas
    d.rectangle([int(size * 0.28), int(size * 0.55),
                 int(size * 0.72), int(size * 0.80)], outline=c, width=2)
    return img


def icon_mail_send(size=20, color=Colors.text_primary):
    """Avion en papier (envoi)."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    d.polygon([
        (int(size * 0.15), int(size * 0.78)),
        (int(size * 0.85), int(size * 0.22)),
        (int(size * 0.55), int(size * 0.85)),
        (int(size * 0.45), int(size * 0.58)),
        (int(size * 0.20), int(size * 0.48)),
    ], outline=c, width=2)
    return img


def icon_briefcase(size=20, color=Colors.text_secondary):
    """Mallette (catégorie travail / contrat)."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    # Corps
    d.rectangle([int(size * 0.15), int(size * 0.38),
                 int(size * 0.85), int(size * 0.82)], outline=c, width=2)
    # Poignée
    d.line([(int(size * 0.40), int(size * 0.38)),
            (int(size * 0.40), int(size * 0.25)),
            (int(size * 0.60), int(size * 0.25)),
            (int(size * 0.60), int(size * 0.38))], fill=c, width=2)
    # Séparation centrale
    d.line([(int(size * 0.15), int(size * 0.55)),
            (int(size * 0.85), int(size * 0.55))], fill=c, width=2)
    return img


def icon_pin(size=20, color=Colors.text_secondary):
    """Pin / map marker."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    cx = size // 2
    # Goutte
    d.arc([int(size * 0.20), int(size * 0.15),
           int(size * 0.80), int(size * 0.75)], 0, 360, fill=c, width=2)
    # Cercle centre
    d.ellipse([cx - 3, int(size * 0.38), cx + 3, int(size * 0.50)], outline=c, width=1)
    # Pointe bas
    d.line([(cx, int(size * 0.65)), (cx, int(size * 0.88))], fill=c, width=2)
    return img


def icon_building(size=20, color=Colors.text_secondary):
    """Immeuble (entreprise)."""
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    # Contour
    d.rectangle([int(size * 0.20), int(size * 0.18),
                 int(size * 0.80), int(size * 0.85)], outline=c, width=2)
    # Fenêtres (3 lignes × 2 colonnes)
    for row in range(3):
        for col in range(2):
            x1 = int(size * (0.30 + col * 0.25))
            y1 = int(size * (0.28 + row * 0.18))
            d.rectangle([x1, y1, x1 + int(size * 0.12), y1 + int(size * 0.10)],
                        outline=c, width=1)
    return img


def icon_question(size=20, color=Colors.text_secondary):
    img, d = _new_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = size // 2, size // 2
    r = int(size * 0.42)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=2)
    # ?
    d.arc([cx - int(size * 0.13), cy - int(size * 0.18),
           cx + int(size * 0.13), cy + int(size * 0.05)],
          180, 360, fill=c, width=2)
    d.line([(cx, cy + 1), (cx, cy + int(size * 0.15))], fill=c, width=2)
    d.ellipse([cx - 1, cy + int(size * 0.22),
               cx + 1, cy + int(size * 0.24)], fill=c)
    return img


# ─── Construction CTkImage à la demande ─────────────────────────
def ctk_icon(icon_fn, size=20, **kwargs):
    """Construit un CTkImage depuis une fonction icon_*.
    À appeler après ctk.set_appearance_mode (sinon Image base manquante)."""
    import customtkinter as ctk
    img = icon_fn(size=size, **kwargs)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


# ─── Helpers ────────────────────────────────────────────────────
def caps(s):
    """Met en majuscules + ajoute des espaces (effet letterspacing visuel)."""
    return s.upper()
