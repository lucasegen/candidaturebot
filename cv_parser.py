"""
Extraction du texte d'un CV (PDF, DOCX, TXT) + analyse ATS + auto-remplissage profil.

Utilisé par la GUI (section « Mes infos ») pour :
- Extraire le texte
- Détecter automatiquement nom, email, téléphone, compétences, langues, années d'exp
- Scorer la compatibilité ATS (Applicant Tracking System)
"""
import os
import re
from datetime import datetime


# ─────────────────────────────────────────────────────────
# Extraction de texte
# ─────────────────────────────────────────────────────────
def extract_text(path):
    """Extrait le texte d'un CV (PDF, DOCX, TXT). Retourne "" si impossible."""
    if not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower()
    raw = ""
    try:
        if ext == ".pdf":
            raw = _extract_pdf(path)
        elif ext in (".docx", ".doc"):
            raw = _extract_docx(path)
        elif ext in (".txt", ".md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
    except Exception:
        return ""
    return _fix_letter_spacing(raw) if raw else ""


def _fix_letter_spacing(text):
    """Beaucoup de CV (Canva, Figma, Illustrator) exportent avec un letter-spacing
    qui se traduit dans pypdf par des caractères séparés par des espaces :
    'C h i a r a' au lieu de 'Chiara'. On détecte et on recolle.
    Règle : double espace = séparateur de mot, espace simple = séparateur de lettres.
    """
    if not text:
        return text
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        tokens = stripped.split(" ")
        tokens = [t for t in tokens if t]
        if len(tokens) >= 4:
            single_char = sum(1 for t in tokens if len(t) == 1)
            if single_char / len(tokens) >= 0.55:
                # Letter-spaced : double-space -> séparateur ; espace simple -> rien
                line = stripped.replace("  ", "\u0001").replace(" ", "").replace("\u0001", " ")
        out.append(line)
    return "\n".join(out)


def _extract_pdf(path):
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts).strip()
    except ImportError:
        return ""


def _extract_docx(path):
    try:
        import docx
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs).strip()
    except ImportError:
        return ""


# ─────────────────────────────────────────────────────────
# Auto-détection des infos profil
# ─────────────────────────────────────────────────────────
_COMPETENCES_CATALOG = [
    # ── Tech / dev ──
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
    "PHP", "Ruby", "Swift", "Kotlin", "Scala", "Dart", "R", "Bash", "Shell",
    "HTML", "CSS", "SASS", "Tailwind", "Bootstrap",
    "SQL", "NoSQL", "MongoDB", "PostgreSQL", "MySQL", "Redis", "Elasticsearch",
    "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt", "Node.js", "Express",
    "Django", "Flask", "FastAPI", "Spring", "Laravel", "Rails",
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Terraform", "Ansible", "Vagrant",
    "Linux", "Unix", "Git", "GitHub", "GitLab", "Bitbucket",
    "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Travis",
    "REST", "GraphQL", "gRPC", "WebSocket", "OAuth", "JWT",
    "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Keras",
    "NLP", "Data Science", "Pandas", "NumPy", "Scikit-learn", "Jupyter",
    # ── Audiovisuel / vidéo / photo ──
    "Premiere Pro", "Premiere", "After Effects", "Final Cut Pro", "Final Cut",
    "DaVinci Resolve", "DaVinci", "Davinci", "Avid Media Composer", "Avid",
    "Lightroom", "Photoshop", "Illustrator", "InDesign", "Bridge", "Audition",
    "Capture One", "DxO", "Affinity Photo", "Affinity Designer",
    "Logic Pro", "Pro Tools", "Ableton", "FL Studio", "GarageBand", "Reaper",
    "Cinema 4D", "Blender", "Maya", "Houdini", "Nuke", "Fusion",
    "OBS", "Streamlabs", "vMix", "Wirecast",
    "Cadrage", "Montage", "Éclairage", "Eclairage", "Tournage", "Storytelling",
    "Réalisation", "Realisation", "Post-production", "Postproduction",
    "Étalonnage", "Etalonnage", "Sound design", "Mixage", "Compositing",
    "Animation", "Motion design", "Motion Design", "VFX", "SFX",
    "Plateau", "Captation", "Multicaméra", "Multicamera", "Multi-caméra",
    "Photographie", "Photo argentique", "Studio photo", "Retouche photo",
    # ── Design / UX / créa ──
    "Figma", "Sketch", "Adobe XD", "InVision", "Canva", "Procreate", "Framer",
    "UI", "UX", "UI/UX", "Design system", "Wireframing", "Prototypage", "Branding",
    "Identité visuelle", "Direction artistique", "Typographie",
    # ── Office / business ──
    "Excel", "Word", "PowerPoint", "Outlook", "OneDrive", "Google Workspace",
    "Notion", "Trello", "Asana", "Jira", "Confluence", "Slack", "Teams",
    "SAP", "Salesforce", "HubSpot", "Zoho", "Pipedrive", "Mailchimp",
    "Comptabilité", "Finance", "Audit", "Contrôle de gestion",
    # ── Marketing / web ──
    "SEO", "SEA", "SMO", "Google Ads", "Meta Ads", "TikTok Ads",
    "Google Analytics", "GA4", "Tag Manager", "Search Console",
    "Marketing digital", "Marketing", "Copywriting", "Content marketing",
    "Réseaux sociaux", "Community management", "Social media",
    "WordPress", "Webflow", "Shopify", "Wix", "Squarespace",
    # ── Méthodes / soft skills ──
    "Gestion de projet", "Management", "Leadership", "Communication",
    "Travail d'équipe", "Travail d équipe", "Autonomie", "Rigueur", "Créativité",
    "Adaptabilité", "Organisation", "Polyvalence", "Esprit d'équipe",
    "Agile", "Scrum", "Kanban", "Lean", "Six Sigma", "PMP", "Prince2",
    "MERISE", "UML",
]

