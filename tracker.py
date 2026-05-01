"""
Suivi des candidatures & relances automatiques
"""
import json
import os
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table

console = Console()


def _default_candidatures_path():
    try:
        import app_paths
        return str(app_paths.candidatures_path())
    except Exception:
        return os.path.join("data", "candidatures.json")


class Tracker:
    def __init__(self, path=None):
        self.path = path or _default_candidatures_path()
        # S'assure que le dossier parent existe avant le _save
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"[tracker] Lecture impossible ({e}) — démarrage vide.")
                return []
        return []

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)

    def already_sent(self, offre_id):
        return any(c.get("offre_id") == offre_id for c in self.data)

    def log(self, offre, email_dest, relance=False):
        self.data.append({
            "offre_id": offre.get("id"),
            "intitule": offre.get("intitule") or offre.get("titre") or offre.get("poste", ""),
            "entreprise": offre.get("entreprise", ""),
            "email_dest": email_dest,
            "date_envoi": datetime.now().isoformat(),
            "relance_envoyee": relance,
            "statut": "envoyé"
        })
        self._save()

    def show_all(self):
        if not self.data:
            console.print("[yellow]Aucune candidature envoyée[/yellow]")
            return
        table = Table(title="📊 Mes candidatures")
        table.add_column("Date")
        table.add_column("Poste")
        table.add_column("Entreprise")
        table.add_column("Email")
        table.add_column("Relance")
        for c in self.data:
            date = (c.get("date_envoi") or "")[:10]
            table.add_row(date, c.get("intitule") or "", c.get("entreprise") or "",
                          c.get("email_dest") or "", "✅" if c.get("relance_envoyee") else "❌")
        console.print(table)

    def check_relances(self, config):
        from mail_sender import MailSender
        delai = (config.get("relance") or {}).get("delai_jours", 10)
        sender = MailSender(config=config)
        now = datetime.now()
        count = 0
        for c in self.data:
            if c.get("relance_envoyee"):
                continue
            raw_date = c.get("date_envoi")
            if not raw_date:
                continue
            try:
                date_envoi = datetime.fromisoformat(raw_date)
            except (TypeError, ValueError):
                console.print(f"[yellow]Date invalide ignorée : {raw_date}[/yellow]")
                continue
            if now - date_envoi >= timedelta(days=delai):
                profil = config.get("profil") or {}
                body = (
                    "Bonjour,\n\n"
                    f"Je me permets de revenir vers vous concernant ma candidature au "
                    f"poste de {c.get('intitule', '?')} envoyée le "
                    f"{date_envoi.strftime('%d/%m/%Y')}.\n\n"
                    "Serait-il possible d'avoir un retour sur l'avancement du processus ?\n\n"
                    "Je reste à votre disposition pour tout complément d'information.\n\n"
                    "Cordialement,\n"
                    f"{profil.get('prenom', '')} {profil.get('nom', '')}"
                )
                try:
                    sent = sender.send(c.get("email_dest", ""),
                                       f"Relance - {c.get('intitule', '?')}",
                                       body)
                except Exception as e:
                    console.print(f"[red]Échec relance : {e}[/red]")
                    continue
                if sent:
                    c["relance_envoyee"] = True
                    count += 1
        self._save()
        console.print(f"[green]✅ {count} relance(s) envoyée(s)[/green]")
