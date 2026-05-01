# Candidature Bot

Application desktop (macOS / Linux / Windows) qui automatise la recherche
d'offres d'emploi et la rédaction des candidatures via IA.

## ✨ Fonctionnalités

- 🔍 Recherche multi-sources : LinkedIn, France Travail, HelloWork, Adzuna, APEC, WTTJ
- 🤖 Génération IA des lettres et mails (Ollama local / OpenAI / Claude)
- 📋 Suivi des candidatures avec statuts, filtres, multi-sélection, pagination
- 📧 Envoi via Gmail SMTP (mot de passe d'application requis)
- 🔁 Routine automatique de recherche en arrière-plan
- 🔄 Mises à jour automatiques (cliquer un bouton, l'app se met à jour seule)
- 🪄 Installation Ollama en un clic

## 📥 Installation

### Utilisateur final (macOS)

Télécharge la dernière release sur [Releases](https://github.com/lucasegen/candidaturebot/releases) :

```bash
# Télécharge CandidatureBot.app, place-le dans /Applications, double-clique.
```

Au premier lancement, **clic-droit → Ouvrir** (Gatekeeper).

### Développeur

```bash
git clone https://github.com/lucasegen/candidaturebot.git
cd candidaturebot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 gui.py
```

## 🛠 Build

```bash
./venv/bin/pip install pyinstaller
./venv/bin/pyinstaller --noconfirm CandidatureBot.spec
# → dist/CandidatureBot.app
```

## 🔄 Publier une mise à jour

1. Bump `APP_VERSION` dans `gui.py`
2. `pyinstaller --noconfirm CandidatureBot.spec`
3. `cd dist && zip -qry CandidatureBot-X.Y.Z.zip CandidatureBot.app`
4. Crée une release GitHub avec tag `vX.Y.Z` et upload le ZIP en asset
5. Édite `version.json` à la racine du repo (version + URL du ZIP) et push

Toutes les apps connectées détectent automatiquement la mise à jour.

## 📁 Structure

```
gui.py                  Application principale (CustomTkinter)
scraper.py              Sources d'offres d'emploi
ai_engine.py            Moteur IA multi-backend
mail_sender.py          Envoi Gmail SMTP
pdf_generator.py        Génération PDF lettres
cv_parser.py            Extraction texte/profil depuis CV
ollama_installer.py     Install one-click Ollama
tracker.py              Suivi candidatures (CLI)
profile_manager.py      Gestion profil (CLI)
main.py                 Point d'entrée CLI (rich)
app_paths.py            Chemins user data cross-platform
CandidatureBot.spec     Config PyInstaller
config.template.json    Config par défaut bundlée
version.json            Manifest de mise à jour
```

## 📝 Configuration utilisateur

L'app stocke ses données dans :
- macOS  : `~/Library/Application Support/CandidatureBot/`
- Linux  : `~/.config/CandidatureBot/`
- Windows: `%APPDATA%/CandidatureBot/`

Aucune donnée perso n'est commit dans ce repo (`.gitignore` strict).