_LANGUES_CATALOG = [
    "Français", "Francais", "Anglais", "Espagnol", "Allemand", "Italien",
    "Portugais", "Chinois", "Mandarin", "Japonais", "Coréen", "Coreen",
    "Arabe", "Russe", "Néerlandais", "Neerlandais", "Suédois", "Suedois",
    "Norvégien", "Norvegien", "Danois", "Polonais", "Tchèque", "Tcheque",
    "Hongrois", "Roumain", "Grec", "Turc", "Hébreu", "Hebreu",
    "Hindi", "Vietnamien", "Thaï", "Thai", "Catalan",
]


def extract_profile_info(text, config=None):
    """Détecte nom, email, téléphone, compétences, langues, années d'exp.

    Stratégie :
    1. Essaie d'abord l'IA (Ollama / OpenAI / Claude si configuré) en demandant du JSON
    2. Complète les infos manquantes via regex / heuristiques
    """
    info = {}
    if not text:
        return info

    # 1) Tentative IA (plus fiable sur le nom/téléphone que les regex)
    if config:
        try:
            ai_info = _extract_via_ai(text, config)
            if ai_info:
                info.update({k: v for k, v in ai_info.items() if v})
        except Exception:
            pass

    # 2) Regex / heuristiques en complément (toujours faites — elles peuvent confirmer)
    low = text.lower()

    # Email
    if "email" not in info:
        m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        if m:
            info["email"] = m.group(0).strip(" .,;")

    # Téléphone — regex très tolérante
    if "telephone" not in info:
        phone = _extract_phone(text)
        if phone:
            info["telephone"] = phone

    # LinkedIn
    if "linkedin" not in info:
        li = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_\-/.%]+", text)
        if li:
            url = li.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            info["linkedin"] = url

    # Nom / prénom — heuristique renforcée
    if "prenom" not in info or "nom" not in info:
        name = _extract_name(text)
        if name:
            info.setdefault("prenom", name[0])
            info.setdefault("nom", name[1])

    # Compétences : catalogue + extraction par section
    if "competences" not in info:
        found = []
        for sk in _COMPETENCES_CATALOG:
            if re.search(r"\b" + re.escape(sk.lower()) + r"\b", low) and sk not in found:
                # Normalisation des doublons (Davinci vs DaVinci Resolve)
                _norm = sk
                if sk.lower() == "davinci":
                    _norm = "DaVinci Resolve"
                elif sk.lower() == "premiere":
                    _norm = "Premiere Pro"
                elif sk.lower() == "final cut":
                    _norm = "Final Cut Pro"
                if _norm not in found:
                    found.append(_norm)

        # Bonus : ce qui est listé directement sous une section "COMPÉTENCES",
        # "LOGICIELS", "OUTILS", "TECHNOLOGIES", "SKILLS"…
        section_items = _extract_section_items(
            text, ("compétences", "competences", "logiciels", "outils",
                   "technologies", "skills", "stack", "tools", "capacités",
                   "capacites", "savoir-faire")
        )
        for item in section_items:
            if item and item not in found:
                found.append(item)

        if found:
            info["competences"] = found[:20]

    # Langues — word boundary pour éviter "Arabesques" → "Arabe"
    if "langues" not in info:
        langues = []
        for lg in _LANGUES_CATALOG:
            if re.search(r"\b" + re.escape(lg.lower()) + r"\b", low):
                norm = (lg.replace("Francais", "Français")
                          .replace("Coreen", "Coréen")
                          .replace("Neerlandais", "Néerlandais")
                          .replace("Suedois", "Suédois")
                          .replace("Norvegien", "Norvégien")
                          .replace("Tcheque", "Tchèque")
                          .replace("Hebreu", "Hébreu")
                          .replace("Thai", "Thaï"))
                if norm not in langues:
                    langues.append(norm)
        # Bonus : section "LANGUES"
        for item in _extract_section_items(text, ("langues", "languages")):
            if item and item not in langues and len(item) < 25:
                langues.append(item)
        if langues:
            info["langues"] = langues

    # Années d'expérience
    if "annees" not in info:
        exp_match = re.search(r"(\d{1,2})\s*(?:\+\s*)?ans? d['']?exp", low)
        if exp_match:
            info["annees"] = int(exp_match.group(1))
        else:
            years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
            if years:
                info["annees"] = max(0, min(50, datetime.now().year - min(years)))

    return info


