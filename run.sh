#!/usr/bin/env bash
# Lanceur Candidature Bot
set -e
cd "$(dirname "$0")"

# Crée le venv s'il n'existe pas
if [ ! -d "venv" ]; then
  echo "📦 Création du venv..."
  python3 -m venv venv
fi

# Active le venv
source venv/bin/activate

# Installe/MAJ les dépendances si requirements.txt a changé
if [ requirements.txt -nt venv/.deps_installed ] 2>/dev/null || [ ! -f venv/.deps_installed ]; then
  echo "📥 Installation des dépendances..."
  pip install -q -r requirements.txt
  touch venv/.deps_installed
fi

# Lance l'app
exec python3 gui.py
