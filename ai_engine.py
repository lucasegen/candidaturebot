"""
Moteur IA multi-backend : Ollama / OpenAI / Claude / Template
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class AIEngine:
    def __init__(self, config=None):
        if config:
            self.engine = config.get("api", {}).get(
                "ai_engine", os.getenv("AI_ENGINE", "ollama")
            ).lower()
        else:
            self.engine = os.getenv("AI_ENGINE", "ollama").lower()
        self.config = config or {}

    def _get_key(self, key_name, env_name):
        return self.config.get("api", {}).get(key_name, "") or os.getenv(env_name, "")

    def complete(self, prompt):
        """Renvoie le texte brut produit par le moteur IA configuré.
        Lève une exception si l'appel échoue — l'appelant choisit le fallback."""
        if self.engine == "ollama":
            return self._ollama(prompt)
        elif self.engine == "openai":
            return self._openai(prompt)
        elif self.engine == "claude":
            return self._claude(prompt)
        raise RuntimeError(f"Moteur IA inconnu : {self.engine}")

    def generate_email(self, offre, config=None):
        cfg = config or self.config
        prompt = self._build_prompt_email(offre, cfg)
        return self._run(prompt, offre, cfg, mode="email")

    def generate_cover_letter(self, offre, config=None):
        cfg = config or self.config
        prompt = self._build_prompt_lettre(offre, cfg)
        return self._run(prompt, offre, cfg, mode="lettre")

    def _run(self, prompt, offre, cfg, mode="email"):
        try:
            if self.engine == "ollama":
                return self._ollama(prompt)
            elif self.engine == "openai":
                return self._openai(prompt)
            elif self.engine == "claude":
                return self._claude(prompt)
        except Exception as e:
            # Log technique complet (stdout) mais affichage utilisateur
            # filtré pour éviter de fuiter une clé API dans un message d'erreur.
            print(f"[ai_engine] {self.engine} a échoué : {type(e).__name__}: {e}")
            err_short = type(e).__name__
            fallback = (self._template_lettre(offre, cfg) if mode == "lettre"
                        else self._template_email(offre, cfg))
            return (f"[⚠️ IA indisponible ({err_short}) — "
                    f"utilisation du template]\n\n{fallback}")

        # Aucun moteur reconnu (ex: engine="template") → template direct.
        if mode == "lettre":
            return self._template_lettre(offre, cfg)
        return self._template_email(offre, cfg)

    def _cv_excerpt(self, config, limit=2500):
        txt = config.get("documents", {}).get("cv_text", "") or ""
        return txt[:limit].strip()

    def _lettre_excerpt(self, config, limit=1500):
        docs = config.get("documents", {}) or {}
        txt = docs.get("lettre_text", "") or config.get("profil", {}).get("lettre_type", "")
        return (txt or "")[:limit].strip()

    _ANTI_IA_RULES = """RÈGLES D'ÉCRITURE (TRÈS IMPORTANT — objectif : ne pas sonner IA) :
- Écris comme un vrai humain qui postule, pas comme un assistant.
- Varie la longueur des phrases : courtes + longues mélangées. Évite un rythme trop régulier.
- BANNIS absolument ces tics d'IA : « D'une part / D'autre part », « En outre », « De surcroît »,
  « Il va sans dire », « Je suis convaincu(e) que mon profil correspond parfaitement »,
  « fort(e) de mes compétences », « une réelle valeur ajoutée », « contribuer efficacement »,
  « au sein de votre prestigieuse entreprise », « à l'aune de », « dans le cadre de », « en ma qualité de ».
- N'utilise PAS d'émojis, PAS de listes à puces, PAS de titres markdown.
- Pas de phrases parfaitement parallèles ni de tournures redondantes.
- Autorise-toi UN détail concret ou une anecdote courte (résultat chiffré, projet précis) si le CV le permet.
- Ton humain : naturel, direct, un peu imparfait plutôt que lisse et creux.
- Ne répète pas mot pour mot l'intitulé du poste ou le nom de l'entreprise plus de 2 fois."""

    def _build_prompt_email(self, offre, config):
        profil = config.get("profil", {})
        exp = config.get("experience", {})
        cv_txt = self._cv_excerpt(config)
        lettre_ref = self._lettre_excerpt(config)

        cv_block = f"\nEXTRAIT DE CV (source de vérité) :\n{cv_txt}\n" if cv_txt else ""
        lettre_block = f"\nLETTRE DE RÉFÉRENCE (ton / style) :\n{lettre_ref}\n" if lettre_ref else ""

        return f"""Tu es un expert en recrutement. Rédige un MAIL D'ACCOMPAGNEMENT TRÈS COURT (90 mots max),
professionnel et personnalisé en français. Ce mail accompagne une lettre de motivation ET un CV joints
en pièces jointes. Il ne doit PAS reprendre le contenu de la lettre : c'est juste un mot d'introduction.

PROFIL DU CANDIDAT :
- Nom : {profil.get('prenom')} {profil.get('nom')}
- Poste recherché : {profil.get('poste_recherche')}
- Compétences : {', '.join(exp.get('competences', []))}
- Années d'expérience : {exp.get('annees', '?')}
{cv_block}{lettre_block}
OFFRE :
- Poste : {offre.get('poste', offre.get('titre', offre.get('intitule', '?')))}
- Entreprise : {offre.get('entreprise', '?')}
- Description : {offre.get('description', '')[:400]}

