"""
Tons de lettre de motivation. Chaque ton = un set de règles ajouté au prompt
de l'IA pour orienter le style sans changer la structure de base.

Utilisé dans ai_engine.py : prompt_letter += TONES[tone]["rules"]
"""

TONES = {
    "classique": {
        "label": "Classique",
        "description": "Formel, structuré. Pour grandes entreprises, banques, secteur public.",
        "rules": """
TON : CLASSIQUE / FORMEL
- Respect strict des codes de la lettre française professionnelle.
- Phrases construites, vocabulaire soutenu mais clair.
- Aucune familiarité, aucune émotion exagérée.
- Pas de tutoiement, vouvoiement obligatoire.
- Conclusion par une formule de politesse classique.
- Évite tout anglicisme inutile."""
    },
    "dynamique": {
        "label": "Dynamique",
        "description": "Énergique, enthousiaste. Pour startups, scale-ups, agences.",
        "rules": """
TON : DYNAMIQUE / ENTHOUSIASTE
- Énergie palpable : verbes d'action, phrases plus courtes.
- Manifeste sa motivation et son envie d'impact ("j'ai hâte de", "ce qui m'enthousiasme").
- Vocabulaire moderne, peut utiliser quelques anglicismes courants (mindset, scope, drive...).
- Pas de jargon RH lourd. Préfère "rejoindre votre équipe" à "intégrer vos effectifs".
- Garde une posture pro mais conversationnelle."""
    },
    "creatif": {
        "label": "Créatif",
        "description": "Personnalité, anecdotes. Pour studios créa, médias, com.",
        "rules": """
TON : CRÉATIF / PERSONNEL
- Ose une accroche originale : observation sur la marque, anecdote courte, regard particulier.
- Phrases qui sonnent vivantes, varier les longueurs (courtes/longues).
- Le candidat doit transparaître : ses goûts, son angle, son humanité.
- Évite les formules toutes faites. Préfère une image concrète à un adjectif générique.
- Reste lisible et pro malgré la liberté de ton."""
    },
    "direct": {
        "label": "Direct",
        "description": "No-bullshit, factuel, court. Pour tech, dev, métiers craft.",
        "rules": """
TON : DIRECT / FACTUEL
- Va à l'essentiel. Pas d'introduction longue.
- Chaque phrase = une info utile (compétence concrète, résultat chiffré, projet précis).
- Pas de formules creuses ("dynamique et motivé"), montre par les faits.
- Lettre courte (max 200 mots). Préfère 3 paragraphes nets à 5 longs.
- Ton respectueux mais peer-to-peer."""
    },
}


def list_tones():
    """Retourne [(key, label, description), ...] pour l'UI."""
    return [(k, v["label"], v["description"]) for k, v in TONES.items()]


def tone_rules(key):
    """Retourne les règles à concaténer au prompt de l'IA."""
    return TONES.get(key, TONES["classique"])["rules"]


def default_tone():
    return "classique"
