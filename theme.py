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
# Stratégie pour des icônes line-art type Lucide :
#   1. On dessine sur un canvas HD (×4 la taille finale).
#   2. Strokes plus épais à cette échelle (8-10 px sur 96 px = ~2 px à 24 px).
#   3. Resize LANCZOS pour anti-aliasing propre.
# Résultat : lignes fines et nettes, pas de jaggies, look pro.

_SUPERSAMPLE = 4
_HD_STROKE = 6        # stroke épaisseur sur canvas HD (donne ~1.5 px en final)
_HD_STROKE_BOLD = 8


def _new_canvas(size):
    """Canvas final RGBA. Conservé pour compat — utilisé pour fallback."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _hex_to_rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)


def _hd_canvas(size):
    """Canvas HD (×4) pour dessins anti-aliasés. Retourne (img, draw, hd_size)."""
    hd = size * _SUPERSAMPLE
    img = Image.new("RGBA", (hd, hd), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), hd


def _finalize(img, size):
    """Resize LANCZOS (anti-aliased) vers la taille finale."""
    if img.size == (size, size):
        return img
    return img.resize((size, size), Image.LANCZOS)


def _line(d, p1, p2, color, width=_HD_STROKE):
    """Trace une ligne avec extrémités arrondies (cap rond)."""
    d.line([p1, p2], fill=color, width=width)
    # Caps ronds aux extrémités
    r = width // 2
    for (cx, cy) in (p1, p2):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def _circle(d, cx, cy, r, color, width=_HD_STROKE, fill=None):
    """Cercle outline ou plein."""
    if fill is not None:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    if width > 0:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=width)


def icon_search(size=20, color=Colors.text_secondary):
    """Loupe — cercle + manche oblique (style Lucide)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    r = int(hd * 0.30)
    cx, cy = int(hd * 0.42), int(hd * 0.42)
    _circle(d, cx, cy, r, c, width=_HD_STROKE)
    # Manche : ligne du bord du cercle (à 45°) vers le coin bas-droit
    p1 = (cx + int(r * 0.71), cy + int(r * 0.71))
    p2 = (int(hd * 0.82), int(hd * 0.82))
    _line(d, p1, p2, c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_plus(size=20, color=Colors.text_primary):
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    m = int(hd * 0.25)
    _line(d, (m, hd // 2), (hd - m, hd // 2), c, _HD_STROKE)
    _line(d, (hd // 2, m), (hd // 2, hd - m), c, _HD_STROKE)
    return _finalize(img, size)


def icon_trash(size=20, color=Colors.red_danger):
    """Poubelle line-art : couvercle + corps + 2 stries verticales."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Couvercle (ligne horizontale en haut)
    _line(d, (int(hd * 0.18), int(hd * 0.30)),
             (int(hd * 0.82), int(hd * 0.30)), c, _HD_STROKE)
    # Poignée (petite barre au-dessus)
    _line(d, (int(hd * 0.38), int(hd * 0.20)),
             (int(hd * 0.62), int(hd * 0.20)), c, _HD_STROKE)
    # Corps (rectangle avec coins arrondis simulés)
    box = [int(hd * 0.26), int(hd * 0.33),
           int(hd * 0.74), int(hd * 0.85)]
    d.rectangle(box, outline=c, width=_HD_STROKE)
    # 2 stries verticales internes
    for x_frac in (0.42, 0.58):
        x = int(hd * x_frac)
        _line(d, (x, int(hd * 0.45)),
                 (x, int(hd * 0.75)), c, _HD_STROKE // 2)
    return _finalize(img, size)


def icon_settings(size=20, color=Colors.text_secondary):
    """Engrenage line-art : anneau + 8 dents trapézoïdales + cercle central.
    Les dents sont des petits rectangles, pas des traits → lecture engrenage."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = hd // 2, hd // 2
    r_in = int(hd * 0.14)
    r_out = int(hd * 0.30)
    r_teeth = int(hd * 0.42)
    # Cercle central
    _circle(d, cx, cy, r_in, c, width=_HD_STROKE)
    # Anneau extérieur
    _circle(d, cx, cy, r_out, c, width=_HD_STROKE)
    # 8 dents trapézoïdales — épaisseur perpendiculaire au rayon
    import math
    teeth_count = 8
    half_w = int(hd * 0.05)
    for i in range(teeth_count):
        angle = (i / teeth_count) * 2 * math.pi
        cosA, sinA = math.cos(angle), math.sin(angle)
        # Perpendiculaire
        px, py = -sinA, cosA
        # 4 coins du trapèze : base sur le bord du r_out, sommet sur r_teeth
        x1 = cx + int(cosA * r_out + px * half_w)
        y1 = cy + int(sinA * r_out + py * half_w)
        x2 = cx + int(cosA * r_teeth + px * half_w * 0.7)
        y2 = cy + int(sinA * r_teeth + py * half_w * 0.7)
        x3 = cx + int(cosA * r_teeth - px * half_w * 0.7)
        y3 = cy + int(sinA * r_teeth - py * half_w * 0.7)
        x4 = cx + int(cosA * r_out - px * half_w)
        y4 = cy + int(sinA * r_out - py * half_w)
        d.polygon([(x1, y1), (x2, y2), (x3, y3), (x4, y4)],
                  outline=c, fill=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_user(size=20, color=Colors.text_secondary):
    """Silhouette : cercle (tête) + arc (épaules)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx = hd // 2
    # Tête (cercle)
    head_r = int(hd * 0.17)
    head_cy = int(hd * 0.30)
    _circle(d, cx, head_cy, head_r, c, width=_HD_STROKE)
    # Épaules / corps (arc bas)
    d.arc([int(hd * 0.15), int(hd * 0.52),
           int(hd * 0.85), int(hd * 1.10)],
          180, 360, fill=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_list(size=20, color=Colors.text_secondary):
    """Liste : 3 lignes horizontales avec points (style menu)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    for y_frac in (0.28, 0.50, 0.72):
        y = int(hd * y_frac)
        # Point gauche
        pr = int(hd * 0.04)
        _circle(d, int(hd * 0.22), y, pr, c, width=0, fill=c)
        # Ligne droite
        _line(d, (int(hd * 0.34), y), (int(hd * 0.82), y), c, _HD_STROKE)
    return _finalize(img, size)


def icon_refresh(size=20, color=Colors.text_secondary):
    """Flèche circulaire (3/4 cercle + pointe tangente)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = hd // 2, hd // 2
    r = int(hd * 0.30)
    # 3/4 d'arc — de 45° à 315° (ouverture en haut)
    d.arc([cx - r, cy - r, cx + r, cy + r], 45, 315,
          fill=c, width=_HD_STROKE)
    # Pointe de flèche tangente à 45° (le point de départ de l'arc)
    import math
    a_rad = _math.radians(45)
    # Centre de la pointe = sur l'arc à 45°
    px = cx + int(r * _math.cos(a_rad))
    py = cy + int(r * _math.sin(a_rad))
    # Vecteur tangent (90° du rayon)
    tg = (-_math.sin(a_rad), _math.cos(a_rad))
    # Vecteur normal sortant
    nm = (_math.cos(a_rad), _math.sin(a_rad))
    sz = int(hd * 0.12)
    d.polygon([
        (px + int(nm[0] * sz), py + int(nm[1] * sz)),         # pointe
        (px + int(tg[0] * sz), py + int(tg[1] * sz)),         # côté tangent +
        (px - int(tg[0] * sz), py - int(tg[1] * sz)),         # côté tangent -
    ], fill=c)
    return _finalize(img, size)


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
    """Boucle / refresh routine — arc 270° + pointe tangente."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = hd // 2, hd // 2
    r = int(hd * 0.30)
    # Arc de 45° à 315° = 3/4 cercle (ouverture en haut)
    d.arc([cx - r, cy - r, cx + r, cy + r], 45, 315,
          fill=c, width=_HD_STROKE)
    # Pointe tangente à la fin de l'arc (315°)
    end_a = _math.radians(315)
    px = cx + int(r * _math.cos(end_a))
    py = cy + int(r * _math.sin(end_a))
    tg = (-_math.sin(end_a), _math.cos(end_a))     # vecteur tangent
    nm = (_math.cos(end_a), _math.sin(end_a))      # vecteur normal sortant
    sz = int(hd * 0.12)
    d.polygon([
        (px + int(nm[0] * sz), py + int(nm[1] * sz)),
        (px + int(tg[0] * sz), py + int(tg[1] * sz)),
        (px - int(tg[0] * sz), py - int(tg[1] * sz)),
    ], fill=c)
    return _finalize(img, size)


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
    """Chaîne — 2 demi-pilules superposées + barre de jonction (Lucide link)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Maillon gauche (demi-pilule horizontale, ouverte à droite)
    # arc 90° → 270° = côté droit du cercle ouvert
    left_box = [int(hd * 0.10), int(hd * 0.36),
                int(hd * 0.52), int(hd * 0.64)]
    d.arc(left_box, 90, 270, fill=c, width=_HD_STROKE)
    # Côté plat (droite) du maillon gauche : 2 traits horizontaux qui ferment
    _line(d, (int(hd * 0.31), int(hd * 0.36)),
             (int(hd * 0.46), int(hd * 0.36)), c, _HD_STROKE)
    _line(d, (int(hd * 0.31), int(hd * 0.64)),
             (int(hd * 0.46), int(hd * 0.64)), c, _HD_STROKE)

    # Maillon droit (demi-pilule horizontale, ouverte à gauche)
    right_box = [int(hd * 0.48), int(hd * 0.36),
                 int(hd * 0.90), int(hd * 0.64)]
    d.arc(right_box, 270, 90, fill=c, width=_HD_STROKE)
    _line(d, (int(hd * 0.54), int(hd * 0.36)),
             (int(hd * 0.69), int(hd * 0.36)), c, _HD_STROKE)
    _line(d, (int(hd * 0.54), int(hd * 0.64)),
             (int(hd * 0.69), int(hd * 0.64)), c, _HD_STROKE)

    # Barre de jonction horizontale au centre
    _line(d, (int(hd * 0.36), int(hd * 0.50)),
             (int(hd * 0.64), int(hd * 0.50)), c, _HD_STROKE)
    return _finalize(img, size)


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
    """Disquette — carré avec coin coupé + label haut + étiquette intérieure."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    m = int(hd * 0.18)
    chamfer = int(hd * 0.15)
    # Contour disquette (polygone avec coin haut-droit coupé)
    pts = [
        (m, m),
        (hd - m - chamfer, m),
        (hd - m, m + chamfer),
        (hd - m, hd - m),
        (m, hd - m),
    ]
    d.polygon(pts, outline=c, width=_HD_STROKE)
    # Slot d'écriture en haut
    d.rectangle([int(hd * 0.32), m,
                 int(hd * 0.68), int(hd * 0.32)],
                outline=c, width=_HD_STROKE)
    # Étiquette en bas
    d.rectangle([int(hd * 0.28), int(hd * 0.55),
                 int(hd * 0.72), int(hd * 0.78)],
                outline=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_mail_send(size=20, color=Colors.text_primary):
    """Avion en papier (envoi) — alias vers icon_send qui est correctement
    dessiné (l'ancienne version sortait 2 triangles disjoints)."""
    return icon_send(size=size, color=color)


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
    """Pin / map marker — vraie goutte avec pointe en bas."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx = hd // 2
    head_r = int(hd * 0.28)
    head_cy = int(hd * 0.36)
    # Demi-cercle haut (le bulbe du pin) = arc 180–360°
    d.arc([cx - head_r, head_cy - head_r,
           cx + head_r, head_cy + head_r],
          180, 360, fill=c, width=_HD_STROKE)
    # 2 lignes diagonales du bord du cercle vers la pointe en bas
    bottom_y = int(hd * 0.92)
    _line(d, (cx - head_r, head_cy),
             (cx, bottom_y), c, _HD_STROKE)
    _line(d, (cx + head_r, head_cy),
             (cx, bottom_y), c, _HD_STROKE)
    # Petit cercle au centre du bulbe (le trou)
    _circle(d, cx, head_cy, int(hd * 0.08), c, width=_HD_STROKE)
    return _finalize(img, size)


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
    """Aide — cercle + point d'interrogation interne (lisible)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = hd // 2, hd // 2
    r = int(hd * 0.42)
    _circle(d, cx, cy, r, c, width=_HD_STROKE)
    # Arc supérieur du ? — plus grand pour ne pas ressembler à un !
    arc_r = int(hd * 0.18)
    arc_cy = int(hd * 0.38)  # centre de l'arc, descendu
    d.arc([cx - arc_r, arc_cy - arc_r,
           cx + arc_r, arc_cy + arc_r],
          180, 360, fill=c, width=_HD_STROKE)
    # Trait vertical descendant du bas-droit de l'arc
    # Le bas de l'arc en mode "arc supérieur" est à arc_cy (côté médian)
    _line(d, (cx, arc_cy),
             (cx, int(hd * 0.66)), c, _HD_STROKE)
    # Point en bas (séparé du trait par un petit gap)
    _circle(d, cx, int(hd * 0.78), int(hd * 0.05),
            c, width=0, fill=c)
    return _finalize(img, size)


# ─── Nouvelles icônes Lucide-style (v1.0.16) ────────────────────
import math as _math


def icon_external(size=20, color=Colors.blue_link):
    """Flèche sortante (lien externe) — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Carré arrondi en bas-gauche (la "fenêtre")
    box = [int(hd * 0.10), int(hd * 0.30),
           int(hd * 0.65), int(hd * 0.85)]
    d.rectangle(box, outline=c, width=_HD_STROKE)
    # Coin haut-droit ouvert (path partiel)
    # Carré recouvre une partie pour masquer l'ouverture
    d.rectangle([int(hd * 0.55), int(hd * 0.20),
                 int(hd * 0.92), int(hd * 0.45)],
                fill=(0, 0, 0, 0))
    # Flèche sortante
    _line(d, (int(hd * 0.45), int(hd * 0.55)),
             (int(hd * 0.85), int(hd * 0.15)), c, _HD_STROKE)
    # Pointe de flèche en haut-droite
    d.polygon([
        (int(hd * 0.65), int(hd * 0.15)),
        (int(hd * 0.85), int(hd * 0.15)),
        (int(hd * 0.85), int(hd * 0.35)),
    ], outline=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_folder(size=20, color=Colors.text_secondary):
    """Dossier — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Onglet en haut
    d.polygon([
        (int(hd * 0.10), int(hd * 0.30)),
        (int(hd * 0.42), int(hd * 0.30)),
        (int(hd * 0.50), int(hd * 0.22)),
        (int(hd * 0.85), int(hd * 0.22)),
        (int(hd * 0.90), int(hd * 0.30)),
        (int(hd * 0.90), int(hd * 0.78)),
        (int(hd * 0.10), int(hd * 0.78)),
    ], outline=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_copy(size=20, color=Colors.text_secondary):
    """2 rectangles superposés (clipboard) — Lucide.
    Pas de fill : on dessine seulement les segments visibles pour rester
    transparent et lisible sur n'importe quel fond."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Rectangle arrière (haut-gauche) — on dessine seulement les
    # segments NON cachés par le rectangle avant
    # Box arrière : (a_left, a_top, a_right, a_bot)
    a_l, a_t, a_r, a_b = int(hd * 0.18), int(hd * 0.12), \
                          int(hd * 0.62), int(hd * 0.62)
    # Rectangle avant : (f_left, f_top, f_right, f_bot)
    f_l, f_t, f_r, f_b = int(hd * 0.38), int(hd * 0.32), \
                          int(hd * 0.86), int(hd * 0.86)
    # Segments visibles du rectangle ARRIÈRE :
    #   - top complet
    _line(d, (a_l, a_t), (a_r, a_t), c, _HD_STROKE)
    #   - left complet
    _line(d, (a_l, a_t), (a_l, a_b), c, _HD_STROKE)
    #   - right (partie au-dessus du front)
    _line(d, (a_r, a_t), (a_r, f_t), c, _HD_STROKE)
    #   - bottom (partie à gauche du front)
    _line(d, (a_l, a_b), (f_l, a_b), c, _HD_STROKE)
    # Rectangle AVANT (entier outline)
    d.rectangle([f_l, f_t, f_r, f_b], outline=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_file(size=20, color=Colors.text_secondary):
    """Document avec lignes intérieures — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Contour avec coin haut-droit coupé
    pts = [
        (int(hd * 0.22), int(hd * 0.10)),
        (int(hd * 0.62), int(hd * 0.10)),
        (int(hd * 0.78), int(hd * 0.26)),
        (int(hd * 0.78), int(hd * 0.88)),
        (int(hd * 0.22), int(hd * 0.88)),
    ]
    d.polygon(pts, outline=c, width=_HD_STROKE)
    # Coin replié (petit carré)
    d.polygon([
        (int(hd * 0.62), int(hd * 0.10)),
        (int(hd * 0.62), int(hd * 0.26)),
        (int(hd * 0.78), int(hd * 0.26)),
    ], outline=c, width=_HD_STROKE)
    # 3 lignes intérieures
    for y_frac in (0.50, 0.62, 0.74):
        y = int(hd * y_frac)
        _line(d, (int(hd * 0.32), y), (int(hd * 0.68), y), c, _HD_STROKE)
    return _finalize(img, size)


def icon_warning(size=20, color=Colors.amber):
    """Triangle alerte — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Triangle
    d.polygon([
        (int(hd * 0.50), int(hd * 0.12)),
        (int(hd * 0.92), int(hd * 0.85)),
        (int(hd * 0.08), int(hd * 0.85)),
    ], outline=c, width=_HD_STROKE)
    # ! vertical
    _line(d, (int(hd * 0.50), int(hd * 0.40)),
             (int(hd * 0.50), int(hd * 0.60)), c, _HD_STROKE)
    # Point bas
    _circle(d, int(hd * 0.50), int(hd * 0.74),
            int(hd * 0.04), c, width=0, fill=c)
    return _finalize(img, size)


def icon_send(size=20, color=Colors.text_primary):
    """Avion en papier — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Triangle pointé en haut-droite (le corps de l'avion)
    d.polygon([
        (int(hd * 0.90), int(hd * 0.10)),
        (int(hd * 0.10), int(hd * 0.45)),
        (int(hd * 0.45), int(hd * 0.55)),
        (int(hd * 0.55), int(hd * 0.90)),
    ], outline=c, width=_HD_STROKE)
    # Ligne du pli intérieur
    _line(d, (int(hd * 0.90), int(hd * 0.10)),
             (int(hd * 0.45), int(hd * 0.55)), c, _HD_STROKE)
    return _finalize(img, size)


def icon_close(size=20, color=Colors.text_secondary):
    """X de fermeture — équivalent à icon_cross mais ici sémantique close."""
    return icon_cross(size=size, color=color)


def icon_import(size=20, color=Colors.text_secondary):
    """Flèche descendante dans une boîte (import) — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Flèche
    cx = hd // 2
    _line(d, (cx, int(hd * 0.15)), (cx, int(hd * 0.62)), c, _HD_STROKE)
    a = int(hd * 0.10)
    d.polygon([
        (cx, int(hd * 0.72)),
        (cx - a, int(hd * 0.52)),
        (cx + a, int(hd * 0.52)),
    ], fill=c)
    # Boîte ouverte en bas (lignes L)
    _line(d, (int(hd * 0.20), int(hd * 0.70)),
             (int(hd * 0.20), int(hd * 0.85)), c, _HD_STROKE)
    _line(d, (int(hd * 0.80), int(hd * 0.70)),
             (int(hd * 0.80), int(hd * 0.85)), c, _HD_STROKE)
    _line(d, (int(hd * 0.20), int(hd * 0.85)),
             (int(hd * 0.80), int(hd * 0.85)), c, _HD_STROKE)
    return _finalize(img, size)


def icon_info(size=20, color=Colors.text_secondary):
    """i dans un cercle — Lucide."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = hd // 2, hd // 2
    r = int(hd * 0.40)
    _circle(d, cx, cy, r, c, width=_HD_STROKE)
    # Point haut
    _circle(d, cx, int(hd * 0.32), int(hd * 0.04), c, width=0, fill=c)
    # Barre verticale
    _line(d, (cx, int(hd * 0.46)),
             (cx, int(hd * 0.70)), c, _HD_STROKE)
    return _finalize(img, size)


# ─── icônes pour les TONS de lettre ──────────────────────────────
def icon_book(size=20, color=Colors.text_secondary):
    """Livre ouvert / classique."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Reliure du livre (rectangle avec ouverture en bas-droite)
    pts = [
        (int(hd * 0.15), int(hd * 0.15)),
        (int(hd * 0.85), int(hd * 0.15)),
        (int(hd * 0.85), int(hd * 0.78)),
        (int(hd * 0.25), int(hd * 0.78)),
        (int(hd * 0.20), int(hd * 0.85)),
        (int(hd * 0.20), int(hd * 0.20)),
    ]
    d.line(pts + [pts[0]], fill=c, width=_HD_STROKE, joint="curve")
    # 2 lignes de texte
    for y_frac in (0.36, 0.50):
        y = int(hd * y_frac)
        _line(d, (int(hd * 0.32), y), (int(hd * 0.72), y), c, _HD_STROKE)
    return _finalize(img, size)


def icon_bolt(size=20, color=Colors.amber):
    """Éclair — Dynamique."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    d.polygon([
        (int(hd * 0.55), int(hd * 0.08)),
        (int(hd * 0.20), int(hd * 0.55)),
        (int(hd * 0.45), int(hd * 0.55)),
        (int(hd * 0.40), int(hd * 0.92)),
        (int(hd * 0.80), int(hd * 0.40)),
        (int(hd * 0.50), int(hd * 0.40)),
        (int(hd * 0.55), int(hd * 0.08)),
    ], outline=c, width=_HD_STROKE)
    return _finalize(img, size)


def icon_bulb(size=20, color=Colors.amber):
    """Ampoule — Créatif."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    # Demi-cercle haut (ampoule)
    d.arc([int(hd * 0.22), int(hd * 0.12),
           int(hd * 0.78), int(hd * 0.68)],
          180, 360, fill=c, width=_HD_STROKE)
    # Connexion au pied
    _line(d, (int(hd * 0.30), int(hd * 0.40)),
             (int(hd * 0.30), int(hd * 0.65)), c, _HD_STROKE)
    _line(d, (int(hd * 0.70), int(hd * 0.40)),
             (int(hd * 0.70), int(hd * 0.65)), c, _HD_STROKE)
    # 2 lignes du culot
    _line(d, (int(hd * 0.32), int(hd * 0.72)),
             (int(hd * 0.68), int(hd * 0.72)), c, _HD_STROKE)
    _line(d, (int(hd * 0.36), int(hd * 0.82)),
             (int(hd * 0.64), int(hd * 0.82)), c, _HD_STROKE)
    # Pieds tout en bas (V central)
    _line(d, (int(hd * 0.42), int(hd * 0.88)),
             (int(hd * 0.58), int(hd * 0.88)), c, _HD_STROKE)
    return _finalize(img, size)


def icon_target(size=20, color=Colors.text_secondary):
    """Cible — Direct (3 cercles concentriques)."""
    img, d, hd = _hd_canvas(size)
    c = _hex_to_rgba(color)
    cx, cy = hd // 2, hd // 2
    _circle(d, cx, cy, int(hd * 0.42), c, width=_HD_STROKE)
    _circle(d, cx, cy, int(hd * 0.26), c, width=_HD_STROKE)
    _circle(d, cx, cy, int(hd * 0.10), c, width=0, fill=c)
    return _finalize(img, size)


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