def _extract_section_items(text, section_names):
    """Extrait les éléments listés sous une ou plusieurs sections du CV.

    Repère un en-tête de section (ex: "COMPÉTENCES", "LOGICIELS"…) et collecte
    les lignes qui suivent jusqu'au prochain en-tête (autre section en
    majuscules ou ligne de digits/dates).
    """
    items = []
    lines = text.splitlines()
    section_re = re.compile(
        r"^\s*(?:" + "|".join(re.escape(n) for n in section_names) + r")\s*:?\s*$",
        re.IGNORECASE
    )
    # Regex : un en-tête de section générique = ligne courte tout en MAJUSCULES
    other_header_re = re.compile(
        rf"^\s*[{_LATIN}\s/&\-]{{3,30}}\s*:?\s*$"
    )

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if section_re.match(line):
            # Collecte les lignes suivantes, jusqu'à un autre en-tête
            j = i + 1
            collected = []
            while j < len(lines):
                cand = lines[j].strip()
                if not cand:
                    j += 1
                    if len(collected) > 0 and len(collected) >= 12:
                        break
                    if j < len(lines) and lines[j].strip() == "":
                        break
                    continue
                # Stop si on retombe sur un autre en-tête (majuscules courtes)
                if (cand == cand.upper() and len(cand.split()) <= 3
                        and 3 <= len(cand) <= 30
                        and not re.search(r"\d", cand)
                        and other_header_re.match(cand)
                        and not section_re.match(cand)):
                    break
                # Skip lignes qui ressemblent à des dates/lieux
                if re.match(r"^[\d\-/.\s]+$", cand):
                    j += 1
                    continue
                # Nettoyage : enlève bullets, tirets de début
                cand = re.sub(r"^[\-•·*▪–—]\s*", "", cand)
                if len(cand) > 60:
                    j += 1
                    continue
                collected.append(cand.strip())
                j += 1
                if len(collected) >= 20:
                    break
            # Mots qui ne sont jamais une vraie compétence (en-tête, glossaire…)
            _BAD = {
                "logiciels", "outils", "competences", "compétences", "skills",
                "langues", "languages", "intérêts", "interets", "intérets",
                "capacités", "capacites", "stack", "tools", "savoir-faire",
                "loisirs", "hobbies", "centres d'intérêt", "centres d intérêt",
            }
            for item in collected:
                low_item = item.lower()
                # Filtres de qualité
                if len(item) < 3:
                    continue
                if low_item in _BAD:
                    continue
                # Pas de mot tout seul d'une seule lettre
                if len(item.split()) == 1 and len(item) <= 2:
                    continue
                # Title-case intelligent (gère les apostrophes)
                if item.isupper() and len(item) <= 6:
                    cleaned = item  # sigle (HTML, SQL, AWS…)
                elif item.isupper():
                    # Phrase tout en majuscules → sentence case
                    cleaned = item[0].upper() + item[1:].lower()
                else:
                    cleaned = item  # déjà bien casé
                items.append(cleaned)
            i = j
        else:
            i += 1
    # Dédup en gardant l'ordre
    seen = set()
    out = []
    for x in items:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _extract_phone(text):
    """Détection téléphone : formats FR (+33, 0X, espaces/points/tirets) et internationaux."""
    patterns = [
        r"\+33\s?(?:\(?0\)?\s?)?[1-9](?:[\s.-]?\d{2}){4}",
        r"0[1-9](?:[\s.-]?\d{2}){4}",
        r"\+\d{2,3}[\s.-]?\d[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}",
        r"\(?\d{2,4}\)?[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(0).strip()
            if sum(c.isdigit() for c in raw) >= 9:
                return raw
    return None


# Mots qui ne peuvent PAS être un nom de personne
_NAME_STOPWORDS = {
    "curriculum", "vitae", "cv", "resume", "résumé",
    "email", "mail", "téléphone", "telephone", "tel",
    "adresse", "address", "contact", "profil", "profile",
    "né", "née", "years", "ans", "old", "expérience", "experience",
    "paris", "lyon", "marseille", "france", "french", "montréal", "montreal",
    "linkedin", "github", "portfolio",
    # Titres de section
    "experiences", "expériences", "formations", "formation",
    "compétences", "competences", "logiciels", "softwares",
    "langues", "languages", "interets", "intérêts",
    "capacites", "capacités", "projets", "references", "références",
    "diplômes", "diplomes", "études", "etudes",
    "événement", "evenement", "évènement", "festival",
    # Métiers audiovisuels / créatifs
    "photographe", "videaste", "vidéaste", "monteur", "monteuse",
    "cadreur", "cadreuse", "technicien", "technicienne",
    "realisateur", "réalisateur", "realisatrice", "réalisatrice",
    "chef", "directeur", "directrice",
    # Métiers tech
    "developpeur", "développeur", "developer", "engineer",
    "ingenieur", "ingénieur", "designer", "graphiste", "architecte",
    "consultant", "consultante",
    # Métiers business
    "manager", "responsable", "assistant", "assistante",
    "analyst", "analyste", "comptable", "commercial", "commerciale",
}

# Unicode range for Latin letters including accents
_LATIN = "A-Za-zÀ-ÖØ-öø-ÿ"


def _extract_name(text):
    """Extrait (prenom, nom) par heuristiques multi-stratégies."""
    # Strat 1 : ligne en CAPITALE dans les 8 premières lignes
    for line in text.splitlines()[:8]:
        line = line.strip()
        if not line or "@" in line or re.search(r"\d", line):
            continue
        if any(sw in line.lower() for sw in _NAME_STOPWORDS):
            continue
        # Ligne entièrement en majuscules (au moins 2 mots de 2+ lettres)
        if re.fullmatch(rf"[{_LATIN}\s\-']+", line) and line == line.upper():
            parts = [p for p in re.split(r"\s+", line) if len(p) >= 2]
            if 2 <= len(parts) <= 4:
                return (parts[0].title(), " ".join(parts[1:]).title())

    # Strat 2 : 2–4 mots commençant par majuscule, sans digit ni @
    for line in text.splitlines()[:10]:
        line = line.strip()
        if not line or "@" in line or re.search(r"\d", line):
            continue
        low = line.lower()
        if any(sw in low for sw in _NAME_STOPWORDS):
            continue
        parts = [p for p in re.split(r"\s+", line) if p]
        if 2 <= len(parts) <= 4:
            if all(len(p) >= 2 and p[0].isupper() for p in parts):
                return (parts[0].title(), " ".join(parts[1:]).title())

    # Strat 3 : ligne avec UN SEUL mot en Title case, juste après un titre métier
    # en majuscules (ou label de section). Ex: "PHOTOGRAPHE VIDÉASTE\nChiara"
    # Placée AVANT le fallback regex pour qu'elle gagne sur les titres de sections.
    lines = text.splitlines()[:15]
    for i in range(1, len(lines)):
        prev = lines[i - 1].strip()
        cur = lines[i].strip()
        if not cur or "@" in cur or re.search(r"\d", cur):
            continue
        prev_words = [w for w in re.split(r"[\s\-]+", prev) if w]
        if not prev_words:
            continue
        prev_is_title = (
            all(w.isupper() for w in prev_words if len(w) >= 2)
            or any(w.lower() in _NAME_STOPWORDS for w in prev_words)
        )
        if not prev_is_title:
            continue
        if re.fullmatch(rf"[{_LATIN}]{{3,15}}", cur) and cur[0].isupper():
            if cur.lower() not in _NAME_STOPWORDS and cur != cur.upper():
                nom = ""
                for j in range(i + 1, min(i + 4, len(lines))):
                    c = lines[j].strip()
                    if (c and re.fullmatch(rf"[{_LATIN}\s\-']+", c)
                            and c == c.upper() and 1 <= len(c.split()) <= 3
                            and c.lower() not in _NAME_STOPWORDS):
                        nom = c.title()
                        break
                return (cur.title(), nom)

    # Strat 4 : fallback regex "Prénom NOM" n'importe où dans les 30 premières lignes
    for line in text.splitlines()[:30]:
        m = re.search(
            rf"\b([{_LATIN}][{_LATIN}\-']{{1,20}})\s+([A-ZÀ-Ö]{{2,}}(?:\s[A-ZÀ-Ö]{{2,}})?)\b",
            line,
        )
        if m:
            prenom, nom = m.group(1), m.group(2)
            if prenom.lower() not in _NAME_STOPWORDS:
                return (prenom.title(), nom.title())

    return None


def _extract_via_ai(text, config):
    """Demande à l'IA d'extraire les infos en JSON. Retourne un dict ou None."""
    engine = (config.get("api", {}) or {}).get("ai_engine", "ollama").lower()
    excerpt = text[:4000]
    prompt = f"""Tu es un parseur de CV. Extrait les informations exactement comme elles apparaissent dans le CV ci-dessous.
Réponds UNIQUEMENT avec un objet JSON valide (aucun commentaire, aucun markdown, aucune balise).

Schéma attendu :
{{
  "prenom": "string",
  "nom": "string",
  "email": "string",
  "telephone": "string (format brut visible dans le CV)",
  "linkedin": "string (URL complète)",
  "annees": 0,
  "competences": ["string", "..."],
  "langues": ["string", "..."]
}}

Règles strictes :
- "prenom" et "nom" : uniquement le vrai nom de la personne (tout en haut du CV, en gros). Jamais un titre de poste (ex: "Photographe", "Développeur"), un nom d'entreprise, ni un nom d'événement.
- Si l'info est absente → "" (chaîne vide) ou [] (liste vide). Jamais null.
- "competences" : 5 à 12 compétences techniques réelles tirées du CV (logiciels, langages, méthodologies).
- "annees" : nombre entier d'années d'expérience estimé à partir des dates du CV.

CV :
\"\"\"
{excerpt}
\"\"\""""
    raw = None
    try:
        if engine == "ollama":
            import ollama
            model = config.get("api", {}).get("ollama_model") or "gemma2:2b"
            # format="json" force Ollama à produire du JSON structuré
            # options.temperature=0.1 pour consistance
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.1},
            )
            raw = resp["message"]["content"]
        elif engine == "openai":
            key = config.get("api", {}).get("openai_key") or os.environ.get("OPENAI_API_KEY")
            if not key:
                return None
            from openai import OpenAI
            r = OpenAI(api_key=key).chat.completions.create(
                model="gpt-4o-mini", max_tokens=800,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            raw = r.choices[0].message.content
        elif engine == "claude":
            key = config.get("api", {}).get("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                return None
            from anthropic import Anthropic
            r = Anthropic(api_key=key).messages.create(
                model="claude-3-5-haiku-latest", max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = r.content[0].text
    except Exception:
        return None

    if not raw:
        return None
    # Extraire le bloc JSON (l'IA peut l'entourer de texte)
    import json
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    # Nettoyage
    out = {}
    for k in ("prenom", "nom", "email", "telephone", "linkedin"):
        v = data.get(k, "")
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    if isinstance(data.get("annees"), (int, float)) and data["annees"] > 0:
        out["annees"] = int(data["annees"])
    for k in ("competences", "langues"):
        v = data.get(k, [])
        if isinstance(v, list):
            clean = [str(x).strip() for x in v if str(x).strip()]
            if clean:
                out[k] = clean
    return out


# ─────────────────────────────────────────────────────────
# Score ATS
# ─────────────────────────────────────────────────────────
def ats_score(path, text=None):
    """Analyse un CV et retourne (score/100, verdict, liste de points).

    Un CV ATS-friendly doit :
    - Être parsable en texte (pas de CV-image uniquement)
    - Contenir les sections classiques (Expérience, Formation, Compétences)
    - Contenir email + téléphone
    - Faire 300+ mots (sinon trop maigre pour ATS)
    - Éviter les colonnes / tableaux complexes (difficilement détectable sans rendu)
    """
    if text is None:
        text = extract_text(path)

    issues = []
    passed = []
    score = 0
    max_score = 100

    # 1) Extraction texte (30 pts)
    if not text or len(text) < 100:
        issues.append(("❌", "Le CV semble être une image — les ATS ne peuvent PAS le lire.",
                       "Exporte ton CV en PDF texte (depuis Word/Canva/Pages) et non en image/scan."))
    else:
        passed.append(("✅", f"Texte extractible ({len(text.split())} mots)", ""))
        score += 30

    low = text.lower() if text else ""

    # 2) Contact (15 pts)
    has_email = bool(re.search(r"@[a-z0-9.-]+\.[a-z]+", low))
    has_phone = bool(re.search(r"\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}", text or ""))
    if has_email and has_phone:
        passed.append(("✅", "Email + téléphone présents", ""))
        score += 15
    elif has_email or has_phone:
        issues.append(("⚠️", "Un seul moyen de contact détecté",
                       "Ajoute email ET téléphone en haut du CV."))
        score += 8
    else:
        issues.append(("❌", "Aucun email ni téléphone détecté",
                       "Les recruteurs doivent pouvoir te joindre : ajoute email + téléphone."))

    # 3) Sections classiques (25 pts)
    sections_required = {
        "Expérience": ["expérience", "experience", "parcours"],
        "Formation":  ["formation", "diplôme", "études", "education"],
        "Compétences": ["compétences", "skills", "savoir-faire"],
    }
    found_sections = []
    for label, variants in sections_required.items():
        if any(v in low for v in variants):
            found_sections.append(label)
    if len(found_sections) >= 3:
        passed.append(("✅", "Sections classiques présentes (Expérience/Formation/Compétences)", ""))
        score += 25
    elif len(found_sections) == 2:
        issues.append(("⚠️", f"Seulement 2 sections détectées ({', '.join(found_sections)})",
                       "Ajoute des titres de section clairs : Expérience, Formation, Compétences."))
        score += 15
    else:
        issues.append(("❌", "Sections classiques manquantes",
                       "Structure ton CV avec des titres clairs : Expérience, Formation, Compétences."))

    # 4) Longueur raisonnable (15 pts)
    wc = len(text.split()) if text else 0
    if 300 <= wc <= 1200:
        passed.append(("✅", f"Longueur OK ({wc} mots)", ""))
        score += 15
    elif wc < 300 and wc >= 100:
        issues.append(("⚠️", f"CV un peu court ({wc} mots)",
                       "Développe tes expériences avec des résultats chiffrés."))
        score += 8
    elif wc > 1200:
        issues.append(("⚠️", f"CV un peu long ({wc} mots)",
                       "Un CV ATS devrait idéalement tenir sur 1-2 pages (600-900 mots)."))
        score += 10

    # 5) Mots-clés et verbes d'action (15 pts)
    action_verbs = ["développé", "mis en place", "géré", "conçu", "optimisé",
                    "coordonné", "piloté", "réalisé", "animé", "encadré", "analysé"]
    verb_hits = sum(1 for v in action_verbs if v in low)
    if verb_hits >= 4:
        passed.append(("✅", f"Utilise des verbes d'action forts ({verb_hits} détectés)", ""))
        score += 15
    elif verb_hits >= 2:
        score += 8
        issues.append(("⚠️", "Peu de verbes d'action",
                       "Utilise plus de verbes d'action (développé, piloté, optimisé...)."))
    else:
        issues.append(("❌", "Très peu de verbes d'action détectés",
                       "Les ATS et recruteurs cherchent des verbes d'action : développé, optimisé, piloté..."))

    # Verdict global
    if score >= 80:
        verdict = f"🎉 Excellent — {score}/100. Ton CV est ATS-friendly !"
    elif score >= 60:
        verdict = f"👍 Correct — {score}/100. Quelques améliorations possibles."
    elif score >= 40:
        verdict = f"⚠️  Moyen — {score}/100. Plusieurs points à corriger pour passer les ATS."
    else:
        verdict = f"❌ Faible — {score}/100. Ton CV risque d'être rejeté automatiquement."

    explanation = (
        "Un Applicant Tracking System (ATS) est un logiciel que 75% des entreprises utilisent "
        "pour filtrer les CV AVANT qu'un humain ne les lise. Si ton CV n'est pas lisible "
        "par la machine, il est rejeté automatiquement — même si tu es le candidat parfait."
    )

    return {
        "score": score,
        "verdict": verdict,
        "explanation": explanation,
        "passed": passed,
        "issues": issues,
    }
