"""
Gestion du profil utilisateur
"""
import json
import os
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def _default_config_path():
    try:
        import app_paths
        return str(app_paths.config_path())
    except Exception:
        return "config.json"


class ProfileManager:
    def __init__(self, path=None):
        self.path = path or _default_config_path()
        self.config = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                console.print(f"[yellow]Config illisible ({e}) — défaut utilisé.[/yellow]")
                return self._default()
        return self._default()

    def _default(self):
        return {
            "profil": {
                "prenom": "", "nom": "", "email": "", "telephone": "",
                "ville": "", "linkedin": "", "poste_recherche": "",
                "experiences": [], "competences": [], "langues": []
            },
            "recherche": {
                "mots_cles": [], "localisation": "", "rayon_km": 20,
                "type_contrat": ["CDI"], "teletravail": False
            },
            "relance": {"active": True, "delai_jours": 10}
        }

    def setup_interactive(self):
        console.print("\n[bold cyan]👤 Configuration du profil[/bold cyan]\n")
        p = self.config["profil"]
        p["prenom"] = Prompt.ask("Prénom", default=p.get("prenom", ""))
        p["nom"] = Prompt.ask("Nom", default=p.get("nom", ""))
        p["email"] = Prompt.ask("Email", default=p.get("email", ""))
        p["telephone"] = Prompt.ask("Téléphone", default=p.get("telephone", ""))
        p["ville"] = Prompt.ask("Ville", default=p.get("ville", ""))
        p["linkedin"] = Prompt.ask("LinkedIn (URL)", default=p.get("linkedin", ""))
        p["poste_recherche"] = Prompt.ask("Poste recherché", default=p.get("poste_recherche", ""))

        comp = Prompt.ask("Compétences (séparées par virgules)",
                          default=",".join(p.get("competences", [])))
        p["competences"] = [c.strip() for c in comp.split(",") if c.strip()]

        exp = Prompt.ask("Expériences clés (séparées par virgules)",
                         default=",".join(p.get("experiences", [])))
        p["experiences"] = [e.strip() for e in exp.split(",") if e.strip()]

        console.print("\n[bold cyan]🔍 Critères de recherche[/bold cyan]\n")
        r = self.config["recherche"]
        mc = Prompt.ask("Mots-clés (virgules)", default=",".join(r.get("mots_cles", [])))
        r["mots_cles"] = [m.strip() for m in mc.split(",") if m.strip()]
        r["localisation"] = Prompt.ask("Localisation", default=r.get("localisation", ""))
        r["rayon_km"] = int(Prompt.ask("Rayon (km)", default=str(r.get("rayon_km", 20))))

        self._save()
        console.print("[green]✅ Profil enregistré[/green]")

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