STRUCTURE (TRÈS sobre, très court) :
- Commence par "Bonjour,"
- 2 paragraphes max : une phrase d'accroche + une phrase qui renvoie vers la lettre et le CV en pièces jointes + call-to-action court
- Termine par "Cordialement, {profil.get('prenom')} {profil.get('nom')}"
- Ne mets PAS "Objet:" ni de signature longue
- MENTIONNE explicitement que la lettre de motivation et le CV sont en pièces jointes

{self._ANTI_IA_RULES}

Écris UNIQUEMENT le mail, rien d'autre."""

    def _build_prompt_lettre(self, offre, config):
        profil = config.get("profil", {})
        exp = config.get("experience", {})
        cv_txt = self._cv_excerpt(config)
        lettre_ref = self._lettre_excerpt(config)

        cv_block = f"\nEXTRAIT DE CV (source de vérité) :\n{cv_txt}\n" if cv_txt else ""
        lettre_block = f"\nLETTRE DE RÉFÉRENCE (réutilise ce ton/style) :\n{lettre_ref}\n" if lettre_ref else ""

        return f"""Tu es un expert RH. Rédige une lettre de motivation professionnelle en français (300 mots max).

PROFIL :
- Nom : {profil.get('prenom')} {profil.get('nom')}
- Poste recherché : {profil.get('poste_recherche')}
- Compétences : {', '.join(exp.get('competences', []))}
- Années d'expérience : {exp.get('annees', '?')}
- Langues : {', '.join(exp.get('langues', []))}
{cv_block}{lettre_block}
OFFRE :
- Poste : {offre.get('poste', offre.get('titre', offre.get('intitule', '?')))}
- Entreprise : {offre.get('entreprise', '?')}
- Description : {offre.get('description', '')[:600]}

STRUCTURE :
1. Accroche personnalisée (pourquoi cette entreprise — éviter les clichés RH)
2. Mes compétences clés en lien avec le poste (pioche 1-2 éléments précis du CV)
3. Ma motivation
4. Call-to-action sobre pour un entretien

Commence par "Madame, Monsieur," et termine par "Cordialement, {profil.get('prenom')} {profil.get('nom')}"

{self._ANTI_IA_RULES}

Écris UNIQUEMENT la lettre, rien d'autre."""

    def _ollama(self, prompt):
        import ollama
        model = self.config.get("api", {}).get("ollama_model") or os.getenv("OLLAMA_MODEL", "gemma2:2b")
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response["message"]["content"].strip()

    def _openai(self, prompt):
        from openai import OpenAI
        key = self._get_key("openai_key", "OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Clé OpenAI manquante")
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600
        )
        return resp.choices[0].message.content.strip()

    def _claude(self, prompt):
        from anthropic import Anthropic
        key = self._get_key("anthropic_key", "ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Clé Anthropic manquante")
        client = Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()

    def _template_email(self, offre, config):
        p = config.get("profil", {})
        exp = config.get("experience", {})
        poste = offre.get('poste', offre.get('titre', offre.get('intitule', '?')))
        return f"""Bonjour,

Actuellement à la recherche d'un poste de {p.get('poste_recherche', '—')}, votre offre pour le poste de {poste} chez {offre.get('entreprise', '?')} a retenu toute mon attention.

Fort(e) de mes compétences en {', '.join(exp.get('competences', [])[:3]) or '—'}, je suis convaincu(e) de pouvoir apporter une réelle valeur ajoutée à votre équipe.

Je reste disponible pour échanger lors d'un entretien à votre convenance.

Cordialement,
{p.get('prenom', '')} {p.get('nom', '')}
{p.get('telephone', '')} | {p.get('email', '')}"""

    def _template_lettre(self, offre, config):
        p = config.get("profil", {})
        exp = config.get("experience", {})
        poste = offre.get('poste', offre.get('titre', offre.get('intitule', '?')))
        return f"""Madame, Monsieur,

Passionné(e) par {p.get('poste_recherche', '—')}, c'est avec un vif intérêt que j'ai découvert votre offre pour le poste de {poste} au sein de {offre.get('entreprise', '?')}.

Au cours de mes {exp.get('annees', '?')} années d'expérience, j'ai développé de solides compétences en {', '.join(exp.get('competences', [])[:4]) or '—'}. Ces expertises me permettraient de contribuer efficacement à vos projets.

Convaincu(e) que mon profil correspond aux attentes de votre équipe, je serais ravi(e) de vous présenter ma candidature lors d'un entretien.

Dans l'attente de votre retour, je vous adresse mes sincères salutations.

Cordialement,
{p.get('prenom', '')} {p.get('nom', '')}
{p.get('telephone', '')} | {p.get('email', '')}"""


def generate_cover_letter(config, offre):
    """Fonction utilitaire appelée depuis gui.py"""
    engine = AIEngine(config=config)
    return engine.generate_cover_letter(offre, config)


def generate_email(config, offre):
    """Fonction utilitaire appelée depuis gui.py"""
    engine = AIEngine(config=config)
    return engine.generate_email(offre, config)
