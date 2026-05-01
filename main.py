"""
Candidature Bot - Point d'entrée
"""
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
import os

from profile_manager import ProfileManager
from scraper import OffreScraper
from ai_engine import AIEngine
from mail_sender import MailSender
from tracker import Tracker

console = Console()


def banner():
    console.print(Panel.fit(
        "[bold cyan]🎯 CANDIDATURE BOT[/bold cyan]\n"
        "[dim]Automatise tes candidatures spontanées & offres[/dim]",
        border_style="cyan"
    ))


def menu():
    console.print("\n[bold]📋 MENU PRINCIPAL[/bold]")
    console.print("  [1] 👤 Configurer mon profil")
    console.print("  [2] 🔍 Rechercher des offres (auto)")
    console.print("  [3] ✋ Ajouter une offre manuellement (URL)")
    console.print("  [4] 📬 Traiter les offres & envoyer mails")
    console.print("  [5] 📊 Voir mes candidatures envoyées")
    console.print("  [6] 🔔 Gérer les relances")
    console.print("  [7] ⚙️  Paramètres IA")
    console.print("  [0] 🚪 Quitter\n")
    return Prompt.ask("Ton choix", choices=["0","1","2","3","4","5","6","7"])


def main():
    banner()
    profile = ProfileManager()
    tracker = Tracker()

    while True:
        choice = menu()

        if choice == "0":
            console.print("[green]À bientôt ! 👋[/green]")
            break
        elif choice == "1":
            profile.setup_interactive()
        elif choice == "2":
            scraper = OffreScraper(profile.config)
            scraper.search_and_save()
        elif choice == "3":
            scraper = OffreScraper(profile.config)
            url = Prompt.ask("URL de l'offre")
            scraper.add_manual(url)
        elif choice == "4":
            process_offers(profile, tracker)
        elif choice == "5":
            tracker.show_all()
        elif choice == "6":
            tracker.check_relances(profile.config)
        elif choice == "7":
            configure_ai()


def process_offers(profile, tracker):
    """Lit les offres, génère les mails via IA, demande validation, envoie."""
    import json
    if not os.path.exists("data/offres.json"):
        console.print("[red]Aucune offre. Lance d'abord une recherche.[/red]")
        return

    with open("data/offres.json", "r") as f:
        offres = json.load(f)

    ai = AIEngine()
    sender = MailSender()

    for offre in offres:
        if tracker.already_sent(offre.get("id")):
            continue

        titre = offre.get("intitule") or offre.get("titre") or offre.get("poste", "?")
        console.print(Panel(
            f"[bold]{titre}[/bold]\n"
            f"🏢 {offre.get('entreprise', '?')}\n"
            f"📍 {offre.get('lieu', '?')}\n\n"
            f"{offre.get('description', '')[:300]}...",
            title="💼 Offre"
        ))

        action = Prompt.ask(
            "Action",
            choices=["g", "s", "q"],
            default="g"
        )
        if action == "q":
            break
        if action == "s":
            continue

        # Génération du mail
        console.print("[yellow]✍️  Génération du mail...[/yellow]")
        mail = ai.generate_email(offre, profile.config)

        console.print(Panel(mail, title="📧 Mail généré", border_style="green"))

        valid = Prompt.ask("Envoyer ? (o/n/r=regénérer)", choices=["o","n","r"])
        if valid == "r":
            mail = ai.generate_email(offre, profile.config)
            console.print(Panel(mail, title="📧 Nouveau", border_style="green"))
            valid = Prompt.ask("Envoyer ? (o/n)", choices=["o","n"])

        if valid == "o":
            email_dest = offre.get("email") or Prompt.ask("Email destinataire")
            if sender.send(email_dest, f"Candidature - {titre}", mail):
                tracker.log(offre, email_dest)
                console.print("[green]✅ Envoyé ![/green]")


def configure_ai():
    console.print("\n[bold]⚙️  Moteur IA actuel :[/bold]", os.getenv("AI_ENGINE", "ollama"))
    console.print("  [1] 🏠 Ollama (local, gratuit)")
    console.print("  [2] 🤖 OpenAI")
    console.print("  [3] 🧠 Claude")
    console.print("  [4] 📝 Template simple")
    c = Prompt.ask("Choix", choices=["1","2","3","4"])
    mapping = {"1":"ollama", "2":"openai", "3":"claude", "4":"template"}
    _update_env("AI_ENGINE", mapping[c])

    if c == "2":
        key = Prompt.ask("Clé OpenAI (sk-...)")
        _update_env("OPENAI_API_KEY", key)
    elif c == "3":
        key = Prompt.ask("Clé Claude (sk-ant-...)")
        _update_env("ANTHROPIC_API_KEY", key)

    console.print("[green]✅ Configuration sauvegardée[/green]")


def _update_env(key, value):
    path = ".env"
    lines = []
    found = False
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
    if not found:
        lines.append(f"{key}={value}\n")
    with open(path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    main()
