"""
Génération de PDF pour les lettres de motivation.
Reportlab est utilisé pour un bon support UTF-8 (accents français).
"""
import os
import re
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_JUSTIFY
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def _slug(s, maxlen=40):
    s = re.sub(r"[^\w\-]+", "_", (s or "").strip()) or "lettre"
    return s[:maxlen].strip("_")


def generate_lettre_pdf(text, profil, offre, dest_dir=None):
    """Génère un PDF propre d'une lettre de motivation.
    Retourne le chemin du PDF créé.
    """
    if dest_dir is None:
        try:
            import app_paths
            dest_dir = str(app_paths.pdfs_dir())
        except Exception:
            dest_dir = os.path.join("data", "pdfs")
    os.makedirs(dest_dir, exist_ok=True)

    entreprise = _slug(offre.get("entreprise", ""))
    poste = _slug(offre.get("poste") or offre.get("titre") or "poste")
    filename = f"Lettre_{entreprise}_{poste}.pdf"
    path = os.path.join(dest_dir, filename)

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        title="Lettre de motivation",
        author=f"{profil.get('prenom','')} {profil.get('nom','')}".strip() or "Candidat",
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["Normal"],
        fontName="Helvetica", fontSize=11, leading=16,
        alignment=TA_JUSTIFY, spaceAfter=10,
    )
    header = ParagraphStyle(
        "header", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10, leading=13,
    )
    header_bold = ParagraphStyle(
        "header_bold", parent=header,
        fontName="Helvetica-Bold",
    )
    right = ParagraphStyle(
        "right", parent=header,
        alignment=TA_RIGHT,
    )

    story = []

    # En-tête candidat (haut gauche)
    full_name = f"{profil.get('prenom','').strip()} {profil.get('nom','').strip()}".strip()
    if full_name:
        story.append(Paragraph(full_name, header_bold))
    for key in ("email", "telephone", "ville", "linkedin"):
        v = profil.get(key)
        if v:
            story.append(Paragraph(str(v), header))

    story.append(Spacer(1, 0.6 * cm))

    # Destinataire (entreprise) + date
    entreprise_name = offre.get("entreprise", "").strip()
    if entreprise_name:
        story.append(Paragraph(entreprise_name, header_bold))
        lieu = offre.get("lieu", "").strip()
        if lieu:
            story.append(Paragraph(lieu, header))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(f"Le {date.today().strftime('%d/%m/%Y')}", right))
    story.append(Spacer(1, 0.8 * cm))

    # Objet
    poste_titre = offre.get("poste") or offre.get("titre") or ""
    if poste_titre:
        story.append(Paragraph(
            f"<b>Objet :</b> Candidature au poste de {poste_titre}",
            body,
        ))
        story.append(Spacer(1, 0.4 * cm))

    # Corps de la lettre (paragraphes séparés par double \n)
    for para in (text or "").strip().split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Échapper AVANT d'insérer les <br/> sinon on casse les balises.
        para_html = (
            para.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
        )
        story.append(Paragraph(para_html, body))

    doc.build(story)
    return path
