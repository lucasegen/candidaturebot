import customtkinter as ctk
from tkinter import messagebox, filedialog, simpledialog
import tkinter as tk
import threading
import json
import os
import re
import sys
import time
import shutil
import zipfile
import tempfile
import datetime
import webbrowser
from PIL import Image
import pytesseract

import app_paths

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Chemins centralisés (cross-platform, compatible PyInstaller).
# En mode source on retombe sur le dossier du projet pour ne pas
# casser le développement habituel.
CONFIG_PATH = str(app_paths.config_path())
APP_VERSION = "1.0.2"
SUPPORT_EMAIL = "candidaturebot.ai@gmail.com"

# 🌐 URL du manifest de mise à jour.
# Format JSON attendu :
#   {
#     "version": "1.0.1",
#     "url": "https://exemple.com/candidaturebot-1.0.1.zip",
#     "notes": "Ce qui a changé...",
#     "released": "2026-04-25"
#   }
# 👉 Tu peux héberger ce fichier où tu veux : un repo GitHub
# (raw.githubusercontent.com/...), GitHub Pages, ton propre serveur, S3,
# etc. Pour pousser une mise à jour : remplace le contenu du JSON et
# le ZIP correspondant à l'URL — toutes les apps connectées récupéreront
# la nouvelle version au prochain check.
UPDATE_MANIFEST_URL = os.getenv(
    "CANDIDATUREBOT_UPDATE_URL",
    "https://raw.githubusercontent.com/lucasegen/candidaturebot/main/version.json"
)

DEFAULT_CONFIG = {
    "profil": {
        "prenom": "", "nom": "", "telephone": "",
        "linkedin": "", "poste_recherche": "", "lettre_type": ""
    },
    "recherche": {
        "mots_cles": ["monteur", "motion design"],
        "localisation": "Paris",
        "rayon_km": 30,
        "contrat": "CDI",
        "mode": "auto",
    },
    "experience": {
        "annees": 0, "competences": [], "langues": []
    },
    "api": {
        "ft_client_id": "",
        "ft_client_secret": "",
        "openai_key": "",
        "anthropic_key": "",
        "gmail_user": "",
        "gmail_password": "",
        "ai_engine": "ollama",
        "ollama_model": "gemma2:2b",
        "adzuna_app_id": "",
        "adzuna_app_key": "",
    },
    "sources": {
        "france_travail": True,
        "indeed": False,
        "linkedin": True,
        "apec": False,
        "welcometothejungle": True,
        "hellowork": True,
        "adzuna": False,    # nécessite clé API gratuite developer.adzuna.com
    },
    "sources_config": {},
    "custom_sources": [],
    "candidatures": [],
    "documents": {
        "cv_path": "",
        "cv_text": "",
        "lettre_path": "",
        "lettre_text": "",
    },
    "preferences": {},
    "routine": {},
    "ui": {"last_tab": "search", "tracker_filter": "Tous"},
}


# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════
def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        # Merge clés top-level
        for key, val in DEFAULT_CONFIG.items():
            if key not in cfg:
                cfg[key] = val if not isinstance(val, (dict, list)) else \
                    (val.copy() if isinstance(val, dict) else list(val))
        # Merge sous-dicts
        for key in ["profil", "recherche", "api", "sources", "sources_config",
                   "experience", "ui", "documents", "preferences", "routine"]:
            if key in DEFAULT_CONFIG and isinstance(DEFAULT_CONFIG[key], dict):
                cfg.setdefault(key, {})
                for subkey, subval in DEFAULT_CONFIG[key].items():
                    cfg[key].setdefault(subkey, subval)
        return cfg
    return {k: (v.copy() if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
            for k, v in DEFAULT_CONFIG.items()}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
# Helper : forcer la fenêtre au premier plan
# ══════════════════════════════════════════════════════════════
def bring_to_front(win):
    """Force une CTkToplevel à passer devant, puis lui rend son comportement normal."""
    try:
        win.update_idletasks()
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        win.after(250, lambda: (win.attributes("-topmost", False), win.focus_force()))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 💜 FENÊTRE EASTER EGG (déclenchée par mot-clef "2202")
# ══════════════════════════════════════════════════════════════
def open_egg_window(parent):
    win = ctk.CTkToplevel(parent)
    win.title("💜")
    win.geometry("440x230")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()
    win.update_idletasks()
    px = parent.winfo_x() + parent.winfo_width() // 2 - 220
    py = parent.winfo_y() + parent.winfo_height() // 2 - 115
    win.geometry(f"+{px}+{py}")

    ctk.CTkLabel(win, text="💜", font=ctk.CTkFont(size=52)).pack(pady=(24, 4))
    ctk.CTkLabel(
        win,
        text="J'espère que tu vas trouver une alternance\n"
             "sur Paris grâce à cette appli, bisous.",
        font=ctk.CTkFont(size=15, weight="bold"),
        justify="center"
    ).pack(pady=(4, 18))
    ctk.CTkButton(win, text="Fermer", width=100, command=win.destroy).pack()
    bring_to_front(win)


# ══════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🎬 Candidature Bot")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.cfg = load_config()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        # Restaure le dernier onglet
        last = self.cfg.get("ui", {}).get("last_tab", "search")
        routes = {
            "search":   self.show_search,
            "tracker":  self.show_tracker,
            "routine":  self.show_routine,
            "profile":  self.show_profile,
            "settings": self.show_settings,
        }
        routes.get(last, self.show_search)()

        # Démarre le scheduler routine en arrière-plan (silencieux si désactivé)
        self._start_routine_scheduler()

    # ── SIDEBAR ───────────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=210, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            self.sidebar, text="🎬 Candidature\nBot",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(30, 25))

        nav = [
            ("🔍  Rechercher",   self.show_search),
            ("📋  Candidatures", self.show_tracker),
            ("🔁  Routine",      self.show_routine),
            ("👤  Mes infos",    self.show_profile),
            ("⚙️  Paramètres",   self.show_settings),
        ]
        self.nav_btns = {}
        for i, (label, cmd) in enumerate(nav, 1):
            b = ctk.CTkButton(
                self.sidebar, text=label, command=cmd,
                height=42, anchor="w", fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray25"),
                font=ctk.CTkFont(size=14)
            )
            b.grid(row=i, column=0, padx=10, pady=3, sticky="ew")
            self.nav_btns[label] = b

        ctk.CTkButton(
            self.sidebar, text="?",
            width=34, height=34, corner_radius=17,
            fg_color="gray25", hover_color="gray35",
            font=ctk.CTkFont(family="Helvetica", size=16, weight="bold"),
            command=self._open_help_window
        ).grid(row=11, column=0, padx=15, pady=(0, 15), sticky="w")

    def _set_active(self, label):
        for l, b in self.nav_btns.items():
            b.configure(fg_color="transparent")
        if label in self.nav_btns:
            self.nav_btns[label].configure(fg_color=("gray75", "gray25"))

    def _clear_main(self):
        for w in self.main.winfo_children():
            w.destroy()

    def _remember_tab(self, key):
        """Mémorise l'onglet actif. Avant de basculer, on déclenche l'auto-save
        des pages avec formulaire (routine, profile, settings) pour ne JAMAIS
        perdre une saisie même si l'utilisateur n'a pas cliqué sur Sauvegarder."""
        ui = self.cfg.setdefault("ui", {})
        old_tab = ui.get("last_tab")
        if old_tab and old_tab != key:
            self._save_current_page_silent(old_tab)
        ui["last_tab"] = key
        save_config(self.cfg)

    def _save_current_page_silent(self, tab_key):
        """Dispatcher : déclenche le silent-save de la page qu'on quitte."""
        try:
            if tab_key == "routine":
                if hasattr(self, "_save_routine_silent"):
                    self._save_routine_silent()
            elif tab_key == "profile":
                if hasattr(self, "_save_profile_silent"):
                    self._save_profile_silent()
            elif tab_key == "settings":
                if hasattr(self, "_save_settings_silent"):
                    self._save_settings_silent()
        except Exception as e:
            # On ne BLOQUE jamais une navigation à cause d'une erreur de save.
            print(f"[auto-save] {tab_key} : {e}")

    # ══════════════════════════════════════════════════════════
    # 🔍 RECHERCHE (auto + manuel fusionnés)
    # ══════════════════════════════════════════════════════════
    def show_search(self):
        self._set_active("🔍  Rechercher")
        self._remember_tab("search")
        self._clear_main()

        # Toggle mode (auto / manuel)
        self.search_mode = self.cfg.get("recherche", {}).get("mode", "auto")
        self._build_search_header()

        self.search_body = ctk.CTkFrame(self.main, fg_color="transparent")
        self.search_body.pack(fill="both", expand=True)
        self.search_body.grid_columnconfigure(0, weight=1)
        self.search_body.grid_rowconfigure(0, weight=1)

        if self.search_mode == "manuel":
            self._render_manual()
        else:
            self._render_auto()

    def _build_search_header(self):
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        title_txt = ("🔍 Recherche automatique" if self.search_mode == "auto"
                     else "➕ Ajout manuel d'une offre")
        ctk.CTkLabel(
            header, text=title_txt,
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")

        if self.search_mode == "auto":
            sources = self.cfg.get("sources", {})
            active = sum(1 for v in sources.values() if v) + len(self.cfg.get("custom_sources", []))
            ctk.CTkLabel(
                header,
                text=f"  •  {active} source(s) active(s)",
                text_color="gray", font=ctk.CTkFont(size=12)
            ).pack(side="left", padx=10)

        # Toggle boutons à droite
        toggle = ctk.CTkFrame(header, fg_color="gray20", corner_radius=8)
        toggle.pack(side="right")

        def mk(label, mode):
            active = (self.search_mode == mode)
            return ctk.CTkButton(
                toggle, text=label,
                height=32, width=140,
                corner_radius=6,
                fg_color=("#1f6aa5" if active else "transparent"),
                text_color=("white" if active else ("gray10", "gray90")),
                hover_color=("#2980b9" if active else "gray25"),
                command=lambda m=mode: self._switch_mode(m),
                font=ctk.CTkFont(size=12, weight=("bold" if active else "normal"))
            )

        mk("🔍 Recherche auto", "auto").pack(side="left", padx=3, pady=3)
        mk("➕ Ajout manuel", "manuel").pack(side="left", padx=3, pady=3)

    def _switch_mode(self, mode):
        self.search_mode = mode
        self.cfg.setdefault("recherche", {})["mode"] = mode
        save_config(self.cfg)
        self.show_search()

    # ── Mode AUTO ────────────────────────────────────────────
    def _render_auto(self):
        rech = self.cfg.get("recherche", {})

        filter_bar = ctk.CTkFrame(self.search_body, fg_color="gray17", corner_radius=10)
        filter_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(filter_bar, text="Mots-clés :").pack(side="left", padx=(12, 4), pady=8)
        self.search_kw_entry = ctk.CTkEntry(filter_bar, width=200, height=30)
        self.search_kw_entry.insert(0, ", ".join(rech.get("mots_cles", [])))
        self.search_kw_entry.pack(side="left", padx=(0, 10), pady=8)

        ctk.CTkLabel(filter_bar, text="Lieu :").pack(side="left", padx=(0, 4))
        self.search_loc_entry = ctk.CTkEntry(filter_bar, width=110, height=30)
        self.search_loc_entry.insert(0, rech.get("localisation", "Paris"))
        self.search_loc_entry.pack(side="left", padx=(0, 10), pady=8)

        # 🆕 Rayon en km
        ctk.CTkLabel(filter_bar, text="Rayon (km) :").pack(side="left", padx=(0, 4))
        self.search_km_entry = ctk.CTkEntry(filter_bar, width=55, height=30)
        self.search_km_entry.insert(0, str(rech.get("rayon_km", 30)))
        self.search_km_entry.pack(side="left", padx=(0, 10), pady=8)

        ctk.CTkLabel(filter_bar, text="Contrat :").pack(side="left", padx=(0, 4))
        self.search_contrat_var = ctk.StringVar(value=rech.get("contrat", "CDI"))
        ctk.CTkOptionMenu(
            filter_bar,
            variable=self.search_contrat_var,
            values=["Tous", "CDI", "CDD", "Stage", "Alternance", "Freelance"],
            width=110, height=30
        ).pack(side="left", padx=(0, 10), pady=8)

        ctk.CTkLabel(filter_bar, text="Afficher :").pack(side="left", padx=(0, 4))
        saved_limit = str(rech.get("max_resultats", "10"))
        if saved_limit not in ("10", "20", "Max"):
            saved_limit = "10"
        self.search_limit_var = ctk.StringVar(value=saved_limit)
        self._search_limit_omenu = ctk.CTkOptionMenu(
            filter_bar,
            variable=self.search_limit_var,
            values=["10", "20", "Max"],
            width=90, height=30,
            command=lambda _v: self._reapply_limit(),
        )
        self._search_limit_omenu.pack(side="left", padx=(0, 10), pady=8)
        # garantit que le texte du bouton reflète bien la valeur
        self._search_limit_omenu.set(saved_limit)

        self.search_box = ctk.CTkScrollableFrame(self.search_body)
        self.search_box.pack(fill="both", expand=True, pady=(0, 10))

        # IMPORTANT : on crée la barre de boutons (et donc self.search_btn)
        # AVANT d'appeler _display_offres pour le cache. Sinon _display_offres
        # tente de configurer un widget détruit et l'exception silencieuse
        # interrompt la suite du rendu (zone vide sans boutons).
        btn_frame = ctk.CTkFrame(self.search_body, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        self.search_btn = ctk.CTkButton(
            btn_frame, text="🚀 Lancer la recherche",
            command=self.run_search, height=42,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.search_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self._searching = False

        ctk.CTkButton(
            btn_frame, text="🌐 Gérer les sources",
            command=self.show_sources_manager, height=42,
            fg_color="gray30", hover_color="gray40"
        ).pack(side="left", padx=(5, 5))

        ctk.CTkButton(
            btn_frame, text="⚙️ Paramètres",
            command=self.show_settings, height=42,
            fg_color="gray30", hover_color="gray40"
        ).pack(side="left", padx=(5, 0))

        # Restaure les résultats si une recherche a déjà été lancée
        cached = getattr(self, "_last_search_offres", None)
        if cached:
            self._display_offres(cached)
        else:
            ctk.CTkLabel(
                self.search_box,
                text="Lance une recherche pour afficher les offres ici.",
                text_color="gray"
            ).pack(pady=40)

    def run_search(self):
        # Si une recherche tourne déjà → le bouton devient "Stop"
        if getattr(self, "_searching", False):
            self._cancel_search = True
            self._searching = False
            self.search_btn.configure(
                state="normal", text="🚀 Lancer la recherche",
                fg_color=("#3a7ebf", "#1f538d"), hover_color=("#325882", "#14375e")
            )
            if hasattr(self, "progress_label") and self.progress_label.winfo_exists():
                self.progress_label.configure(text="⛔ Recherche annulée.")
            return

        kw_raw = self.search_kw_entry.get().strip()
        if kw_raw:
            self.cfg["recherche"]["mots_cles"] = [
                k.strip() for k in kw_raw.split(",") if k.strip()
            ]
        self.cfg["recherche"]["localisation"] = self.search_loc_entry.get().strip()
        try:
            self.cfg["recherche"]["rayon_km"] = int(self.search_km_entry.get().strip() or "30")
        except ValueError:
            self.cfg["recherche"]["rayon_km"] = 30
        self.cfg["recherche"]["contrat"] = self.search_contrat_var.get()
        self.cfg["recherche"]["max_resultats"] = self.search_limit_var.get()
        save_config(self.cfg)

        # 🥚 Easter egg : mot-clef "2202" → fausse offre
        if "2202" in self.cfg["recherche"]["mots_cles"]:
            self._display_offres([{
                "id": "easteregg_2202",
                "titre": "Petite copine à temps plein",
                "entreprise": "Lucas",
                "lieu": "Paris",
                "contrat": "CDI passion",
                "description": "Mission : être adorable. Bonus : câlins illimités.",
                "url": "easteregg://2202",
                "email": "",
                "source": "easteregg",
            }])
            return

        self._searching = True
        self._cancel_search = False
        self.search_btn.configure(
            state="normal", text="⛔ Arrêter la recherche",
            fg_color="#c0392b", hover_color="#e74c3c"
        )
        for w in self.search_box.winfo_children():
            w.destroy()

        self.progress_label = ctk.CTkLabel(
            self.search_box, text="🔄 Connexion aux sources...", text_color="gray"
        )
        self.progress_label.pack(pady=20)

        def _progress(msg):
            if self._cancel_search:
                return
            self.after(0, lambda m=msg: self.progress_label.configure(text=m)
                       if self.progress_label.winfo_exists() else None)

        def task():
            try:
                from scraper import OffreScraper
                scraper = OffreScraper(self.cfg)
                offres = scraper.search_all(progress_cb=_progress)
                if self._cancel_search:
                    return
                self.after(0, lambda: self._display_offres(offres))
            except Exception as e:
                if self._cancel_search:
                    return
                import traceback
                tb = traceback.format_exc()
                self.after(0, lambda: self._display_offres([], error=f"{e}\n\n{tb}"))

        threading.Thread(target=task, daemon=True).start()

    def _display_offres(self, offres, error=None):
        self._searching = False
        self.search_btn.configure(
            state="normal", text="🚀 Lancer la recherche",
            fg_color=("#3a7ebf", "#1f538d"), hover_color=("#325882", "#14375e")
        )
        for w in self.search_box.winfo_children():
            w.destroy()

        if error:
            ctk.CTkLabel(
                self.search_box, text=f"❌ Erreur :\n{error}",
                text_color="red", justify="left", wraplength=600
            ).pack(pady=20, padx=20, anchor="w")
            return

        if not offres:
            self._last_search_offres = []
            ctk.CTkLabel(
                self.search_box,
                text="😕 Aucune offre trouvée.\nVérifie tes sources et filtres.",
                text_color="gray", justify="center"
            ).pack(pady=40)
            return

        # Filtrage contrat côté client (les APIs le gèrent mal)
        contrat_filter = self.cfg.get("recherche", {}).get("contrat", "Tous")
        if contrat_filter and contrat_filter != "Tous":
            offres = [o for o in offres
                      if not o.get("contrat") or contrat_filter.lower() in (o.get("contrat", "") or "").lower()]

        # Mémorise pour persistance entre onglets (volatile)
        self._last_search_offres = offres

        # Limite d'affichage (10 / 20 / Max)
        total_count = len(offres)
        offres = self._apply_display_limit(offres)
        displayed_count = len(offres)

        # ── Barre d'actions groupées (multi-sélection) ──────────
        self._offres_selection = {}   # idx → BooleanVar
        self._postule_buttons = {}    # idx → bouton "Postuler"

        action_bar = ctk.CTkFrame(self.search_box, fg_color="gray17", corner_radius=8)
        action_bar.pack(fill="x", padx=5, pady=(5, 8))

        def _count_text(n_sel):
            if displayed_count < total_count:
                return (f"✅  {displayed_count} / {total_count} "
                        f"offre(s) affichée(s)  —  {n_sel} sélectionnée(s)")
            return (f"✅  {total_count} offre(s) trouvée(s)  —  "
                    f"{n_sel} sélectionnée(s)")

        count_label = ctk.CTkLabel(
            action_bar,
            text=_count_text(0),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#27ae60"
        )
        count_label.pack(side="left", padx=10, pady=8)

        self._search_count_label = count_label

        select_all_var = ctk.BooleanVar(value=False)

        def _refresh_count():
            n = sum(1 for v in self._offres_selection.values() if v.get())
            count_label.configure(text=_count_text(n))

        def _on_select_all():
            val = select_all_var.get()
            for v in self._offres_selection.values():
                v.set(val)
            _refresh_count()

        ctk.CTkCheckBox(
            action_bar, text="Tout sélectionner",
            variable=select_all_var, command=_on_select_all,
            checkbox_width=18, checkbox_height=18,
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=10)

        def _add_selected():
            selected_idx = [i for i, v in self._offres_selection.items() if v.get()]
            if not selected_idx:
                messagebox.showinfo("ℹ️", "Aucune offre sélectionnée.")
                return
            added = 0
            for i in selected_idx:
                if self._postule_buttons.get(i, {}).get("done"):
                    continue  # déjà ajoutée
                self._postuler(offres[i], silent=True, ui_idx=i)
                added += 1
            messagebox.showinfo(
                "✅", f"{added} offre(s) ajoutée(s) aux candidatures."
            )
            _refresh_count()

        ctk.CTkButton(
            action_bar, text="➕ Ajouter aux candidatures",
            command=_add_selected, height=32,
            fg_color="#27ae60", hover_color="#2ecc71"
        ).pack(side="right", padx=10, pady=6)

        SOURCE_COLORS = {
            "france_travail":     "#2980b9",
            "indeed":             "#e74c3c",
            "linkedin":           "#0077b5",
            "apec":               "#f39c12",
            "welcometothejungle": "#3cb371",
        }

        # Set des offres déjà candidates (pour griser le bouton)
        already = set()
        for c in self.cfg.get("candidatures", []):
            key = (c.get("entreprise", ""), c.get("poste", ""), c.get("url", ""))
            already.add(key)

        for i, o in enumerate(offres):
            card = ctk.CTkFrame(self.search_box, corner_radius=8)
            card.pack(fill="x", pady=4, padx=5)
            card.grid_columnconfigure(1, weight=1)

            # Case à cocher à gauche
            sel_var = ctk.BooleanVar(value=False)
            self._offres_selection[i] = sel_var
            ctk.CTkCheckBox(
                card, text="", variable=sel_var,
                command=_refresh_count,
                checkbox_width=20, checkbox_height=20, width=20
            ).grid(row=0, column=0, rowspan=3, padx=(12, 4), pady=8, sticky="n")

            source = o.get("source", "custom")
            badge_color = SOURCE_COLORS.get(source, "#8e44ad")

            ctk.CTkLabel(
                card,
                text=f"  {source.replace('_', ' ').title()}  ",
                font=ctk.CTkFont(size=10),
                fg_color=badge_color, corner_radius=6,
                text_color="white"
            ).grid(row=0, column=1, sticky="w", padx=(4, 0), pady=(8, 0))

            ctk.CTkLabel(
                card,
                text=o.get("titre", "—"),
                font=ctk.CTkFont(size=14, weight="bold")
            ).grid(row=1, column=1, sticky="w", padx=4, pady=(2, 0))

            email_suffix = f"   ✉️ {o.get('email')}" if o.get("email") else ""
            ctk.CTkLabel(
                card,
                text=f"🏢 {o.get('entreprise','?')}   "
                     f"📍 {o.get('lieu','?')}   "
                     f"💼 {o.get('contrat','')}" + email_suffix,
                text_color="gray", font=ctk.CTkFont(size=12)
            ).grid(row=2, column=1, sticky="w", padx=4, pady=(0, 8))

            btn_col = ctk.CTkFrame(card, fg_color="transparent")
            btn_col.grid(row=0, column=2, rowspan=3, padx=12, pady=8, sticky="e")

            if o.get("url"):
                ctk.CTkButton(
                    btn_col, text="🔗 Voir l'offre", width=110, height=30,
                    fg_color="gray30", hover_color="gray40",
                    command=lambda url=o.get("url"): self._open_url(url)
                ).pack(pady=(0, 5))

            key = (o.get("entreprise", ""), o.get("titre", ""), o.get("url", ""))
            is_already = key in already
            btn = ctk.CTkButton(
                btn_col, text=("✅ Ajoutée" if is_already else "➕ Ajouter"),
                width=110, height=30,
                fg_color=("#27ae60" if is_already else ("#3a7ebf", "#1f538d")),
                hover_color=("#2ecc71" if is_already else ("#325882", "#14375e")),
                state=("disabled" if is_already else "normal"),
                command=lambda off=o, ii=i: self._postuler(off, ui_idx=ii)
            )
            btn.pack()
            self._postule_buttons[i] = {"btn": btn, "done": is_already}

    def _apply_display_limit(self, offres):
        raw = (self.search_limit_var.get()
               if hasattr(self, "search_limit_var") else "Max")
        if str(raw).lower() == "max":
            return offres
        try:
            n = int(raw)
        except (ValueError, TypeError):
            return offres
        return offres[:max(0, n)]

    def _reapply_limit(self):
        cached = getattr(self, "_last_search_offres", None)
        if cached is None:
            return
        sb = getattr(self, "search_box", None)
        try:
            if sb is None or not sb.winfo_exists():
                return
        except Exception:
            return
        try:
            self.cfg["recherche"]["max_resultats"] = self.search_limit_var.get()
            save_config(self.cfg)
        except Exception:
            pass
        try:
            self._display_offres(cached)
        except Exception:
            pass

    def _open_url(self, url):
        if url == "easteregg://2202":
            open_egg_window(self)
            return
        if not url:
            return
        # Whitelist stricte de schémas pour éviter file:// ou javascript:
        u = str(url).strip()
        if not (u.startswith("http://") or u.startswith("https://")
                or u.startswith("mailto:")):
            messagebox.showwarning(
                "URL bloquée",
                f"Ce lien n'utilise pas un schéma autorisé :\n{u[:80]}"
            )
            return
        webbrowser.open(u)

    def _postuler(self, offre, silent=False, ui_idx=None):
        self.cfg.setdefault("candidatures", []).append({
            "entreprise": offre.get("entreprise", ""),
            "poste":      offre.get("titre", ""),
            "email":      offre.get("email", ""),
            "lieu":       offre.get("lieu", ""),
            "contrat":    offre.get("contrat", ""),
            "url":        offre.get("url", ""),
            "source":     offre.get("source", ""),
            "description": offre.get("description", ""),
            "statut":     "À envoyer",
            "date":       datetime.date.today().isoformat(),
            "notes":      ""
        })
        save_config(self.cfg)

        # Transforme le bouton en coche verte (plus de popup)
        if ui_idx is not None:
            info = getattr(self, "_postule_buttons", {}).get(ui_idx)
            if info and info["btn"].winfo_exists():
                info["btn"].configure(
                    text="✅ Ajoutée", state="disabled",
                    fg_color="#27ae60", hover_color="#2ecc71"
                )
                info["done"] = True

    # ── Mode MANUEL (intégré dans Rechercher) ────────────────
    def _render_manual(self):
        # Zone import image / URL
        import_zone = ctk.CTkFrame(self.search_body, fg_color="gray17", corner_radius=10)
        import_zone.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            import_zone, text="📥 Importer une offre",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        # Zone OCR : image
        img_row = ctk.CTkFrame(import_zone, fg_color="transparent")
        img_row.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(img_row, text="🖼 Image :", width=80, anchor="w").pack(side="left")
        self.drop_label = ctk.CTkLabel(
            img_row,
            text="📎 Clique ici pour sélectionner une image (OCR automatique)",
            text_color="gray", cursor="hand2", fg_color="gray25",
            corner_radius=6, anchor="w", padx=12, pady=8
        )
        self.drop_label.pack(side="left", fill="x", expand=True)
        self.drop_label.bind("<Button-1>", lambda e: self._import_image_ocr())

        # 🆕 URL d'analyse
        url_row = ctk.CTkFrame(import_zone, fg_color="transparent")
        url_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(url_row, text="🔗 URL :", width=80, anchor="w").pack(side="left")
        self.manual_url_entry = ctk.CTkEntry(
            url_row, height=32, placeholder_text="https://exemple.com/offre-poste"
        )
        self.manual_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            url_row, text="🔍 Analyser la page",
            command=self._analyze_manual_url,
            height=32, width=150,
            fg_color="#2980b9", hover_color="#3498db"
        ).pack(side="left")

        # Formulaire
        form_scroll = ctk.CTkScrollableFrame(self.search_body)
        form_scroll.pack(fill="both", expand=True, pady=(0, 10))
        form_scroll.grid_columnconfigure(1, weight=1)

        manual_fields_def = [
            ("Entreprise",     "entreprise",  False),
            ("Poste",          "poste",       False),
            ("Email",          "email",       False),
            ("Lieu",           "lieu",        False),
            ("Contrat",        "contrat",     False),
            ("URL de l'offre", "url",         False),
            ("Description",    "description", True),
            ("Notes",          "notes",       True),
        ]

        self.manual_fields = {}
        for i, (label, key, multiline) in enumerate(manual_fields_def):
            ctk.CTkLabel(form_scroll, text=label).grid(
                row=i, column=0, sticky="nw" if multiline else "w",
                padx=(5, 15), pady=6)
            if multiline:
                w = ctk.CTkTextbox(form_scroll, height=80)
            else:
                w = ctk.CTkEntry(form_scroll, height=36)
            w.grid(row=i, column=1, sticky="ew", pady=6, padx=(0, 5))
            self.manual_fields[key] = w
            if multiline:
                self._isolate_textbox_scroll(w)

        btn_row = ctk.CTkFrame(self.search_body, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(
            btn_row, text="💾 Ajouter aux candidatures",
            command=self._save_manual, height=42,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(
            btn_row, text="🤖 Générer lettre IA",
            command=self._generate_lettre_manual, height=42,
            fg_color="#6c3483", hover_color="#7d3c98"
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            btn_row, text="🗑 Effacer",
            command=self._clear_manual, height=42,
            fg_color="gray30", hover_color="gray40"
        ).pack(side="left")

    def _import_image_ocr(self):
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp")]
        )
        if not path:
            return
        self.drop_label.configure(text="⏳ Analyse OCR en cours...", text_color="gray")

        def task():
            try:
                img = Image.open(path)
                text = pytesseract.image_to_string(img, lang="fra")
                data = self._parse_ocr(text)
                self.after(0, lambda: self._fill_manual(data))
            except Exception as e:
                err_ocr = str(e)
                self.after(0, lambda err_ocr=err_ocr: self.drop_label.configure(
                    text=f"❌ Erreur OCR : {err_ocr}", text_color="red"))

        threading.Thread(target=task, daemon=True).start()

    def _parse_ocr(self, texte):
        data = {"description": texte.strip()}
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", texte)
        if emails:
            data["email"] = emails[0]
        for c in ["CDI", "CDD", "Stage", "Alternance", "Freelance", "Intérim"]:
            if c.lower() in texte.lower():
                data["contrat"] = c
                break
        villes = ["Paris", "Lyon", "Marseille", "Bordeaux", "Nantes",
                  "Toulouse", "Lille", "Strasbourg", "Nice", "Rennes"]
        for v in villes:
            if v.lower() in texte.lower():
                data["lieu"] = v
                break
        lignes = [l.strip() for l in texte.split("\n") if len(l.strip()) > 4]
        if lignes:
            data["poste"] = lignes[0]
        if len(lignes) > 1:
            data["entreprise"] = lignes[1]
        return data

    def _analyze_manual_url(self):
        url = self.manual_url_entry.get().strip()
        if not url:
            messagebox.showwarning("⚠️", "Colle une URL d'abord.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.manual_url_entry.delete(0, "end")
            self.manual_url_entry.insert(0, url)

        self.drop_label.configure(text="⏳ Analyse de la page en cours...", text_color="gray")

        def task():
            try:
                from scraper import OffreScraper
                scraper = OffreScraper(self.cfg)
                data = scraper.analyze_url(url)
                if "titre" in data and "poste" not in data:
                    data["poste"] = data.pop("titre")
                self.after(0, lambda: self._fill_manual(data))
                self.after(0, lambda: self.drop_label.configure(
                    text="✅ Page analysée — vérifie et corrige si besoin",
                    text_color="#27ae60"
                ))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self.drop_label.configure(
                    text=f"❌ Erreur analyse : {err[:80]}", text_color="red"))

        threading.Thread(target=task, daemon=True).start()

    def _fill_manual(self, data):
        if "titre" in data and "poste" not in data:
            data["poste"] = data["titre"]
        for key, val in data.items():
            if key in self.manual_fields:
                widget = self.manual_fields[key]
                if isinstance(widget, ctk.CTkTextbox):
                    widget.delete("1.0", "end")
                    widget.insert("1.0", val)
                else:
                    widget.delete(0, "end")
                    widget.insert(0, val)

    def _clear_manual(self):
        for key, widget in self.manual_fields.items():
            if isinstance(widget, ctk.CTkTextbox):
                widget.delete("1.0", "end")
            else:
                widget.delete(0, "end")
        if hasattr(self, "manual_url_entry"):
            self.manual_url_entry.delete(0, "end")
        self.drop_label.configure(
            text="📎 Clique ici pour sélectionner une image (OCR automatique)",
            text_color="gray"
        )

    def _save_manual(self):
        def get(key):
            w = self.manual_fields[key]
            if isinstance(w, ctk.CTkTextbox):
                return w.get("1.0", "end").strip()
            return w.get().strip()

        if not get("entreprise") and not get("poste"):
            messagebox.showwarning("⚠️", "Remplis au moins l'entreprise ou le poste.")
            return

        self.cfg.setdefault("candidatures", []).append({
            "entreprise":  get("entreprise"),
            "poste":       get("poste"),
            "email":       get("email"),
            "lieu":        get("lieu"),
            "contrat":     get("contrat"),
            "url":         get("url"),
            "notes":       get("notes"),
            "description": get("description"),
            "statut":      "À envoyer",
            "date":        datetime.date.today().isoformat(),
            "source":      "manuel"
        })
        save_config(self.cfg)
        messagebox.showinfo("✅", "Offre ajoutée à tes candidatures !")
        self._clear_manual()

    def _generate_lettre_manual(self):
        def get(key):
            w = self.manual_fields[key]
            if isinstance(w, ctk.CTkTextbox):
                return w.get("1.0", "end").strip()
            return w.get().strip()
        offre = {
            "titre":       get("poste"),
            "poste":       get("poste"),
            "entreprise":  get("entreprise"),
            "description": get("description"),
        }
        self._open_lettre_window(offre)

    # ══════════════════════════════════════════════════════════
    # 🌐 GESTIONNAIRE DE SOURCES
    # ══════════════════════════════════════════════════════════
    def show_sources_manager(self):
        win = ctk.CTkToplevel(self)
        win.title("🌐 Gérer les sources de recherche")
        win.geometry("600x650")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 300
        py = self.winfo_y() + self.winfo_height() // 2 - 325
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="🌐 Sources de recherche",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 5), padx=20, anchor="w")
        ctk.CTkLabel(
            win,
            text="Active/désactive les plateformes. Ajoute tes propres sites.",
            text_color="gray", font=ctk.CTkFont(size=12)
        ).pack(padx=20, anchor="w", pady=(0, 15))

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        sources = self.cfg.setdefault("sources", DEFAULT_CONFIG["sources"].copy())
        custom_sources = self.cfg.setdefault("custom_sources", [])

        BUILTIN = {
            "france_travail":     ("🇫🇷 France Travail",      "API officielle — nécessite Client ID/Secret (gratuit)"),
            "indeed":             ("🔴 Indeed",                "Scraping gratuit — souvent bloqué (Cloudflare)"),
            "linkedin":           ("🔵 LinkedIn",              "Scraping gratuit — fonctionne, ~100 résultats max"),
            "apec":               ("🟠 APEC",                  "API publique — cadres & managers (endpoint instable)"),
            "welcometothejungle": ("🟢 Welcome to the Jungle", "API publique — startups & créa (clé Algolia volatile)"),
            "hellowork":          ("💼 HelloWork",             "Scraping gratuit — marché français, sans clé"),
            "adzuna":             ("🔍 Adzuna",                "API gratuite (1000 req/mois) — clé requise dans Paramètres"),
        }

        self.source_switches = {}

        ctk.CTkLabel(
            scroll, text="Plateformes intégrées",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 8))

        for key, (label, desc) in BUILTIN.items():
            row = ctk.CTkFrame(scroll, fg_color="gray17", corner_radius=8)
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(0, weight=1)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=0, sticky="w", padx=12, pady=8)
            ctk.CTkLabel(info, text=label, font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            ctk.CTkLabel(info, text=desc, text_color="gray",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")

            sw = ctk.CTkSwitch(row, text="")
            if sources.get(key, False):
                sw.select()
            else:
                sw.deselect()
            sw.grid(row=0, column=1, padx=(0, 12))
            self.source_switches[key] = sw

        ctk.CTkLabel(
            scroll, text="Sites personnalisés",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(20, 8))

        self.custom_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self.custom_frame.pack(fill="x")

        def refresh_custom():
            for w in self.custom_frame.winfo_children():
                w.destroy()
            for i, site in enumerate(custom_sources):
                row = ctk.CTkFrame(self.custom_frame, fg_color="gray17", corner_radius=8)
                row.pack(fill="x", pady=3)
                row.grid_columnconfigure(0, weight=1)

                ctk.CTkLabel(
                    row,
                    text=f"🌐 {site.get('nom', 'Site ' + str(i+1))}",
                    font=ctk.CTkFont(weight="bold")
                ).grid(row=0, column=0, sticky="w", padx=12, pady=4)
                ctk.CTkLabel(
                    row,
                    text=site.get("url_base", "—"),
                    text_color="gray", font=ctk.CTkFont(size=11)
                ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))

                action_frame = ctk.CTkFrame(row, fg_color="transparent")
                action_frame.grid(row=0, column=1, rowspan=2, padx=10, sticky="e")
                ctk.CTkButton(
                    action_frame, text="✏️", width=32, height=28,
                    fg_color="gray30", hover_color="gray40",
                    command=lambda idx=i: edit_custom(idx)
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    action_frame, text="🗑", width=32, height=28,
                    fg_color="gray30", hover_color="#e74c3c",
                    command=lambda idx=i: delete_custom(idx)
                ).pack(side="left", padx=2)

        def _custom_form_window(title, existing=None):
            """Popup formulaire partagé entre add & edit."""
            w = ctk.CTkToplevel(win)
            w.title(title)
            w.geometry("520x520")
            w.transient(win)
            w.grab_set()

            ctk.CTkLabel(
                w, text=title,
                font=ctk.CTkFont(size=15, weight="bold")
            ).pack(pady=(20, 10), padx=20, anchor="w")

            ctk.CTkLabel(
                w,
                text="💡 Indique un user/password si le site en demande.\n"
                     "Les sélecteurs CSS sont optionnels (pour extraire les offres).",
                text_color="gray", font=ctk.CTkFont(size=11), justify="left"
            ).pack(padx=20, anchor="w", pady=(0, 10))

            form = ctk.CTkScrollableFrame(w, fg_color="transparent")
            form.pack(fill="both", expand=True, padx=20)
            form.grid_columnconfigure(1, weight=1)

            fields = [
                ("Nom du site",           "nom",            "ex: Glassdoor",                         False),
                ("URL de recherche",      "url_base",       "https://site.com/jobs?q={keywords}",    False),
                ("Nom d'utilisateur",     "user",           "optionnel (si login requis)",           False),
                ("Mot de passe",          "password",       "optionnel",                             True),
                ("Sélecteur CSS item",    "selector_item",  "optionnel — ex: .job-card",             False),
                ("Sélecteur CSS titre",   "selector_title", "optionnel — ex: h3",                    False),
                ("Sélecteur CSS lien",    "selector_link",  "optionnel — ex: a",                     False),
                ("Notes",                 "notes",          "optionnel",                             False),
            ]
            entries = {}
            for i, (label, key, placeholder, hidden) in enumerate(fields):
                ctk.CTkLabel(form, text=label).grid(
                    row=i, column=0, sticky="w", padx=(0, 10), pady=5)
                e = ctk.CTkEntry(form, placeholder_text=placeholder,
                                 height=34, show="*" if hidden else "")
                if existing:
                    e.insert(0, existing.get(key, ""))
                e.grid(row=i, column=1, sticky="ew", pady=5)
                entries[key] = e

            return w, entries

        def add_custom():
            w, entries = _custom_form_window("➕ Nouveau site de recherche")
            def do_add():
                new_site = {k: e.get().strip() for k, e in entries.items()}
                if not new_site.get("nom") or not new_site.get("url_base"):
                    messagebox.showwarning("⚠️",
                        "Remplis au moins le nom et l'URL de recherche.",
                        parent=w)
                    return
                custom_sources.append(new_site)
                save_config(self.cfg)
                refresh_custom()
                w.destroy()
            ctk.CTkButton(w, text="➕ Ajouter", command=do_add, height=38).pack(pady=15)
            bring_to_front(w)

        def edit_custom(idx):
            site = custom_sources[idx]
            w, entries = _custom_form_window(
                f"✏️ Modifier — {site.get('nom','Site')}", existing=site)
            def do_save():
                for k, e in entries.items():
                    custom_sources[idx][k] = e.get().strip()
                save_config(self.cfg)
                refresh_custom()
                w.destroy()
            ctk.CTkButton(w, text="💾 Sauvegarder", command=do_save, height=38).pack(pady=15)
            bring_to_front(w)

        def delete_custom(idx):
            if messagebox.askyesno("Supprimer ?",
                                   f"Supprimer « {custom_sources[idx].get('nom','ce site')} » ?",
                                   parent=win):
                custom_sources.pop(idx)
                save_config(self.cfg)
                refresh_custom()

        ctk.CTkButton(
            scroll, text="➕ Ajouter un site personnalisé",
            command=add_custom, height=36,
            fg_color="gray25", hover_color="gray35"
        ).pack(anchor="w", pady=(8, 0))

        refresh_custom()

        def save_sources():
            for key, sw in self.source_switches.items():
                sources[key] = sw.get() == 1
            save_config(self.cfg)
            messagebox.showinfo("✅", "Sources sauvegardées !", parent=win)
            win.destroy()
            self.show_search()

        ctk.CTkButton(
            win, text="💾 Sauvegarder", command=save_sources, height=42,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(fill="x", padx=15, pady=15)

        bring_to_front(win)

    # ══════════════════════════════════════════════════════════
    # 🤖 LETTRE DE MOTIVATION IA
    # ══════════════════════════════════════════════════════════
    def _open_lettre_window(self, offre, idx=None, on_save=None):
        """Ouvre la fenêtre de rédaction de lettre.
        - Si idx est fourni, la lettre est liée à cette candidature (sauvegarde par candidature).
        - on_save : callback appelé après sauvegarde (pour rafraîchir le statut dans le parent).
        """
        win = ctk.CTkToplevel(self)
        win.title("🤖 Génération lettre de motivation")
        win.geometry("780x780")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 390
        py = self.winfo_y() + self.winfo_height() // 2 - 390
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win,
            text=f"🤖 {offre.get('titre') or offre.get('poste','?')} — {offre.get('entreprise','?')}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(18, 6), padx=20, anchor="w")

        # ── Sélecteur de ton (cumulables) ────────────────────
        ton_bar = ctk.CTkFrame(win, fg_color="gray17", corner_radius=8)
        ton_bar.pack(fill="x", padx=20, pady=(0, 6))
        ctk.CTkLabel(
            ton_bar, text="🎭 Ton (cumulable) :",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=10, pady=(8, 2))

        TONS = [
            ("Professionnel",  "professionnel, sobre, formel"),
            ("Décontracté",    "décontracté mais soigné, ton naturel"),
            ("Enthousiaste",   "enthousiaste, énergique, qui transmet de la motivation"),
            ("Chaleureux",     "chaleureux, humain, proche"),
            ("Confiant",       "confiant sans arrogance, assertif"),
            ("Direct",         "direct, concis, sans fioritures"),
            ("Persuasif",      "persuasif, axé sur la valeur apportée"),
            ("Créatif",        "créatif, original, qui sort du lot"),
            ("Humble",         "humble, modeste, à l'écoute"),
            ("Concret",        "concret, chiffré, axé résultats"),
            ("Narratif",       "narratif, raconte une histoire / un parcours"),
            ("Technique",      "technique, précis sur les compétences métier"),
        ]
        ton_vars = {}
        tons_frame = ctk.CTkFrame(ton_bar, fg_color="transparent")
        tons_frame.pack(fill="x", padx=10, pady=(0, 6))
        for i, (label, _) in enumerate(TONS):
            v = ctk.BooleanVar(value=(label == "Professionnel"))
            ton_vars[label] = v
            ctk.CTkCheckBox(
                tons_frame, text=label, variable=v,
                checkbox_width=16, checkbox_height=16,
                font=ctk.CTkFont(size=11)
            ).grid(row=i // 4, column=i % 4, sticky="w", padx=6, pady=3)

        # ── Instructions libres ──────────────────────────────
        instr_bar = ctk.CTkFrame(win, fg_color="gray17", corner_radius=8)
        instr_bar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(
            instr_bar, text="💬 Instructions libres (optionnel) :",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=10, pady=(8, 2))
        instr_entry = ctk.CTkTextbox(instr_bar, height=60, font=ctk.CTkFont(size=11), wrap="word")
        instr_entry.pack(fill="x", padx=10, pady=(0, 8))

        text_area = ctk.CTkTextbox(win, font=ctk.CTkFont(size=13), wrap="word")
        text_area.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Si lettre déjà sauvegardée pour cette candidature, on la préremplit
        existing_lettre = ""
        if idx is not None:
            try:
                existing_lettre = (self.cfg.get("candidatures", [])[idx] or {}).get("lettre", "") or ""
            except (IndexError, TypeError):
                existing_lettre = ""
        if existing_lettre:
            text_area.insert("1.0", existing_lettre)
        else:
            text_area.insert("1.0", "⏳ Génération en cours...")

        def _set_text(txt):
            text_area.delete("1.0", "end")
            text_area.insert("1.0", txt)

        def _current_directives():
            tons = [desc for label, desc in TONS if ton_vars[label].get()]
            instr = instr_entry.get("1.0", "end").strip()
            parts = []
            if tons:
                parts.append("TON souhaité : " + " ; ".join(tons) + ".")
            if instr:
                parts.append("INSTRUCTIONS SUPPLÉMENTAIRES : " + instr)
            return "\n".join(parts)

        def generate():
            try:
                from ai_engine import AIEngine
                engine = AIEngine(config=self.cfg)
                # Construit prompt enrichi avec directives
                base = engine._build_prompt_lettre(offre, self.cfg)
                directives = _current_directives()
                prompt = base + (f"\n\n{directives}" if directives else "")
                result = engine._run(prompt, offre, self.cfg, mode="lettre")
                win.after(0, lambda: _set_text(result))
            except Exception as e:
                import traceback
                err_msg = f"❌ Erreur : {e}\n\n{traceback.format_exc()}"
                win.after(0, lambda err_msg=err_msg: _set_text(err_msg))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 18))

        ctk.CTkButton(
            btn_row, text="🪄 Générer avec ces réglages",
            command=lambda: (text_area.delete("1.0", "end"),
                             text_area.insert("1.0", "⏳ Génération en cours..."),
                             threading.Thread(target=generate, daemon=True).start()),
            fg_color="#6c3483", hover_color="#7d3c98", height=38
        ).pack(side="left", padx=(0, 5))

        def copy_text():
            txt = text_area.get("1.0", "end").strip()
            win.clipboard_clear()
            win.clipboard_append(txt)
            messagebox.showinfo("✅", "Copié !", parent=win)

        ctk.CTkButton(
            btn_row, text="📋 Copier",
            command=copy_text, height=38,
            fg_color="gray30", hover_color="gray40"
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="💾 Sauvegarder dans profil",
            command=lambda: self._save_lettre_to_profil(
                text_area.get("1.0", "end").strip(), win),
            height=38
        ).pack(side="left", padx=(0, 5))

        # Si on vient d'une candidature, permet une sauvegarde liée à celle-ci
        if idx is not None:
            def _save_to_candidature():
                txt = text_area.get("1.0", "end").strip()
                if not txt or txt.startswith("⏳") or txt.startswith("❌"):
                    messagebox.showwarning("⚠️", "Rien à sauvegarder.", parent=win)
                    return
                try:
                    self.cfg["candidatures"][idx]["lettre"] = txt
                    save_config(self.cfg)
                    messagebox.showinfo("✅", "Lettre sauvegardée pour cette candidature !", parent=win)
                    if on_save:
                        on_save(txt)
                    win.destroy()
                except (IndexError, KeyError) as e:
                    messagebox.showerror("❌", f"Impossible de sauvegarder : {e}", parent=win)

            ctk.CTkButton(
                btn_row, text="📎 Lier à cette candidature",
                command=_save_to_candidature,
                fg_color="#27ae60", hover_color="#2ecc71", height=38
            ).pack(side="left")

        # Génère automatiquement uniquement si pas de lettre préexistante
        if not existing_lettre:
            threading.Thread(target=generate, daemon=True).start()
        bring_to_front(win)

    def _save_lettre_to_profil(self, txt, win):
        self.cfg.setdefault("profil", {})["lettre_type"] = txt
        save_config(self.cfg)
        messagebox.showinfo("✅", "Lettre sauvegardée dans ton profil !", parent=win)

    # ══════════════════════════════════════════════════════════
    # 📋 CANDIDATURES
    # ══════════════════════════════════════════════════════════
    def show_tracker(self):
        self._set_active("📋  Candidatures")
        self._remember_tab("tracker")
        self._clear_main()

        header_row = ctk.CTkFrame(self.main, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(
            header_row, text="📋 Mes candidatures",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")

        candidatures = self.cfg.get("candidatures", [])

        # Stats
        stats = {}
        for c in candidatures:
            s = c.get("statut", "À envoyer")
            stats[s] = stats.get(s, 0) + 1

        stats_frame = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=10)
        stats_frame.pack(fill="x", pady=(0, 10))

        COULEURS_STAT = {
            "À envoyer": "#7f8c8d", "Envoyée": "#2980b9",
            "Relancée":  "#f39c12", "Entretien": "#8e44ad",
            "Refusée":   "#e74c3c", "Acceptée": "#27ae60"
        }

        ctk.CTkLabel(
            stats_frame,
            text=f"Total : {len(candidatures)}",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=15, pady=10)

        for statut, count in stats.items():
            ctk.CTkLabel(
                stats_frame,
                text=f"  {statut} : {count}  ",
                fg_color=COULEURS_STAT.get(statut, "gray"),
                corner_radius=6, font=ctk.CTkFont(size=11), text_color="white"
            ).pack(side="left", padx=4, pady=10)

        # Barre d'action : filtre auto + envoyer tout + export
        action_row = ctk.CTkFrame(self.main, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(action_row, text="Filtre :").pack(side="left", padx=(0, 8))

        scroll_frame = ctk.CTkScrollableFrame(self.main)
        last_filter = self.cfg.get("ui", {}).get("tracker_filter", "Tous")
        self.tracker_filter_var = ctk.StringVar(value=last_filter)

        def on_filter_change(_=None):
            self.cfg.setdefault("ui", {})["tracker_filter"] = self.tracker_filter_var.get()
            save_config(self.cfg)
            self._refresh_tracker_list(scroll_frame)

        ctk.CTkOptionMenu(
            action_row,
            variable=self.tracker_filter_var,
            values=["Tous", "À envoyer", "Envoyée", "Relancée",
                    "Entretien", "Refusée", "Acceptée"],
            width=140, height=32,
            command=on_filter_change
        ).pack(side="left")

        ctk.CTkButton(
            action_row, text="📊 Exporter CSV",
            command=self._export_csv,
            height=32, width=130,
            fg_color="gray30", hover_color="gray40"
        ).pack(side="right")

        # 🆕 Bouton "tout envoyer" les 'À envoyer'
        ctk.CTkButton(
            action_row, text="📧 Tout envoyer",
            command=lambda: self._send_all_pending(scroll_frame),
            height=32, width=140,
            fg_color="#27ae60", hover_color="#2ecc71"
        ).pack(side="right", padx=(5, 5))

        # ── Barre multi-sélection (toujours visible) ──────────
        self._tracker_selection = {}     # real_idx → BooleanVar
        self._tracker_page = 0           # pagination interne
        select_row = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=8)
        select_row.pack(fill="x", pady=(0, 8))

        self._tracker_select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            select_row, text="Tout sélectionner",
            variable=self._tracker_select_all_var,
            command=lambda: self._tracker_toggle_all(scroll_frame),
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=12, pady=8)

        self._tracker_sel_count_label = ctk.CTkLabel(
            select_row, text="0 sélectionnée(s)",
            text_color="gray", font=ctk.CTkFont(size=11)
        )
        self._tracker_sel_count_label.pack(side="left", padx=(12, 0))

        ctk.CTkButton(
            select_row, text="🗑 Supprimer la sélection",
            command=lambda: self._tracker_delete_selected(scroll_frame),
            height=30, width=200,
            fg_color="#c0392b", hover_color="#e74c3c"
        ).pack(side="right", padx=10, pady=6)

        scroll_frame.pack(fill="both", expand=True)
        self._refresh_tracker_list(scroll_frame)

    # Palette des couleurs de statut (utilisée à plusieurs endroits)
    STATUT_COLORS = {
        "À envoyer": "#7f8c8d",
        "Envoyée":   "#2980b9",
        "Relancée":  "#f39c12",
        "Entretien": "#8e44ad",
        "Refusée":   "#e74c3c",
        "Acceptée":  "#27ae60",
    }

    @staticmethod
    def _statut_hover(color):
        """Retourne une variante légèrement plus claire pour le hover."""
        hover = {
            "#7f8c8d": "#95a5a6",
            "#2980b9": "#3498db",
            "#f39c12": "#f5b041",
            "#8e44ad": "#a569bd",
            "#e74c3c": "#ec7063",
            "#27ae60": "#2ecc71",
        }
        return hover.get(color, color)

    # Nombre max de cartes à rendre par page (perf : Tk devient lent au-delà)
    TRACKER_PAGE_SIZE = 30

    def _refresh_tracker_list(self, container):
        for w in container.winfo_children():
            w.destroy()

        candidatures = self.cfg.get("candidatures", [])
        filtre_val = getattr(self, "tracker_filter_var", None)
        filtre_val = filtre_val.get() if filtre_val else "Tous"

        STATUTS = ["À envoyer", "Envoyée", "Relancée", "Entretien", "Refusée", "Acceptée"]

        filtered = [
            (len(candidatures) - 1 - i, c)
            for i, c in enumerate(reversed(candidatures))
            if filtre_val == "Tous" or c.get("statut") == filtre_val
        ]

        if not filtered:
            ctk.CTkLabel(
                container, text="Aucune candidature pour ce filtre.",
                text_color="gray"
            ).pack(pady=40)
            self._tracker_update_selection_count()
            return

        # ── Pagination : on découpe filtered par tranches ───────
        total = len(filtered)
        page_size = self.TRACKER_PAGE_SIZE
        max_page = max(0, (total - 1) // page_size)
        # Clamp la page courante (au cas où on a supprimé des éléments)
        if not hasattr(self, "_tracker_page"):
            self._tracker_page = 0
        self._tracker_page = max(0, min(self._tracker_page, max_page))
        page = self._tracker_page

        start = page * page_size
        end = min(start + page_size, total)
        page_items = filtered[start:end]

        # Garantit que self._tracker_selection contient une BooleanVar pour
        # chaque candidature visible (sinon les cases sautent au reload).
        if not hasattr(self, "_tracker_selection"):
            self._tracker_selection = {}
        # Nettoie les BooleanVar pour les candidatures supprimées
        valid_indices = {real_i for real_i, _ in filtered}
        for k in list(self._tracker_selection.keys()):
            if k not in valid_indices:
                self._tracker_selection.pop(k, None)

        STATUT_COLORS = self.STATUT_COLORS

        for real_i, c in page_items:
            statut = c.get("statut", "À envoyer")
            statut_color = STATUT_COLORS.get(statut, "#7f8c8d")

            # Wrapper coloré qui forme la bordure gauche (5px) par statut
            wrapper = ctk.CTkFrame(
                container, corner_radius=8,
                fg_color=statut_color,
            )
            wrapper.pack(fill="x", pady=4, padx=3)

            card = ctk.CTkFrame(wrapper, corner_radius=6)
            card.pack(fill="both", expand=True, padx=(5, 0), pady=0)
            card.grid_columnconfigure(1, weight=1)

            # Checkbox de sélection multiple (col 0)
            sel_var = self._tracker_selection.get(real_i)
            if sel_var is None:
                sel_var = ctk.BooleanVar(value=False)
                self._tracker_selection[real_i] = sel_var
            ctk.CTkCheckBox(
                card, text="", variable=sel_var, width=22,
                command=self._tracker_update_selection_count
            ).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8, sticky="w")

            # Badge statut + libellé (col 1)
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.grid(row=0, column=1, sticky="w", padx=4, pady=(8, 2))

            statut_badge = ctk.CTkLabel(
                info_frame,
                text=f"  {statut}  ",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=statut_color, corner_radius=6,
                text_color="white",
            )
            statut_badge.pack(side="left", padx=(0, 8))

            ctk.CTkLabel(
                info_frame,
                text=f"{c.get('entreprise','—')} — {c.get('poste','—')}",
                font=ctk.CTkFont(size=13, weight="bold")
            ).pack(side="left")

            if c.get("source"):
                ctk.CTkLabel(
                    info_frame, text=f"  [{c.get('source')}]",
                    text_color="gray", font=ctk.CTkFont(size=11)
                ).pack(side="left")

            ctk.CTkLabel(
                card,
                text=f"📍 {c.get('lieu','?')}   💼 {c.get('contrat','')}   📅 {c.get('date','—')}",
                text_color="gray", font=ctk.CTkFont(size=11)
            ).grid(row=1, column=1, sticky="w", padx=4, pady=(0, 8))

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=0, column=2, rowspan=2, padx=12, pady=8, sticky="e")

            statut_var = ctk.StringVar(value=c.get("statut", "À envoyer"))
            statut_menu = ctk.CTkOptionMenu(
                actions, variable=statut_var, values=STATUTS, width=130,
                fg_color=statut_color,
                button_color=statut_color,
                button_hover_color=self._statut_hover(statut_color),
                text_color="white",
            )
            statut_menu.pack(pady=(0, 5))

            def _on_change(val, idx=real_i, menu=statut_menu,
                           wrap=wrapper, badge=statut_badge):
                self._update_statut(idx, val)
                new_color = STATUT_COLORS.get(val, "#7f8c8d")
                # Mise à jour visuelle immédiate (pas besoin de rebuild la liste)
                wrap.configure(fg_color=new_color)
                badge.configure(text=f"  {val}  ", fg_color=new_color)
                menu.configure(
                    fg_color=new_color,
                    button_color=new_color,
                    button_hover_color=self._statut_hover(new_color),
                )
                # Si le filtre est actif et que le nouveau statut ne match plus,
                # on rebuild pour faire disparaître la carte
                cur_filter = getattr(self, "tracker_filter_var", None)
                cur_filter = cur_filter.get() if cur_filter else "Tous"
                if cur_filter != "Tous" and cur_filter != val:
                    self._refresh_tracker_list(container)

            statut_menu.configure(command=_on_change)

            btn_row = ctk.CTkFrame(actions, fg_color="transparent")
            btn_row.pack()

            if c.get("url"):
                ctk.CTkButton(
                    btn_row, text="🔗", width=32, height=28,
                    fg_color="gray30", hover_color="gray40",
                    command=lambda url=c["url"]: self._open_url(url)
                ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_row, text="🤖", width=32, height=28,
                fg_color="#6c3483", hover_color="#7d3c98",
                command=lambda off=c, i=real_i: self._open_lettre_window(off, idx=i)
            ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_row, text="📧", width=32, height=28,
                fg_color="#2980b9", hover_color="#3498db",
                command=lambda off=c, idx=real_i, cont=container:
                    self._send_candidature(off, idx, cont)
            ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_row, text="🗑", width=32, height=28,
                fg_color="gray30", hover_color="#e74c3c",
                command=lambda idx=real_i, cont=container:
                    self._delete_candidature(idx, cont)
            ).pack(side="left", padx=2)

        # ── Footer pagination ────────────────────────────────────
        if max_page > 0:
            pager = ctk.CTkFrame(container, fg_color="transparent")
            pager.pack(fill="x", pady=(8, 4))

            ctk.CTkButton(
                pager, text="← Précédent",
                command=lambda: self._tracker_change_page(container, -1),
                state=("normal" if page > 0 else "disabled"),
                width=110, height=30,
                fg_color="gray30", hover_color="gray40"
            ).pack(side="left", padx=(8, 4))

            ctk.CTkLabel(
                pager,
                text=f"Page {page + 1} / {max_page + 1}  "
                     f"({start + 1}–{end} sur {total})",
                text_color="gray", font=ctk.CTkFont(size=12)
            ).pack(side="left", expand=True)

            ctk.CTkButton(
                pager, text="Suivant →",
                command=lambda: self._tracker_change_page(container, +1),
                state=("normal" if page < max_page else "disabled"),
                width=110, height=30,
                fg_color="gray30", hover_color="gray40"
            ).pack(side="right", padx=(4, 8))

        # Met à jour le compteur de sélection après render
        self._tracker_update_selection_count()

    def _tracker_change_page(self, container, delta):
        if not hasattr(self, "_tracker_page"):
            self._tracker_page = 0
        self._tracker_page += delta
        self._refresh_tracker_list(container)

    def _tracker_update_selection_count(self):
        """Recalcule le nombre de candidatures cochées et met à jour le label."""
        try:
            count = sum(1 for v in (getattr(self, "_tracker_selection", {}) or {}).values()
                        if v.get())
            if hasattr(self, "_tracker_sel_count_label") and \
               self._tracker_sel_count_label.winfo_exists():
                self._tracker_sel_count_label.configure(
                    text=f"{count} sélectionnée(s)",
                    text_color=("#27ae60" if count > 0 else "gray")
                )
        except Exception:
            pass

    def _tracker_toggle_all(self, container):
        """Coche/décoche TOUTES les candidatures correspondant au filtre actif."""
        check = bool(getattr(self, "_tracker_select_all_var",
                             ctk.BooleanVar(value=False)).get())
        candidatures = self.cfg.get("candidatures", [])
        filtre_val = getattr(self, "tracker_filter_var", None)
        filtre_val = filtre_val.get() if filtre_val else "Tous"
        for i, c in enumerate(candidatures):
            if filtre_val != "Tous" and c.get("statut") != filtre_val:
                continue
            v = self._tracker_selection.get(i)
            if v is None:
                v = ctk.BooleanVar()
                self._tracker_selection[i] = v
            v.set(check)
        # Re-render pour que les checkboxes UI reflètent le nouvel état
        self._refresh_tracker_list(container)

    def _tracker_delete_selected(self, container):
        """Supprime toutes les candidatures cochées (avec confirmation)."""
        selected_ids = sorted(
            [k for k, v in (getattr(self, "_tracker_selection", {}) or {}).items()
             if v.get()],
            reverse=True  # supprime en partant de la fin pour ne pas décaler les indices
        )
        if not selected_ids:
            messagebox.showinfo("ℹ️", "Aucune candidature sélectionnée.")
            return
        if not messagebox.askyesno(
            "Supprimer la sélection ?",
            f"Supprimer définitivement {len(selected_ids)} candidature(s) ?\n"
            "Cette action est irréversible."
        ):
            return
        for idx in selected_ids:
            try:
                self.cfg["candidatures"].pop(idx)
            except IndexError:
                pass
        self._tracker_selection.clear()
        if hasattr(self, "_tracker_select_all_var"):
            self._tracker_select_all_var.set(False)
        save_config(self.cfg)
        # Reset à la page 0 pour éviter une page vide après suppression
        self._tracker_page = 0
        self._refresh_tracker_list(container)
        messagebox.showinfo("✅", f"{len(selected_ids)} candidature(s) supprimée(s).")

    def _update_statut(self, idx, val):
        self.cfg["candidatures"][idx]["statut"] = val
        save_config(self.cfg)

    def _delete_candidature(self, idx, container):
        if messagebox.askyesno("Supprimer ?", "Supprimer cette candidature ?"):
            self.cfg["candidatures"].pop(idx)
            save_config(self.cfg)
            self._refresh_tracker_list(container)

    def _send_candidature(self, offre, idx, container):
        """Popup preview → envoyer candidature par mail"""
        email_dest = (offre.get("email") or "").strip()

        win = ctk.CTkToplevel(self)
        win.title("📧 Prévisualisation candidature")
        win.geometry("720x720")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 360
        py = self.winfo_y() + self.winfo_height() // 2 - 360
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win,
            text=f"📧 {offre.get('entreprise','?')} — {offre.get('poste','?')}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 5), padx=20, anchor="w")

        # Destinataire (éditable, persisté)
        dest_frame = ctk.CTkFrame(win, fg_color="transparent")
        dest_frame.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(dest_frame, text="À :", width=60).pack(side="left")
        email_entry = ctk.CTkEntry(
            dest_frame, height=32,
            placeholder_text="email@entreprise.com"
        )
        email_entry.insert(0, email_dest)
        email_entry.pack(side="left", fill="x", expand=True)

        # Auto-détection si source fiable (ex: scraping) → indique la provenance
        if offre.get("email"):
            ctk.CTkLabel(
                dest_frame,
                text="  (auto-détecté)" if offre.get("source") not in ("manuel", None) else "  (mémorisé)",
                text_color="gray", font=ctk.CTkFont(size=11)
            ).pack(side="left", padx=(6, 0))

        def _persist_email(_evt=None):
            v = email_entry.get().strip()
            if v != self.cfg["candidatures"][idx].get("email", ""):
                self.cfg["candidatures"][idx]["email"] = v
                save_config(self.cfg)
        email_entry.bind("<FocusOut>", _persist_email)
        email_entry.bind("<Return>", _persist_email)

        obj_frame = ctk.CTkFrame(win, fg_color="transparent")
        obj_frame.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(obj_frame, text="Objet :", width=60).pack(side="left")
        subject_entry = ctk.CTkEntry(obj_frame, height=32)
        p = self.cfg.get("profil", {})
        subject_entry.insert(0,
            f"Candidature – {offre.get('poste','?')} – {p.get('prenom','')} {p.get('nom','')}")
        subject_entry.pack(side="left", fill="x", expand=True)

        # ── Statut de la lettre ───────────────────────────────
        lettre_status_frame = ctk.CTkFrame(win, fg_color="gray17", corner_radius=8)
        lettre_status_frame.pack(fill="x", padx=20, pady=(4, 6))

        lettre_status_label = ctk.CTkLabel(
            lettre_status_frame, text="", anchor="w",
            font=ctk.CTkFont(size=12)
        )
        lettre_status_label.pack(side="left", padx=10, pady=8)

        def _refresh_lettre_status():
            lettre = (self.cfg["candidatures"][idx].get("lettre") or "").strip()
            if lettre:
                n = len(lettre.split())
                lettre_status_label.configure(
                    text=f"✅ Lettre liée à cette candidature ({n} mots) — sera jointe en PDF",
                    text_color="#27ae60"
                )
            else:
                lettre_status_label.configure(
                    text="⚠️ Aucune lettre liée — clique sur ✏️ pour la rédiger",
                    text_color="#e67e22"
                )

        def _on_lettre_saved(_txt):
            _refresh_lettre_status()

        def _edit_lettre():
            self._open_lettre_window(offre, idx=idx, on_save=_on_lettre_saved)

        ctk.CTkButton(
            lettre_status_frame, text="✏️ Éditer / Générer la lettre",
            command=_edit_lettre,
            fg_color="#6c3483", hover_color="#7d3c98", height=32
        ).pack(side="right", padx=10, pady=6)

        _refresh_lettre_status()

        # ── Corps du mail (court) ─────────────────────────────
        ctk.CTkLabel(
            win,
            text="Corps du mail (court — la lettre et le CV sont en pièces jointes) :"
        ).pack(anchor="w", padx=20)
        body_box = ctk.CTkTextbox(win, height=240, font=ctk.CTkFont(size=12), wrap="word")
        body_box.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        body_box.insert("1.0", "⏳ Génération en cours...")

        def generate():
            try:
                from ai_engine import AIEngine
                engine = AIEngine(config=self.cfg)
                mail = engine.generate_email(offre, self.cfg)
                def update():
                    body_box.delete("1.0", "end")
                    body_box.insert("1.0", mail)
                win.after(0, update)
            except Exception as e:
                import traceback
                err_msg = f"❌ {e}\n{traceback.format_exc()}"
                def show_err(err_msg=err_msg):
                    body_box.delete("1.0", "end")
                    body_box.insert("1.0", err_msg)
                win.after(0, show_err)

        threading.Thread(target=generate, daemon=True).start()

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 15))

        def do_send():
            current_email = email_entry.get().strip()
            if not current_email:
                messagebox.showwarning("⚠️", "Indique un destinataire.", parent=win)
                return
            _persist_email()
            subject = subject_entry.get().strip()
            body = body_box.get("1.0", "end").strip()

            lettre_txt = (self.cfg["candidatures"][idx].get("lettre") or "").strip()
            if not lettre_txt:
                if not messagebox.askyesno(
                    "Aucune lettre",
                    "Tu n'as pas de lettre de motivation liée à cette candidature.\n"
                    "Le mail sera envoyé SANS lettre jointe.\n\nContinuer quand même ?",
                    parent=win
                ):
                    return

            # Préparation des pièces jointes
            attachments = []
            pdf_path = None
            if lettre_txt:
                try:
                    from pdf_generator import generate_lettre_pdf
                    pdf_path = generate_lettre_pdf(
                        lettre_txt,
                        self.cfg.get("profil", {}),
                        offre,
                    )
                    attachments.append(pdf_path)
                except Exception as e:
                    messagebox.showerror(
                        "❌ PDF lettre",
                        f"Impossible de générer le PDF de la lettre :\n{e}",
                        parent=win
                    )
                    return

            cv_path = (self.cfg.get("documents", {}) or {}).get("cv_path", "")
            if cv_path and os.path.exists(cv_path):
                attachments.append(cv_path)

            try:
                from mail_sender import MailSender
                sender = MailSender(self.cfg)
                sender.send(
                    to=current_email, subject=subject, body=body,
                    attachments=attachments,
                )
                self.cfg["candidatures"][idx]["statut"] = "Envoyée"
                self.cfg["candidatures"][idx]["email"] = current_email
                if pdf_path:
                    self.cfg["candidatures"][idx]["lettre_pdf"] = pdf_path
                save_config(self.cfg)
                win.destroy()
                pj_info = (
                    f"\n\nPièces jointes : {len(attachments)} fichier(s)"
                    if attachments else ""
                )
                messagebox.showinfo("✅ Envoyé !", f"Mail envoyé à {current_email}{pj_info}")
                self._refresh_tracker_list(container)
            except Exception as e:
                messagebox.showerror("❌ Erreur envoi", str(e), parent=win)

        ctk.CTkButton(
            btn_row, text="🔄 Régénérer mail",
            command=lambda: threading.Thread(target=generate, daemon=True).start(),
            fg_color="gray30", hover_color="gray40", height=38, width=150
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="📧 Envoyer",
            command=do_send,
            fg_color="#27ae60", hover_color="#2ecc71", height=38, width=120
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="✖ Annuler",
            command=win.destroy,
            fg_color="gray30", hover_color="#e74c3c", height=38, width=100
        ).pack(side="right")

        bring_to_front(win)

    # 🆕 Envoi en masse
    def _send_all_pending(self, container):
        candidatures = self.cfg.get("candidatures", [])
        pending = [(i, c) for i, c in enumerate(candidatures)
                   if c.get("statut") == "À envoyer"]
        if not pending:
            messagebox.showinfo("ℹ️", "Aucune candidature « À envoyer ».")
            return

        missing_email = [c for _, c in pending if not c.get("email")]
        if missing_email:
            messagebox.showwarning(
                "⚠️ Emails manquants",
                f"{len(missing_email)} candidature(s) n'ont pas d'email destinataire.\n"
                f"Elles seront ignorées. Ajoute-les manuellement via 📧."
            )

        sendable = [(i, c) for i, c in pending if c.get("email")]
        if not sendable:
            return

        if not messagebox.askyesno(
            "Confirmer l'envoi",
            f"Envoyer {len(sendable)} candidature(s) en lot ?\n\n"
            f"La génération IA + envoi peut prendre plusieurs minutes."
        ):
            return

        win = ctk.CTkToplevel(self)
        win.title("📧 Envoi en lot")
        win.geometry("580x420")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 290
        py = self.winfo_y() + self.winfo_height() // 2 - 210
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="📧 Envoi en lot des candidatures",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=(20, 10), padx=20, anchor="w")

        log = ctk.CTkTextbox(win, font=ctk.CTkFont(size=11))
        log.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        def append(msg):
            log.insert("end", msg + "\n")
            log.see("end")

        close_btn = ctk.CTkButton(
            win, text="Fermer", command=win.destroy,
            height=38, state="disabled"
        )
        close_btn.pack(pady=(0, 15))

        def task():
            ok, fail = 0, 0
            try:
                from ai_engine import AIEngine
                from mail_sender import MailSender
                engine = AIEngine(config=self.cfg)
                sender = MailSender(self.cfg)
                p = self.cfg.get("profil", {})
                for idx, c in sendable:
                    entreprise = c.get("entreprise", "?")
                    poste = c.get("poste", "?")
                    try:
                        win.after(0, append, f"✍️  {entreprise} — {poste}…")
                        mail = engine.generate_email(c, self.cfg)
                        lettre = engine.generate_cover_letter(c, self.cfg)
                        body = mail + "\n\n────────────────────\n\n" + lettre
                        subject = f"Candidature – {poste} – {p.get('prenom','')} {p.get('nom','')}"
                        sender.send(to=c["email"], subject=subject, body=body)
                        self.cfg["candidatures"][idx]["statut"] = "Envoyée"
                        save_config(self.cfg)
                        ok += 1
                        win.after(0, append, f"   ✅ envoyé à {c['email']}")
                    except Exception as e:
                        fail += 1
                        win.after(0, append, f"   ❌ {str(e)[:120]}")
            except Exception as e:
                win.after(0, append, f"❌ Erreur globale : {e}")
            finally:
                win.after(0, append, f"\n🎯 Terminé : {ok} envoyée(s), {fail} échec(s).")
                win.after(0, lambda: close_btn.configure(state="normal"))
                win.after(0, lambda: self._refresh_tracker_list(container))

        threading.Thread(target=task, daemon=True).start()
        bring_to_front(win)

    def _export_csv(self):
        try:
            import pandas as pd
            df = pd.DataFrame(self.cfg.get("candidatures", []))
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="candidatures.csv"
            )
            if path:
                df.to_csv(path, index=False, encoding="utf-8-sig")
                messagebox.showinfo("✅", f"Export réussi !\n{path}")
        except Exception as e:
            messagebox.showerror("❌ Erreur export", str(e))

    # ══════════════════════════════════════════════════════════
    # 🔁 ROUTINE : recherches automatiques récurrentes
    # ══════════════════════════════════════════════════════════
    def show_routine(self):
        self._set_active("🔁  Routine")
        self._remember_tab("routine")
        self._clear_main()

        # IMPORTANT : setdefault (pas get) sinon les "héritages" depuis
        # la recherche manuelle ne sont jamais persistés dans cfg.
        routine = self.cfg.setdefault("routine", {})
        # Par défaut, on hérite des params de la recherche automatique
        # pour les champs qui n'ont jamais été configurés dans la routine.
        rech = self.cfg.get("recherche", {}) or {}
        if "mots_cles" not in routine:
            routine["mots_cles"] = list(rech.get("mots_cles", []) or [])
        if "localisation" not in routine:
            routine["localisation"] = rech.get("localisation", "Paris")
        if "rayon_km" not in routine:
            routine["rayon_km"] = rech.get("rayon_km", 30)
        if "contrat" not in routine:
            routine["contrat"] = rech.get("contrat", "Tous")

        ctk.CTkLabel(
            self.main, text="🔁 Routine — recherches automatiques",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            self.main,
            text="Active une recherche récurrente en arrière-plan.\n"
                 "Tant que l'app est ouverte, elle se déclenche à la fréquence choisie.",
            text_color="gray", justify="left"
        ).pack(anchor="w", pady=(0, 14))

        # ── Activation ─────────────────────────────────────────
        switch_frame = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=10)
        switch_frame.pack(fill="x", pady=(0, 12))

        self.routine_enabled_var = ctk.BooleanVar(value=routine.get("enabled", False))
        ctk.CTkSwitch(
            switch_frame,
            text="Routine active",
            variable=self.routine_enabled_var,
            command=self._on_routine_toggle,
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=15, pady=12)

        self.routine_next_label = ctk.CTkLabel(
            switch_frame, text=self._routine_next_text(),
            text_color="gray", font=ctk.CTkFont(size=12)
        )
        self.routine_next_label.pack(side="right", padx=15, pady=12)

        # ── Fréquence ──────────────────────────────────────────
        freq_frame = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=10)
        freq_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            freq_frame, text="⏱ Fréquence",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 2))

        freq_row = ctk.CTkFrame(freq_frame, fg_color="transparent")
        freq_row.pack(fill="x", padx=15, pady=(0, 12))

        self.routine_interval_var = ctk.StringVar(
            value=str(routine.get("interval", 6))
        )
        ctk.CTkLabel(freq_row, text="Toutes les").pack(side="left", padx=(0, 6))
        interval_entry = ctk.CTkEntry(
            freq_row, textvariable=self.routine_interval_var,
            width=60, height=30
        )
        interval_entry.pack(side="left", padx=(0, 6))
        interval_entry.bind("<FocusOut>", self._save_routine_silent)
        interval_entry.bind("<Return>", self._save_routine_silent)

        self.routine_unit_var = ctk.StringVar(value=routine.get("unit", "heures"))
        ctk.CTkOptionMenu(
            freq_row, variable=self.routine_unit_var,
            values=["minutes", "heures", "jours"],
            width=110, height=30,
            command=lambda _v: self._save_routine_silent()
        ).pack(side="left")

        # ── Critères de recherche ──────────────────────────────
        crit_frame = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=10)
        crit_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            crit_frame, text="🎯 Critères (indépendants de la recherche manuelle)",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 2))

        row1 = ctk.CTkFrame(crit_frame, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=(4, 4))
        ctk.CTkLabel(row1, text="Mots-clés :", width=90, anchor="w").pack(side="left")
        self.routine_kw_entry = ctk.CTkEntry(row1, height=30)
        self.routine_kw_entry.insert(0, ", ".join(routine.get("mots_cles", [])))
        self.routine_kw_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.routine_kw_entry.bind("<FocusOut>", self._save_routine_silent)
        self.routine_kw_entry.bind("<Return>", self._save_routine_silent)

        row2 = ctk.CTkFrame(crit_frame, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=(4, 4))
        ctk.CTkLabel(row2, text="Lieu :", width=90, anchor="w").pack(side="left")
        self.routine_loc_entry = ctk.CTkEntry(row2, width=200, height=30)
        self.routine_loc_entry.insert(0, routine.get("localisation", "Paris"))
        self.routine_loc_entry.pack(side="left", padx=(5, 15))
        self.routine_loc_entry.bind("<FocusOut>", self._save_routine_silent)
        self.routine_loc_entry.bind("<Return>", self._save_routine_silent)
        ctk.CTkLabel(row2, text="Rayon (km) :", width=90, anchor="w").pack(side="left")
        self.routine_km_entry = ctk.CTkEntry(row2, width=70, height=30)
        self.routine_km_entry.insert(0, str(routine.get("rayon_km", 30)))
        self.routine_km_entry.pack(side="left", padx=(5, 0))
        self.routine_km_entry.bind("<FocusOut>", self._save_routine_silent)
        self.routine_km_entry.bind("<Return>", self._save_routine_silent)

        row3 = ctk.CTkFrame(crit_frame, fg_color="transparent")
        row3.pack(fill="x", padx=15, pady=(4, 12))
        ctk.CTkLabel(row3, text="Contrat :", width=90, anchor="w").pack(side="left")
        self.routine_contrat_var = ctk.StringVar(
            value=routine.get("contrat", "Tous")
        )
        ctk.CTkOptionMenu(
            row3, variable=self.routine_contrat_var,
            values=["Tous", "CDI", "CDD", "Stage", "Alternance", "Freelance"],
            width=140, height=30,
            command=lambda _v: self._save_routine_silent()
        ).pack(side="left", padx=(5, 0))

        # ── Options d'ajout automatique ───────────────────────
        opt_frame = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=10)
        opt_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            opt_frame, text="🤖 Automatisation",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 2))

        self.routine_auto_add_var = ctk.BooleanVar(
            value=routine.get("auto_add", False)
        )
        ctk.CTkCheckBox(
            opt_frame,
            text="Ajouter automatiquement les nouvelles offres aux candidatures",
            variable=self.routine_auto_add_var,
            command=self._save_routine_silent
        ).pack(anchor="w", padx=15, pady=(4, 10))

        # ── Historique ────────────────────────────────────────
        hist_frame = ctk.CTkFrame(self.main, fg_color="gray17", corner_radius=10)
        hist_frame.pack(fill="both", expand=True, pady=(0, 12))

        ctk.CTkLabel(
            hist_frame, text="📜 Dernières exécutions",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 4))

        hist_box = ctk.CTkScrollableFrame(hist_frame, height=130, fg_color="transparent")
        hist_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        hist = routine.get("history", []) or []
        if not hist:
            ctk.CTkLabel(
                hist_box, text="Aucune exécution pour l'instant.",
                text_color="gray"
            ).pack(anchor="w", padx=5, pady=5)
        for entry in hist[-20:][::-1]:
            ctk.CTkLabel(
                hist_box,
                text=f"• {entry.get('ts','?')} — {entry.get('found',0)} offre(s), "
                     f"{entry.get('added',0)} ajoutée(s)",
                text_color="gray", font=ctk.CTkFont(size=11)
            ).pack(anchor="w", padx=5, pady=1)

        # ── Boutons ────────────────────────────────────────────
        # Petit indicateur d'auto-save : la routine se persiste en
        # silence sur changement de champ ; le bouton ci-dessous est
        # juste un confirmateur explicite (popup de validation).
        info_row = ctk.CTkFrame(self.main, fg_color="transparent")
        info_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            info_row,
            text="✓ Les modifications sont sauvegardées automatiquement",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).pack(side="left")
        self.routine_save_status = ctk.CTkLabel(
            info_row, text="", text_color="#27ae60",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.routine_save_status.pack(side="right")

        btn_row = ctk.CTkFrame(self.main, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            btn_row, text="💾 Sauvegarder",
            command=self._save_routine, height=42,
            fg_color="#27ae60", hover_color="#2ecc71",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="▶️ Lancer maintenant",
            command=lambda: threading.Thread(
                target=lambda: self._run_routine_search(manual=True),
                daemon=True
            ).start(),
            height=42, fg_color="#6c3483", hover_color="#7d3c98",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(5, 0))

    def _routine_next_text(self):
        nxt = self.cfg.get("routine", {}).get("next_run", 0)
        if not nxt:
            return "Jamais exécutée"
        import time as _t
        remain = int(nxt - _t.time())
        if remain <= 0:
            return "Prochaine exécution : imminente"
        if remain < 60:
            return f"Prochaine exécution dans {remain}s"
        if remain < 3600:
            return f"Prochaine exécution dans {remain // 60} min"
        return f"Prochaine exécution dans {remain // 3600}h{(remain % 3600)//60:02d}"

    def _on_routine_toggle(self):
        """Sauvegarde immédiate de l'état activé/désactivé de la routine,
        pour que l'utilisateur n'ait pas besoin de cliquer sur Sauvegarder
        avant de changer de section."""
        routine = self.cfg.setdefault("routine", {})
        routine["enabled"] = bool(self.routine_enabled_var.get())
        # Si on active la routine et qu'aucun prochain run n'est planifié,
        # on en programme un.
        if routine["enabled"] and not routine.get("next_run"):
            routine["next_run"] = self._routine_compute_next()
        save_config(self.cfg)
        # Refresh du label "prochaine exécution" (si la page est encore visible)
        try:
            if hasattr(self, "routine_next_label") and \
               self.routine_next_label.winfo_exists():
                self.routine_next_label.configure(text=self._routine_next_text())
        except Exception:
            pass

    def _save_routine_silent(self, *_args):
        """Persistance silencieuse : appelée par auto-save sur changement
        de n'importe quel champ. Pas de popup, pas de re-render UI
        (sinon le focus saute hors du widget en cours d'édition)."""
        # Si la page de routine n'est plus active, on ignore (les widgets
        # ont été détruits par _clear_main).
        if not (hasattr(self, "routine_kw_entry")
                and self.routine_kw_entry.winfo_exists()):
            return
        try:
            interval = int(self.routine_interval_var.get() or "1")
            interval = max(1, interval)
        except ValueError:
            interval = 6
        kw_raw = self.routine_kw_entry.get().strip()
        routine = self.cfg.setdefault("routine", {})
        routine["enabled"]      = bool(self.routine_enabled_var.get())
        routine["interval"]     = interval
        routine["unit"]         = self.routine_unit_var.get()
        routine["mots_cles"]    = [k.strip() for k in kw_raw.split(",") if k.strip()]
        routine["localisation"] = self.routine_loc_entry.get().strip()
        try:
            routine["rayon_km"] = int(self.routine_km_entry.get().strip() or "30")
        except ValueError:
            routine["rayon_km"] = 30
        routine["contrat"]  = self.routine_contrat_var.get()
        routine["auto_add"] = bool(self.routine_auto_add_var.get())
        routine["next_run"] = self._routine_compute_next()
        save_config(self.cfg)
        # Refresh du label "prochaine exécution" sans recréer la page
        try:
            if hasattr(self, "routine_next_label") and \
               self.routine_next_label.winfo_exists():
                self.routine_next_label.configure(text=self._routine_next_text())
            if hasattr(self, "routine_save_status") and \
               self.routine_save_status.winfo_exists():
                w = self.routine_save_status
                w.configure(text="✓ Sauvegardé", text_color="#27ae60")
                # Capture la référence du widget courant pour éviter
                # d'effacer un nouveau widget si la page est recréée < 2s.
                self.after(2000, lambda w=w: (
                    w.configure(text="") if w.winfo_exists() else None
                ))
        except Exception:
            pass

    def _save_routine(self):
        """Sauvegarde explicite déclenchée par le bouton (popup confirm)."""
        self._save_routine_silent()
        messagebox.showinfo("✅", "Routine sauvegardée.")
        self.show_routine()

    def _routine_compute_next(self):
        import time as _t
        routine = self.cfg.get("routine", {})
        if not routine.get("enabled"):
            return 0
        interval = max(1, int(routine.get("interval", 6) or 1))
        unit = routine.get("unit", "heures")
        seconds = interval * {"minutes": 60, "heures": 3600, "jours": 86400}.get(unit, 3600)
        return _t.time() + seconds

    def _start_routine_scheduler(self):
        """Thread daemon qui vérifie toutes les 30s si la routine doit tourner."""
        import time as _t

        def loop():
            while True:
                try:
                    routine = self.cfg.get("routine", {})
                    if routine.get("enabled"):
                        if not routine.get("next_run"):
                            self.cfg.setdefault("routine", {})["next_run"] = self._routine_compute_next()
                            save_config(self.cfg)
                        if routine.get("next_run", 0) <= _t.time():
                            self._run_routine_search(manual=False)
                except Exception as e:
                    print(f"[routine] erreur : {e}")
                _t.sleep(30)

        threading.Thread(target=loop, daemon=True).start()

    def _run_routine_search(self, manual=False):
        """Exécute une recherche routine avec les critères sauvegardés."""
        import time as _t
        routine = self.cfg.get("routine", {})
        if not manual and not routine.get("enabled"):
            return

        # Copie cfg avec critères routine
        cfg_run = dict(self.cfg)
        cfg_run["recherche"] = {
            "mots_cles":   routine.get("mots_cles", []) or self.cfg.get("recherche", {}).get("mots_cles", []),
            "localisation": routine.get("localisation", "") or self.cfg.get("recherche", {}).get("localisation", ""),
            "rayon_km":    routine.get("rayon_km", 30),
            "contrat":     routine.get("contrat", "Tous"),
        }

        try:
            from scraper import OffreScraper
            scraper = OffreScraper(cfg_run)
            offres = scraper.search_all(progress_cb=lambda m: None)
        except Exception as e:
            print(f"[routine] scrape error : {e}")
            offres = []

        # Dédup : écarte les offres déjà en candidatures
        already = set()
        for c in self.cfg.get("candidatures", []):
            already.add((c.get("entreprise", ""), c.get("poste", ""), c.get("url", "")))
        new_offres = [
            o for o in offres
            if (o.get("entreprise", ""), o.get("titre", ""), o.get("url", "")) not in already
        ]

        added = 0
        if routine.get("auto_add"):
            import datetime as _dt
            for o in new_offres:
                self.cfg.setdefault("candidatures", []).append({
                    "entreprise":  o.get("entreprise", ""),
                    "poste":       o.get("titre", ""),
                    "email":       o.get("email", ""),
                    "lieu":        o.get("lieu", ""),
                    "contrat":     o.get("contrat", ""),
                    "url":         o.get("url", ""),
                    "source":      o.get("source", ""),
                    "description": o.get("description", ""),
                    "statut":      "À envoyer",
                    "date":        _dt.date.today().isoformat(),
                    "notes":       "(via routine)",
                })
                added += 1

        # Enregistre historique + prochain run
        hist = routine.setdefault("history", [])
        hist.append({
            "ts":    _t.strftime("%Y-%m-%d %H:%M", _t.localtime()),
            "found": len(new_offres),
            "added": added,
        })
        if len(hist) > 50:
            del hist[:-50]
        routine["next_run"] = self._routine_compute_next()
        self.cfg["routine"] = routine
        save_config(self.cfg)

        # Mise à jour UI si onglet routine ouvert
        if hasattr(self, "routine_next_label") and self.routine_next_label.winfo_exists():
            self.after(0, lambda: self.routine_next_label.configure(text=self._routine_next_text()))

        if manual:
            def _report():
                messagebox.showinfo(
                    "🔁 Routine",
                    f"{len(new_offres)} nouvelle(s) offre(s) trouvée(s)\n"
                    f"{added} ajoutée(s) automatiquement"
                )
            self.after(0, _report)

    # ══════════════════════════════════════════════════════════
    # 🖱️ Scroll helper : isole le wheel d'un textbox du parent
    # ══════════════════════════════════════════════════════════
    def _isolate_textbox_scroll(self, textbox):
        """Empêche un CTkTextbox de propager les événements de molette
        au CTkScrollableFrame parent : quand le curseur est sur le
        textbox, seul son contenu défile."""
        inner = getattr(textbox, "_textbox", None)
        if inner is None:
            return

        def _on_wheel(event):
            try:
                # macOS : delta petit (souvent 1)
                # Windows : delta = ±120 par cran
                # Linux : pas de delta, event.num = 4 (haut) / 5 (bas)
                if getattr(event, "num", None) == 4:
                    inner.yview_scroll(-3, "units")
                elif getattr(event, "num", None) == 5:
                    inner.yview_scroll(3, "units")
                elif getattr(event, "delta", 0):
                    direction = -1 if event.delta > 0 else 1
                    inner.yview_scroll(direction * 3, "units")
            except Exception:
                pass
            return "break"

        for w in (textbox, inner):
            try:
                w.bind("<MouseWheel>", _on_wheel, add="+")
                w.bind("<Button-4>", _on_wheel, add="+")
                w.bind("<Button-5>", _on_wheel, add="+")
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════
    # 👤 PROFIL (simplifié — retrait des redondances)
    # ══════════════════════════════════════════════════════════
    def show_profile(self):
        self._set_active("👤  Mes infos")
        self._remember_tab("profile")
        self._clear_main()

        ctk.CTkLabel(
            self.main, text="📋 Mes infos",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            self.main,
            text="Identité, expérience, CV et lettre type — tout est injecté dans les mails/lettres générés par l'IA.",
            text_color="gray", font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(0, 10))

        form = ctk.CTkScrollableFrame(self.main)
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(1, weight=1)

        p = self.cfg.setdefault("profil", {})
        exp = self.cfg.setdefault("experience", {})

        # Section identité
        ctk.CTkLabel(form, text="👤 Identité",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=0, column=0, columnspan=2, sticky="w",
                            padx=5, pady=(5, 8))

        fields = [
            ("Prénom",           "prenom",          False),
            ("Nom",              "nom",             False),
            ("Téléphone",        "telephone",       False),
            ("LinkedIn (URL)",   "linkedin",        False),
            ("Poste recherché",  "poste_recherche", False),
        ]
        self.profile_entries = {}
        for i, (label, key, _) in enumerate(fields, start=1):
            ctk.CTkLabel(form, text=label).grid(
                row=i, column=0, sticky="w", padx=(10, 15), pady=5)
            e = ctk.CTkEntry(form, height=36)
            e.insert(0, p.get(key, ""))
            e.grid(row=i, column=1, sticky="ew", pady=5, padx=(0, 5))
            self.profile_entries[key] = e

        # Section expérience
        row = len(fields) + 2
        ctk.CTkLabel(form, text="💼 Expérience",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=row, column=0, columnspan=2, sticky="w",
                            padx=5, pady=(15, 8))

        ctk.CTkLabel(form, text="Années").grid(
            row=row+1, column=0, sticky="w", padx=(10, 15), pady=5)
        self.exp_annees_entry = ctk.CTkEntry(form, height=36)
        self.exp_annees_entry.insert(0, str(exp.get("annees", 0)))
        self.exp_annees_entry.grid(row=row+1, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(form, text="Compétences\n(virgules)").grid(
            row=row+2, column=0, sticky="nw", padx=(10, 15), pady=5)
        self.exp_comp_entry = ctk.CTkEntry(form, height=36)
        self.exp_comp_entry.insert(0, ", ".join(exp.get("competences", [])))
        self.exp_comp_entry.grid(row=row+2, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(form, text="Langues\n(virgules)").grid(
            row=row+3, column=0, sticky="nw", padx=(10, 15), pady=5)
        self.exp_lang_entry = ctk.CTkEntry(form, height=36)
        self.exp_lang_entry.insert(0, ", ".join(exp.get("langues", [])))
        self.exp_lang_entry.grid(row=row+3, column=1, sticky="ew", pady=5, padx=(0, 5))

        # Section CV
        row += 4
        docs = self.cfg.setdefault("documents", {})
        ctk.CTkLabel(form, text="📄 CV",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=row, column=0, columnspan=2, sticky="w",
                            padx=5, pady=(15, 8))

        cv_row = ctk.CTkFrame(form, fg_color="transparent")
        cv_row.grid(row=row+1, column=0, columnspan=2, sticky="ew", pady=6, padx=(5, 5))
        cv_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(cv_row, text="Fichier :").grid(row=0, column=0, sticky="w", padx=(5, 15))
        cv_path = docs.get("cv_path", "")
        self.cv_file_label = ctk.CTkLabel(
            cv_row,
            text=(os.path.basename(cv_path) if cv_path and os.path.exists(cv_path)
                  else "Aucun CV importé"),
            text_color=("#27ae60" if cv_path and os.path.exists(cv_path) else "gray"),
            anchor="w",
        )
        self.cv_file_label.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ctk.CTkButton(
            cv_row,
            text=("🔁 Remplacer" if cv_path and os.path.exists(cv_path) else "📥 Importer CV"),
            width=140, command=self._import_cv
        ).grid(row=0, column=2, padx=(0, 5))
        self.cv_replace_btn = None

        cv_actions = ctk.CTkFrame(form, fg_color="transparent")
        cv_actions.grid(row=row+2, column=0, columnspan=2, sticky="ew", pady=(0, 4), padx=(5, 5))
        ctk.CTkButton(
            cv_actions, text="🪄 Remplir le profil depuis le CV",
            command=self._autofill_from_cv, height=32,
            fg_color="#6c3483", hover_color="#7d3c98"
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            cv_actions, text="🧪 Analyser la compatibilité ATS",
            command=self._analyze_ats, height=32,
            fg_color="#2980b9", hover_color="#3498db"
        ).pack(side="left", padx=(0, 6))

        # Section Lettre de motivation (fichier)
        row += 3
        ctk.CTkLabel(form, text="💌 Lettre de motivation (fichier)",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=row, column=0, columnspan=2, sticky="w",
                            padx=5, pady=(15, 8))
        lm_row = ctk.CTkFrame(form, fg_color="transparent")
        lm_row.grid(row=row+1, column=0, columnspan=2, sticky="ew", pady=6, padx=(5, 5))
        lm_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(lm_row, text="Fichier :").grid(row=0, column=0, sticky="w", padx=(5, 15))
        lm_path = docs.get("lettre_path", "")
        self.lm_file_label = ctk.CTkLabel(
            lm_row,
            text=(os.path.basename(lm_path) if lm_path and os.path.exists(lm_path)
                  else "Aucune lettre importée"),
            text_color=("#27ae60" if lm_path and os.path.exists(lm_path) else "gray"),
            anchor="w",
        )
        self.lm_file_label.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkButton(
            lm_row,
            text=("🔁 Remplacer" if lm_path and os.path.exists(lm_path) else "📥 Importer lettre"),
            width=140, command=self._import_lettre
        ).grid(row=0, column=2, padx=(0, 5))

        # Lettre type (texte brut — utilisé si aucun fichier)
        row += 2
        lettre_header = ctk.CTkFrame(form, fg_color="transparent")
        lettre_header.grid(row=row, column=0, columnspan=2,
                           sticky="ew", padx=5, pady=(15, 8))
        lettre_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            lettre_header, text="✍️ Lettre type (texte)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            lettre_header, text="🤖 Générer lettre IA",
            command=lambda: self._open_lettre_window({
                "titre": self.cfg.get("profil", {}).get("poste_recherche", ""),
                "poste": self.cfg.get("profil", {}).get("poste_recherche", ""),
                "entreprise": "",
                "description": ""
            }),
            height=32, width=180,
            fg_color="#6c3483", hover_color="#7d3c98"
        ).grid(row=0, column=1, sticky="e", padx=(10, 0))

        ctk.CTkLabel(form, text="Base texte\n(optionnel)").grid(
            row=row+1, column=0, sticky="nw", padx=(10, 15), pady=6)
        self.lettre_box = ctk.CTkTextbox(form, height=160, wrap="word")
        self.lettre_box.grid(row=row+1, column=1, sticky="ew", pady=6, padx=(0, 5))
        self.lettre_box.insert("1.0", p.get("lettre_type", ""))
        self._isolate_textbox_scroll(self.lettre_box)

        # Note info
        ctk.CTkLabel(
            self.main,
            text="💡 Email & ville viennent de ⚙️ Paramètres (Gmail) et de 🔍 Recherche (localisation).",
            text_color="gray", font=ctk.CTkFont(size=11), justify="left"
        ).pack(anchor="w", pady=(8, 0))

        btn_row = ctk.CTkFrame(self.main, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            btn_row, text="💾 Sauvegarder le profil",
            command=self.save_profile, height=42,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", expand=True, fill="x")

    def _save_profile_silent(self):
        """Persiste le profil sans popup ni rebuild (utilisé par auto-save
        sur changement de page). Renvoie l'ancien et le nouveau poste
        recherché, pour que `save_profile` puisse déclencher la regen
        des mots-clés si besoin."""
        # Si la page n'est pas active, les widgets n'existent plus
        if not (hasattr(self, "profile_entries") and self.profile_entries):
            return None, None
        try:
            if not list(self.profile_entries.values())[0].winfo_exists():
                return None, None
        except Exception:
            return None, None

        p = self.cfg.setdefault("profil", {})
        old_poste = p.get("poste_recherche", "")
        for key, entry in self.profile_entries.items():
            try:
                p[key] = entry.get().strip()
            except Exception:
                pass
        try:
            if hasattr(self, "lettre_box") and self.lettre_box.winfo_exists():
                p["lettre_type"] = self.lettre_box.get("1.0", "end").strip()
        except Exception:
            pass

        exp = self.cfg.setdefault("experience", {})
        try:
            exp["annees"] = int(self.exp_annees_entry.get().strip() or 0)
        except (ValueError, AttributeError, Exception):
            exp.setdefault("annees", 0)
        try:
            exp["competences"] = [
                s.strip() for s in self.exp_comp_entry.get().split(",") if s.strip()
            ]
        except Exception:
            pass
        try:
            exp["langues"] = [
                s.strip() for s in self.exp_lang_entry.get().split(",") if s.strip()
            ]
        except Exception:
            pass

        save_config(self.cfg)
        return old_poste, p.get("poste_recherche", "")

    def save_profile(self):
        old_poste, new_poste = self._save_profile_silent()
        messagebox.showinfo("✅", "Profil sauvegardé !")

        # Si le poste recherché a changé → régénère les mots-clés
        # de recherche en arrière-plan (via l'IA configurée).
        if new_poste and new_poste != old_poste:
            threading.Thread(
                target=self._regen_keywords_from_role_async,
                args=(new_poste,), daemon=True
            ).start()

    def _regen_keywords_from_role_async(self, poste):
        kws = self._suggest_keywords_for_role(poste)
        if not kws:
            return
        self.cfg.setdefault("recherche", {})["mots_cles"] = kws
        save_config(self.cfg)
        self.after(0, self._maybe_refresh_search_keywords)

    def _suggest_keywords_for_role(self, poste):
        """Renvoie 6-10 mots-clés de recherche pertinents pour le poste,
        générés via l'IA configurée. Fallback : [poste] si l'IA échoue."""
        poste = (poste or "").strip()
        if not poste:
            return []
        prompt = (
            f"Pour une recherche d'emploi sur le poste « {poste} », "
            f"propose 6 à 10 mots-clés courts et pertinents en français "
            f"pour des sites comme Indeed, LinkedIn ou France Travail. "
            f"Inclus des synonymes du titre, des outils ou technologies "
            f"associés et des variantes courantes du métier.\n"
            f"Réponds UNIQUEMENT par les mots-clés séparés par des "
            f"virgules — pas de phrase d'introduction, pas de "
            f"numérotation, pas de guillemets."
        )
        try:
            from ai_engine import AIEngine
            raw = AIEngine(self.cfg).complete(prompt)
        except Exception:
            return [poste]
        keywords = []
        for k in (raw or "").replace("\n", ",").split(","):
            k = k.strip().strip('"').strip("'").strip(".").strip("-").strip()
            if k and 1 < len(k) <= 50 and k.lower() not in ("etc", "etc."):
                keywords.append(k)
        # Dédup tout en gardant l'ordre
        seen = set()
        unique = []
        for k in keywords:
            kl = k.lower()
            if kl in seen:
                continue
            seen.add(kl)
            unique.append(k)
        return unique[:10] or [poste]

    def _maybe_refresh_search_keywords(self):
        """Si la barre de recherche auto est visible, recharge le champ
        mots-clés depuis la config (utilisé après regen IA)."""
        entry = getattr(self, "search_kw_entry", None)
        if entry is None:
            return
        try:
            if not entry.winfo_exists():
                return
        except Exception:
            return
        kws = self.cfg.get("recherche", {}).get("mots_cles", []) or []
        try:
            entry.delete(0, "end")
            entry.insert(0, ", ".join(kws))
        except Exception:
            pass

    # ── CV & Lettre ──────────────────────────────────────────
    def _import_cv(self):
        path = filedialog.askopenfilename(
            title="Sélectionne ton CV",
            filetypes=[("Documents", "*.pdf *.docx *.doc *.txt"),
                       ("PDF", "*.pdf"), ("Word", "*.docx *.doc"), ("Texte", "*.txt")]
        )
        if not path:
            return
        try:
            from cv_parser import extract_text, ats_score
        except Exception as e:
            messagebox.showerror("Erreur", f"Module cv_parser introuvable : {e}")
            return

        text = extract_text(path) or ""
        if not text:
            if not messagebox.askyesno(
                "⚠️ CV non lisible",
                "Impossible d'extraire du texte de ce CV.\n\n"
                "C'est probablement un CV-image (scan ou PDF exporté depuis Canva comme image).\n"
                "Les ATS ne pourront PAS le lire non plus.\n\n"
                "L'importer quand même ?"
            ):
                return

        self.cfg.setdefault("documents", {})["cv_path"] = path
        self.cfg["documents"]["cv_text"] = text[:20000]
        save_config(self.cfg)

        self.cv_file_label.configure(
            text=os.path.basename(path), text_color="#27ae60"
        )

        # Auto-analyse ATS immédiate
        if text:
            report = ats_score(path, text=text)
            self._show_ats_report(report, auto=True)

    def _import_lettre(self):
        path = filedialog.askopenfilename(
            title="Sélectionne ta lettre de motivation",
            filetypes=[("Documents", "*.pdf *.docx *.doc *.txt"),
                       ("PDF", "*.pdf"), ("Word", "*.docx *.doc"), ("Texte", "*.txt")]
        )
        if not path:
            return
        try:
            from cv_parser import extract_text
        except Exception as e:
            messagebox.showerror("Erreur", f"Module cv_parser introuvable : {e}")
            return
        text = extract_text(path) or ""
        self.cfg.setdefault("documents", {})["lettre_path"] = path
        self.cfg["documents"]["lettre_text"] = text[:10000]
        save_config(self.cfg)
        self.lm_file_label.configure(
            text=os.path.basename(path), text_color="#27ae60"
        )
        messagebox.showinfo("✅", f"Lettre importée : {os.path.basename(path)}")

    def _autofill_from_cv(self):
        docs = self.cfg.get("documents", {})
        text = docs.get("cv_text", "")
        if not text:
            messagebox.showwarning("⚠️", "Importe d'abord un CV dans la section CV.")
            return
        try:
            from cv_parser import extract_profile_info
        except Exception as e:
            messagebox.showerror("Erreur", f"Module cv_parser introuvable : {e}")
            return
        # Passe config=self.cfg pour que l'IA (Ollama/OpenAI/Claude) soit utilisée
        info = extract_profile_info(text, config=self.cfg)
        if not info:
            messagebox.showinfo(
                "ℹ️",
                "Aucune info détectée automatiquement.\n\n"
                "Astuce : vérifie que Ollama est bien installé (⚙️ Paramètres → IA),\n"
                "l'analyse est beaucoup plus précise avec l'IA activée."
            )
            return

        # Remplir UI (l'utilisateur peut encore corriger)
        for key in ("prenom", "nom", "telephone", "linkedin"):
            if key in info and key in self.profile_entries:
                self.profile_entries[key].delete(0, "end")
                self.profile_entries[key].insert(0, info[key])

        if "annees" in info:
            self.exp_annees_entry.delete(0, "end")
            self.exp_annees_entry.insert(0, str(info["annees"]))
        if "competences" in info:
            self.exp_comp_entry.delete(0, "end")
            self.exp_comp_entry.insert(0, ", ".join(info["competences"]))
        if "langues" in info:
            self.exp_lang_entry.delete(0, "end")
            self.exp_lang_entry.insert(0, ", ".join(info["langues"]))

        # Email → on l'enregistre côté Gmail (info du CV ≠ forcément mail d'envoi)
        detected = ", ".join(f"{k}={v}" for k, v in info.items() if k not in ("competences", "langues"))
        messagebox.showinfo(
            "🪄 Profil auto-rempli",
            f"Infos détectées :\n\n{detected}\n\n"
            f"Compétences : {len(info.get('competences', []))}\n"
            f"Langues : {len(info.get('langues', []))}\n\n"
            "Vérifie et corrige si besoin, puis clique sur 💾 Sauvegarder."
        )

    def _analyze_ats(self):
        docs = self.cfg.get("documents", {})
        path = docs.get("cv_path", "")
        text = docs.get("cv_text", "")
        if not path or not os.path.exists(path):
            messagebox.showwarning("⚠️", "Importe d'abord un CV.")
            return
        try:
            from cv_parser import ats_score
        except Exception as e:
            messagebox.showerror("Erreur", f"Module cv_parser introuvable : {e}")
            return
        report = ats_score(path, text=text)
        self._show_ats_report(report, auto=False)

    def _show_ats_report(self, report, auto=False):
        win = ctk.CTkToplevel(self)
        win.title("🧪 Analyse ATS")
        win.geometry("640x620")
        bring_to_front(win)

        ctk.CTkLabel(
            win,
            text=("🧪 Analyse ATS — Importé automatiquement" if auto else "🧪 Analyse ATS"),
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(16, 4), padx=20, anchor="w")

        score = report["score"]
        color = "#27ae60" if score >= 80 else ("#f39c12" if score >= 60 else
                                               "#e67e22" if score >= 40 else "#e74c3c")
        ctk.CTkLabel(
            win, text=report["verdict"],
            font=ctk.CTkFont(size=15, weight="bold"), text_color=color
        ).pack(padx=20, anchor="w")

        ctk.CTkLabel(
            win, text="À quoi sert une analyse ATS ?",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(padx=20, pady=(10, 2), anchor="w")
        ctk.CTkLabel(
            win, text=report["explanation"],
            text_color="gray", wraplength=600, justify="left",
            font=ctk.CTkFont(size=11)
        ).pack(padx=20, anchor="w")

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=15, pady=(10, 10))

        if report["passed"]:
            ctk.CTkLabel(
                scroll, text="Points forts",
                font=ctk.CTkFont(size=13, weight="bold"), text_color="#27ae60"
            ).pack(anchor="w", pady=(5, 4))
            for icon, msg, _ in report["passed"]:
                ctk.CTkLabel(
                    scroll, text=f"{icon}  {msg}",
                    wraplength=560, justify="left", anchor="w"
                ).pack(anchor="w", padx=10, pady=1)

        if report["issues"]:
            ctk.CTkLabel(
                scroll, text="Ce que ça change pour toi si tu n'améliores pas",
                font=ctk.CTkFont(size=13, weight="bold"), text_color="#e74c3c"
            ).pack(anchor="w", pady=(12, 4))
            for icon, msg, tip in report["issues"]:
                ctk.CTkLabel(
                    scroll, text=f"{icon}  {msg}",
                    wraplength=560, justify="left", anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold")
                ).pack(anchor="w", padx=10, pady=(6, 1))
                if tip:
                    ctk.CTkLabel(
                        scroll, text=f"       → {tip}",
                        wraplength=540, justify="left", anchor="w",
                        text_color="gray"
                    ).pack(anchor="w", padx=10)

        ctk.CTkButton(win, text="Fermer", command=win.destroy).pack(pady=(0, 15))

    # ══════════════════════════════════════════════════════════
    # ⚙️ PARAMÈTRES
    # ══════════════════════════════════════════════════════════
    def show_settings(self):
        self._set_active("⚙️  Paramètres")
        self._remember_tab("settings")
        self._clear_main()

        ctk.CTkLabel(
            self.main, text="⚙️ Paramètres",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", pady=(0, 10))

        scroll = ctk.CTkScrollableFrame(self.main)
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(1, weight=1)

        api = self.cfg.setdefault("api", {})
        rech = self.cfg.setdefault("recherche", {})

        # ── Section IA ─────────────────────────────────────────
        ctk.CTkLabel(
            scroll, text="🤖 Intelligence Artificielle",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(15, 5))

        ctk.CTkLabel(
            scroll,
            text="Par défaut : Ollama local (gratuit). Renseigne une clé pour OpenAI/Claude si tu veux plus rapide/qualitatif.",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 6))

        ctk.CTkLabel(scroll, text="Moteur IA").grid(
            row=2, column=0, sticky="w", padx=(10, 15), pady=5)

        ai_engines = ["ollama", "openai", "claude", "template"]
        current_engine = api.get("ai_engine", "ollama")
        self.ai_engine_var = ctk.StringVar(value=current_engine)
        ctk.CTkOptionMenu(
            scroll, variable=self.ai_engine_var,
            values=ai_engines, width=200, height=36
        ).grid(row=2, column=1, sticky="w", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Modèle Ollama").grid(
            row=3, column=0, sticky="w", padx=(10, 15), pady=5)
        self.ollama_entry = ctk.CTkEntry(scroll, height=36)
        self.ollama_entry.insert(0, api.get("ollama_model", "gemma2:2b"))
        self.ollama_entry.grid(row=3, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Clé API OpenAI (optionnel)").grid(
            row=4, column=0, sticky="w", padx=(10, 15), pady=5)
        self.openai_entry = ctk.CTkEntry(scroll, height=36, show="*")
        self.openai_entry.insert(0, api.get("openai_key", ""))
        self.openai_entry.grid(row=4, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Clé API Anthropic (optionnel)").grid(
            row=5, column=0, sticky="w", padx=(10, 15), pady=5)
        self.anthropic_entry = ctk.CTkEntry(scroll, height=36, show="*")
        self.anthropic_entry.insert(0, api.get("anthropic_key", ""))
        self.anthropic_entry.grid(row=5, column=1, sticky="ew", pady=5, padx=(0, 5))

        # Boutons IA
        ai_btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        ai_btn_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 2))

        ctk.CTkButton(
            ai_btn_frame, text="🧪 Tester la connexion IA",
            command=self._test_ai_connection,
            height=34, width=200,
            fg_color="gray25", hover_color="gray35"
        ).pack(side="left", padx=(0, 6))

        # 🆕 Bouton magique Install Ollama
        ctk.CTkButton(
            ai_btn_frame, text="🪄 Installer & connecter Ollama",
            command=self._magic_install_ollama,
            height=34, width=240,
            fg_color="#6c3483", hover_color="#7d3c98"
        ).pack(side="left")

        self.ai_test_label = ctk.CTkLabel(scroll, text="", text_color="gray")
        self.ai_test_label.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        # ── Section Gmail ──────────────────────────────────────
        ctk.CTkLabel(
            scroll, text="📧 Gmail",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))

        ctk.CTkLabel(scroll, text="Adresse Gmail").grid(
            row=9, column=0, sticky="w", padx=(10, 15), pady=5)
        self.gmail_user_entry = ctk.CTkEntry(scroll, height=36,
                                             placeholder_text="ton.adresse@gmail.com")
        self.gmail_user_entry.insert(0, api.get("gmail_user", ""))
        self.gmail_user_entry.grid(row=9, column=1, sticky="ew", pady=5, padx=(0, 5))

        # Mot de passe avec bouton info
        pwd_lbl_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        pwd_lbl_frame.grid(row=10, column=0, sticky="w", padx=(10, 15), pady=5)
        ctk.CTkLabel(pwd_lbl_frame, text="Mot de passe app").pack(side="left")
        ctk.CTkButton(
            pwd_lbl_frame, text="ⓘ", width=24, height=24,
            corner_radius=12, fg_color="gray30", hover_color="#2980b9",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._show_gmail_info
        ).pack(side="left", padx=(6, 0))

        self.gmail_pwd_entry = ctk.CTkEntry(scroll, height=36, show="*",
                                            placeholder_text="abcd efgh ijkl mnop")
        self.gmail_pwd_entry.insert(0, api.get("gmail_password", ""))
        self.gmail_pwd_entry.grid(row=10, column=1, sticky="ew", pady=5, padx=(0, 5))

        # ── Section France Travail ─────────────────────────────
        ctk.CTkLabel(
            scroll, text="🏢 API France Travail (gratuit)",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=11, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))

        ctk.CTkLabel(scroll, text="Client ID").grid(
            row=12, column=0, sticky="w", padx=(10, 15), pady=5)
        self.ft_id_entry = ctk.CTkEntry(scroll, height=36)
        self.ft_id_entry.insert(0, api.get("ft_client_id", ""))
        self.ft_id_entry.grid(row=12, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Client Secret").grid(
            row=13, column=0, sticky="w", padx=(10, 15), pady=5)
        self.ft_secret_entry = ctk.CTkEntry(scroll, height=36, show="*")
        self.ft_secret_entry.insert(0, api.get("ft_client_secret", ""))
        self.ft_secret_entry.grid(row=13, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkButton(
            scroll, text="🔗 Créer un compte France Travail →",
            command=lambda: self._open_url("https://francetravail.io/"),
            height=30, width=280,
            fg_color="gray25", hover_color="gray35"
        ).grid(row=14, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        # ── Section Adzuna (rows 15-18) ────────────────────────
        ctk.CTkLabel(
            scroll, text="🔍 Adzuna (source de jobs supplémentaire) — facultatif",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=15, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))

        ctk.CTkLabel(scroll, text="Adzuna App ID").grid(
            row=16, column=0, sticky="w", padx=(10, 15), pady=5)
        self.adzuna_id_entry = ctk.CTkEntry(scroll, height=36)
        self.adzuna_id_entry.insert(0, api.get("adzuna_app_id", ""))
        self.adzuna_id_entry.grid(row=16, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Adzuna App Key").grid(
            row=17, column=0, sticky="w", padx=(10, 15), pady=5)
        self.adzuna_key_entry = ctk.CTkEntry(scroll, height=36, show="*")
        self.adzuna_key_entry.insert(0, api.get("adzuna_app_key", ""))
        self.adzuna_key_entry.grid(row=17, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkButton(
            scroll, text="🔗 Inscription Adzuna (1000 req/mois gratuites) →",
            command=lambda: self._open_url("https://developer.adzuna.com/signup"),
            height=28, width=380,
            fg_color="gray25", hover_color="gray35"
        ).grid(row=18, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))

        # ── Section Filtres (rows 21-26) ───────────────────────
        ctk.CTkLabel(
            scroll, text="🔍 Filtres par défaut",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=21, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))

        ctk.CTkLabel(scroll, text="Mots-clés (virgules)").grid(
            row=22, column=0, sticky="w", padx=(10, 15), pady=5)
        self.mc_entry = ctk.CTkEntry(scroll, height=36)
        self.mc_entry.insert(0, ", ".join(rech.get("mots_cles", [])))
        self.mc_entry.grid(row=22, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Localisation").grid(
            row=23, column=0, sticky="w", padx=(10, 15), pady=5)
        self.loc_entry = ctk.CTkEntry(scroll, height=36)
        self.loc_entry.insert(0, rech.get("localisation", ""))
        self.loc_entry.grid(row=23, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Rayon (km)").grid(
            row=24, column=0, sticky="w", padx=(10, 15), pady=5)
        self.km_entry = ctk.CTkEntry(scroll, height=36)
        self.km_entry.insert(0, str(rech.get("rayon_km", 30)))
        self.km_entry.grid(row=24, column=1, sticky="ew", pady=5, padx=(0, 5))

        ctk.CTkLabel(scroll, text="Type de contrat").grid(
            row=25, column=0, sticky="w", padx=(10, 15), pady=5)
        self.contrat_var = ctk.StringVar(value=rech.get("contrat", "CDI"))
        ctk.CTkOptionMenu(
            scroll, variable=self.contrat_var,
            values=["Tous", "CDI", "CDD", "Stage", "Alternance", "Freelance"],
            width=200, height=36
        ).grid(row=25, column=1, sticky="w", pady=5, padx=(0, 5))

        ctk.CTkButton(
            scroll, text="🌐 Gérer les sources de recherche →",
            command=self.show_sources_manager,
            height=36, fg_color="gray25", hover_color="gray35"
        ).grid(row=26, column=0, columnspan=2,
               sticky="w", padx=5, pady=(15, 5))

        # ── Section Mises à jour (rows 27-30) ──────────────────
        ctk.CTkLabel(
            scroll, text="🔄 Mises à jour",
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=27, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))

        ctk.CTkLabel(
            scroll,
            text=f"Version actuelle : v{APP_VERSION}",
            text_color="gray", font=ctk.CTkFont(size=12)
        ).grid(row=28, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))

        update_btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        update_btn_row.grid(row=29, column=0, columnspan=2,
                            sticky="w", padx=5, pady=(0, 5))
        ctk.CTkButton(
            update_btn_row, text="🔄 Vérifier les mises à jour",
            command=self._check_for_updates,
            height=36, width=240,
            fg_color="#27ae60", hover_color="#2ecc71"
        ).pack(side="left", padx=(0, 6))

        self._update_status_label = ctk.CTkLabel(
            scroll, text="", text_color="gray",
            font=ctk.CTkFont(size=12), wraplength=600, justify="left"
        )
        self._update_status_label.grid(row=30, column=0, columnspan=2,
                                       sticky="w", padx=10, pady=(0, 10))

        ctk.CTkButton(
            self.main, text="💾 Sauvegarder les paramètres",
            command=self.save_settings, height=42,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(fill="x", pady=(10, 0))

    def _show_gmail_info(self):
        win = ctk.CTkToplevel(self)
        win.title("ⓘ Mot de passe Gmail")
        win.geometry("540x440")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 270
        py = self.winfo_y() + self.winfo_height() // 2 - 220
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="ⓘ Ce n'est PAS ton mot de passe Gmail habituel !",
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=480, justify="left"
        ).pack(padx=20, pady=(20, 10), anchor="w")

        msg = (
            "Google bloque les apps externes qui utilisent ton vrai mot de passe "
            "pour des raisons de sécurité.\n\n"
            "Tu dois créer un mot de passe d'application (16 lettres) dédié à cette app :\n\n"
            "1.  Va sur myaccount.google.com/apppasswords\n"
            "2.  Connecte-toi à ton compte Google\n"
            "3.  Nomme l'app « CandidatureBot »\n"
            "4.  Google te donne un code du type  abcd efgh ijkl mnop\n"
            "5.  Colle ce code dans le champ « Mot de passe app »\n\n"
            "👉 Ton vrai mot de passe Gmail reste inchangé et privé."
        )
        ctk.CTkLabel(win, text=msg, justify="left", wraplength=480,
                     font=ctk.CTkFont(size=12)).pack(padx=20, anchor="w")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=15)
        ctk.CTkButton(
            btn_row, text="🔗 Ouvrir Google App Passwords",
            command=lambda: self._open_url("https://myaccount.google.com/apppasswords"),
            height=36, fg_color="#2980b9", hover_color="#3498db"
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Fermer", command=win.destroy,
            height=36, fg_color="gray30", hover_color="gray40"
        ).pack(side="left", padx=5)

        bring_to_front(win)

    def _test_ai_connection(self):
        self.ai_test_label.configure(text="⏳ Test en cours...", text_color="gray")
        def task():
            try:
                self.cfg.setdefault("api", {})["ai_engine"] = self.ai_engine_var.get()
                self.cfg["api"]["openai_key"] = self.openai_entry.get().strip()
                self.cfg["api"]["anthropic_key"] = self.anthropic_entry.get().strip()
                self.cfg["api"]["ollama_model"] = self.ollama_entry.get().strip() or "gemma2:2b"
                from ai_engine import AIEngine
                engine = AIEngine(config=self.cfg)
                offre_test = {"poste": "test", "entreprise": "test", "description": "test"}
                result = engine.generate_email(offre_test, self.cfg)
                if result and "IA indisponible" not in result:
                    self.after(0, lambda: self.ai_test_label.configure(
                        text="✅ Connexion IA OK !", text_color="#27ae60"))
                else:
                    self.after(0, lambda r=result: self.ai_test_label.configure(
                        text=f"⚠️ Fallback template actif. {r[:80] if r else ''}",
                        text_color="#f39c12"))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self.ai_test_label.configure(
                    text=f"❌ Erreur : {err[:100]}", text_color="#e74c3c"))
        threading.Thread(target=task, daemon=True).start()

    # 🆕 Installateur magique Ollama
    def _magic_install_ollama(self):
        from ollama_installer import (is_ollama_installed, is_ollama_running,
                                       list_installed_models, DEFAULT_MODEL)

        win = ctk.CTkToplevel(self)
        win.title("🪄 Installation Ollama")
        win.geometry("580x480")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 290
        py = self.winfo_y() + self.winfo_height() // 2 - 240
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="🪄 Installation automatique d'Ollama",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(20, 8), padx=20, anchor="w")

        # État actuel
        model_wanted = (self.ollama_entry.get().strip()
                        if hasattr(self, "ollama_entry") else DEFAULT_MODEL) or DEFAULT_MODEL
        installed = is_ollama_installed()
        running = is_ollama_running() if installed else False
        models = list_installed_models() if running else []
        model_ready = model_wanted in models

        if installed and running and model_ready:
            status_txt = f"✅ Ollama est opérationnel — modèle « {model_wanted} » prêt."
            status_color = "#27ae60"
        elif installed and running:
            status_txt = f"⚠️  Ollama installé mais le modèle « {model_wanted} » manque."
            status_color = "#f39c12"
        elif installed:
            status_txt = "⚠️  Ollama installé mais le serveur n'est pas lancé."
            status_color = "#f39c12"
        else:
            status_txt = "❌ Ollama n'est pas installé."
            status_color = "#e74c3c"

        ctk.CTkLabel(
            win, text=status_txt,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=status_color
        ).pack(padx=20, pady=(0, 6), anchor="w")

        ctk.CTkLabel(
            win,
            text="• Vérifie si Ollama est installé, l'installe sinon\n"
                 "• Télécharge le modèle (gemma2:2b par défaut, ~1.6 Go)\n"
                 "• Configure l'app pour utiliser Ollama",
            justify="left", font=ctk.CTkFont(size=12), text_color="gray"
        ).pack(padx=20, pady=(0, 10), anchor="w")

        log = ctk.CTkTextbox(win, font=ctk.CTkFont(size=11))
        log.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Append intelligent : les lignes contenant "%" ÉCRASENT la dernière ligne
        # au lieu d'empiler → évite le spam de 100 lignes de téléchargement.
        def append(msg):
            line_end = log.index("end-1c").split(".")
            last_line = max(1, int(line_end[0]) - 1) if log.get("1.0", "end").strip() else 0
            if last_line and "%" in msg:
                prev = log.get(f"{last_line}.0", f"{last_line}.end").rstrip()
                prev_key = prev.rsplit("—", 1)[0].rsplit("…", 1)[0].split(" 1")[0].split(" 2")[0]
                new_key = msg.rsplit("—", 1)[0].rsplit("…", 1)[0].split(" 1")[0].split(" 2")[0]
                # Si même préfixe → remplacer la ligne
                if prev_key.strip() and prev_key.strip() == new_key.strip():
                    log.delete(f"{last_line}.0", f"{last_line}.end")
                    log.insert(f"{last_line}.0", msg)
                    log.see("end")
                    return
            log.insert("end", msg + "\n")
            log.see("end")

        btn_bar = ctk.CTkFrame(win, fg_color="transparent")
        btn_bar.pack(fill="x", padx=20, pady=(0, 15))

        start_btn = ctk.CTkButton(
            btn_bar, text="🚀 Lancer l'installation",
            height=38, fg_color="#6c3483", hover_color="#7d3c98"
        )
        change_btn = ctk.CTkButton(
            btn_bar, text="🔄 Télécharger un autre modèle",
            height=38, fg_color="gray30", hover_color="gray40"
        )
        close_btn = ctk.CTkButton(
            btn_bar, text="Fermer", command=win.destroy,
            height=38, fg_color="gray30", hover_color="gray40"
        )

        def start(force_model=None):
            from ollama_installer import run_full_install, DEFAULT_MODEL
            model = force_model or model_wanted
            start_btn.configure(state="disabled", text="⏳ Installation…")
            change_btn.configure(state="disabled")

            def on_progress(msg):
                win.after(0, append, msg)

            def on_done(success, err):
                def finish():
                    if success:
                        append("")
                        append("🎉 Tout est prêt ! L'IA est configurée sur Ollama.")
                        if hasattr(self, "ai_engine_var"):
                            self.ai_engine_var.set("ollama")
                        if hasattr(self, "ollama_entry"):
                            self.ollama_entry.delete(0, "end")
                            self.ollama_entry.insert(0, model)
                        if hasattr(self, "ai_test_label"):
                            self.ai_test_label.configure(
                                text="✅ Ollama installé & connecté",
                                text_color="#27ae60")
                        # Fin réussie → plus besoin de réinstaller, on grise
                        start_btn.configure(
                            text="✅ Déjà installé",
                            state="disabled", fg_color="gray30")
                        change_btn.configure(state="normal")
                    else:
                        append(f"\n❌ Échec : {err}")
                        start_btn.configure(text="🔄 Réessayer", state="normal")
                        change_btn.configure(state="normal")
                win.after(0, finish)

            run_full_install(self.cfg, save_config, on_progress, on_done, model=model)

        def change_model():
            new_model = simpledialog.askstring(
                "Changer de modèle",
                "Nom du modèle Ollama à télécharger\n"
                "(ex: gemma2:2b, llama3.2:3b, qwen2.5:3b) :",
                parent=win, initialvalue=DEFAULT_MODEL
            )
            if new_model and new_model.strip():
                start(force_model=new_model.strip())

        start_btn.configure(command=lambda: start())
        change_btn.configure(command=change_model)
        start_btn.pack(side="left", padx=(0, 5))
        change_btn.pack(side="left", padx=(0, 5))
        close_btn.pack(side="left")

        # Si déjà tout prêt → on grise le bouton d'install
        if installed and running and model_ready:
            start_btn.configure(
                text="✅ Déjà installé", state="disabled",
                fg_color="gray30", hover_color="gray30"
            )
            append("✅ Tout est opérationnel — rien à faire.")
            append(f"   Modèles présents : {', '.join(models) if models else '(aucun)'}")

        bring_to_front(win)

    def _save_settings_silent(self):
        """Persistance silencieuse des Paramètres (utilisée par auto-save
        sur changement de page). Tous les accès widgets sont entourés de
        winfo_exists guards car la page peut être en cours de destruction."""
        # Si la page n'a jamais été affichée, les widgets n'existent pas
        if not (hasattr(self, "ai_engine_var") and hasattr(self, "openai_entry")):
            return
        try:
            if not self.openai_entry.winfo_exists():
                return
        except Exception:
            return

        rech = self.cfg.setdefault("recherche", {})
        api = self.cfg.setdefault("api", {})

        def _g(attr):
            try:
                w = getattr(self, attr, None)
                if w is None or not w.winfo_exists():
                    return None
                return w.get().strip()
            except Exception:
                return None

        # IA
        try:
            api["ai_engine"] = self.ai_engine_var.get()
        except Exception:
            pass
        for attr, key, default in [
            ("openai_entry",   "openai_key",       None),
            ("anthropic_entry","anthropic_key",    None),
            ("ollama_entry",   "ollama_model",     "gemma2:2b"),
            ("gmail_user_entry",      "gmail_user",       None),
            ("gmail_pwd_entry",       "gmail_password",   None),
            ("ft_id_entry",           "ft_client_id",     None),
            ("ft_secret_entry",       "ft_client_secret", None),
            ("adzuna_id_entry",       "adzuna_app_id",    None),
            ("adzuna_key_entry",      "adzuna_app_key",   None),
        ]:
            v = _g(attr)
            if v is not None:
                api[key] = v if v else (default or "")

        # Filtres
        v = _g("mc_entry")
        if v is not None:
            rech["mots_cles"] = [m.strip() for m in v.split(",") if m.strip()]
        v = _g("loc_entry")
        if v is not None:
            rech["localisation"] = v
        v = _g("km_entry")
        if v is not None:
            try:
                rech["rayon_km"] = int(v or "30")
            except ValueError:
                rech.setdefault("rayon_km", 30)
        try:
            if hasattr(self, "contrat_var"):
                rech["contrat"] = self.contrat_var.get()
        except Exception:
            pass

        try:
            self._write_env()
        except Exception:
            pass
        save_config(self.cfg)

    def save_settings(self):
        self._save_settings_silent()
        messagebox.showinfo("✅", "Paramètres sauvegardés !")

    def _write_env(self):
        api = self.cfg.get("api", {})
        lines = [
            f"FT_CLIENT_ID={api.get('ft_client_id', '')}",
            f"FT_CLIENT_SECRET={api.get('ft_client_secret', '')}",
            f"OPENAI_API_KEY={api.get('openai_key', '')}",
            f"ANTHROPIC_API_KEY={api.get('anthropic_key', '')}",
            f"GMAIL_USER={api.get('gmail_user', '')}",
            f"GMAIL_APP_PASSWORD={api.get('gmail_password', '')}",
            f"AI_ENGINE={api.get('ai_engine', 'ollama')}",
            f"OLLAMA_MODEL={api.get('ollama_model', 'gemma2:2b')}",
        ]
        env_p = app_paths.env_path()
        with open(env_p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        # Restreint les permissions pour limiter la fuite des secrets
        try:
            os.chmod(env_p, 0o600)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    # ❓ AIDE : manuel PDF + formulaire de support
    # ══════════════════════════════════════════════════════════════
    def _open_help_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Aide")
        win.geometry("440x290")
        win.resizable(False, False)
        win.transient(self)
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 220
        py = self.winfo_y() + self.winfo_height() // 2 - 145
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="Comment pouvons-nous vous aider ?",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=(22, 18))

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(expand=True, pady=(0, 10))

        def _icon(parent, emoji, label, cmd):
            box = ctk.CTkFrame(parent, fg_color="transparent")
            box.pack(side="left", padx=22)
            ctk.CTkButton(
                box, text=emoji, width=86, height=86,
                corner_radius=14,
                font=ctk.CTkFont(size=38),
                fg_color=("gray80", "gray25"),
                hover_color=("gray70", "gray35"),
                command=cmd,
            ).pack()
            ctk.CTkLabel(
                box, text=label, font=ctk.CTkFont(size=12)
            ).pack(pady=(6, 0))

        _icon(row, "📄", "Manuel",
              lambda: (win.destroy(), self._open_user_manual_pdf()))
        _icon(row, "✉️", "Support",
              lambda: (win.destroy(), self._open_support_form()))

        ctk.CTkLabel(
            win, text=f"Candidature Bot — version {APP_VERSION}",
            text_color="gray", font=ctk.CTkFont(size=10)
        ).pack(side="bottom", pady=10)

        bring_to_front(win)

    # ── Formulaire de support ─────────────────────────────────
    def _open_support_form(self):
        win = ctk.CTkToplevel(self)
        win.title("Contacter le support")
        win.geometry("480x430")
        win.resizable(False, False)
        win.transient(self)
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 240
        py = self.winfo_y() + self.winfo_height() // 2 - 215
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="Contacter le support",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=(18, 14))

        # Barre d'action en bas — packée AVANT le body pour
        # toujours rester visible quel que soit le contenu.
        action_bar = ctk.CTkFrame(win, fg_color="transparent")
        action_bar.pack(side="bottom", fill="x", padx=22, pady=(0, 14))

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(side="top", fill="both", expand=True, padx=22)

        ctk.CTkLabel(body, text="Objet").pack(anchor="w")
        e_subject = ctk.CTkEntry(body, height=32)
        e_subject.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(body, text="Votre e-mail (pour la réponse)").pack(anchor="w")
        e_mail = ctk.CTkEntry(body, height=32)
        prefill = (self.cfg.get("api", {}).get("gmail_user")
                   or self.cfg.get("profil", {}).get("email", ""))
        if prefill:
            e_mail.insert(0, prefill)
        e_mail.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(body, text="Message").pack(anchor="w")
        txt = ctk.CTkTextbox(body, height=130)
        txt.pack(fill="both", expand=True, pady=(2, 0))

        status = ctk.CTkLabel(action_bar, text="", text_color="gray",
                              font=ctk.CTkFont(size=11))
        status.pack(anchor="w")

        def _do_send():
            obj = e_subject.get().strip()
            mail = e_mail.get().strip()
            com = txt.get("1.0", "end").strip()
            if not obj or not mail or not com:
                messagebox.showwarning(
                    "Champs manquants",
                    "Merci de remplir l'objet, votre e-mail et le message."
                )
                return
            if "@" not in mail:
                messagebox.showwarning(
                    "E-mail invalide",
                    "L'adresse e-mail saisie est invalide."
                )
                return

            profil = self.cfg.get("profil", {}) or {}
            nom = f"{profil.get('prenom','')} {profil.get('nom','')}".strip() or "—"
            full_subject = f"[Support — Candidature Bot v{APP_VERSION}] {obj}"
            mail_body = (
                f"De   : {nom}\n"
                f"Mail : {mail}\n"
                f"Version : {APP_VERSION}\n"
                f"--------------------------------------------\n\n"
                f"{com}\n"
            )

            # 1) Si Gmail est configuré → envoi SMTP silencieux
            from mail_sender import MailSender
            sender = MailSender(self.cfg)
            if sender.user and sender.password:
                send_btn.configure(state="disabled", text="Envoi en cours…")
                status.configure(text="", text_color="gray")

                def task():
                    try:
                        sender.send(SUPPORT_EMAIL, full_subject, mail_body)
                        self.after(0, lambda: (
                            messagebox.showinfo(
                                "Merci",
                                "Votre message a bien été envoyé."),
                            win.destroy()
                        ))
                    except Exception as e:
                        self.after(0, lambda err=e: (
                            send_btn.configure(state="normal",
                                               text="Envoyer"),
                            status.configure(
                                text=f"❌ {err}", text_color="#e74c3c")
                        ))

                threading.Thread(target=task, daemon=True).start()
                return

            # 2) Sinon → fallback mailto (ouvre l'app mail par défaut)
            import urllib.parse
            qs = urllib.parse.urlencode({
                "subject": full_subject,
                "body": mail_body,
            })
            try:
                webbrowser.open(f"mailto:{SUPPORT_EMAIL}?{qs}")
                win.destroy()
            except Exception as e:
                status.configure(text=f"❌ {e}", text_color="#e74c3c")

        send_btn = ctk.CTkButton(
            action_bar, text="Envoyer",
            height=40, command=_do_send,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        send_btn.pack(fill="x", pady=(8, 0))

        bring_to_front(win)

    # ── Manuel PDF ────────────────────────────────────────────
    def _open_user_manual_pdf(self):
        import tempfile
        import subprocess
        import sys
        path = os.path.join(
            tempfile.gettempdir(),
            f"CandidatureBot_Manuel_v{APP_VERSION}.pdf"
        )
        try:
            self._build_user_manual_pdf(path)
        except Exception as e:
            messagebox.showerror(
                "Manuel",
                f"Erreur lors de la génération du PDF :\n{e}"
            )
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", path])
            elif sys.platform == "win32":
                os.startfile(path)
            else:
                messagebox.showinfo("Manuel", f"PDF généré ici :\n{path}")
        except Exception as e:
            messagebox.showerror(
                "Manuel",
                f"PDF généré mais ouverture impossible.\n{path}\n\n{e}"
            )

    def _build_user_manual_pdf(self, out_path):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_JUSTIFY
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak,
        )

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        doc = SimpleDocTemplate(
            out_path, pagesize=A4,
            topMargin=2 * cm, bottomMargin=2 * cm,
            leftMargin=2.2 * cm, rightMargin=2.2 * cm,
            title=f"Candidature Bot — Manuel v{APP_VERSION}",
            author="Candidature Bot",
        )

        styles = getSampleStyleSheet()
        cover = ParagraphStyle(
            "cover", parent=styles["Title"],
            fontSize=32, leading=38, spaceAfter=20,
            textColor=HexColor("#1f538d"),
        )
        sub = ParagraphStyle(
            "sub", parent=styles["Normal"],
            fontSize=13, leading=18, textColor=HexColor("#555555"),
        )
        h1 = ParagraphStyle(
            "h1", parent=styles["Heading1"],
            fontSize=18, leading=22, spaceBefore=14, spaceAfter=8,
            textColor=HexColor("#1f538d"),
        )
        h2 = ParagraphStyle(
            "h2", parent=styles["Heading2"],
            fontSize=13, leading=17, spaceBefore=10, spaceAfter=4,
            textColor=HexColor("#222222"),
        )
        body = ParagraphStyle(
            "body", parent=styles["Normal"],
            fontSize=11, leading=15, alignment=TA_JUSTIFY, spaceAfter=6,
        )
        bullet = ParagraphStyle(
            "bullet", parent=body,
            leftIndent=14, bulletIndent=2, spaceAfter=3,
        )

        story = []

        # Page de garde
        story.append(Spacer(1, 4 * cm))
        story.append(Paragraph("Candidature Bot", cover))
        story.append(Paragraph(
            f"Manuel utilisateur — version {APP_VERSION}", sub))
        story.append(Spacer(1, 0.6 * cm))
        story.append(Paragraph(
            f"Date de génération : "
            f"{datetime.date.today().strftime('%d/%m/%Y')}", sub))
        story.append(Spacer(1, 1.2 * cm))
        story.append(Paragraph(
            "Ce manuel est généré automatiquement à partir de la version "
            "installée — il reflète toujours l'état actuel de l'application.",
            body))
        story.append(PageBreak())

        # Contenu
        for kind, txt in self._user_manual_content():
            if kind == "h1":
                story.append(Paragraph(txt, h1))
            elif kind == "h2":
                story.append(Paragraph(txt, h2))
            elif kind == "bullet":
                story.append(Paragraph(f"•&nbsp;&nbsp;{txt}", bullet))
            else:
                story.append(Paragraph(txt, body))

        doc.build(story)
        return out_path

    def _user_manual_content(self):
        sources = self.cfg.get("sources", {}) or {}
        active = [name for name, on in sources.items() if on]
        custom = self.cfg.get("custom_sources", []) or []
        ai_engine = (self.cfg.get("api", {}) or {}).get("ai_engine", "ollama")

        C = []
        C.append(("h1", "Présentation"))
        C.append(("body",
            "Candidature Bot automatise la recherche d'offres d'emploi, "
            "la génération de lettres de motivation personnalisées et "
            "l'envoi des candidatures par e-mail. Toutes les données "
            "restent en local sur votre machine."))

        C.append(("h1", "1. Rechercher"))
        C.append(("h2", "Recherche automatique"))
        C.append(("body",
            "Saisissez vos mots-clés, votre lieu, le rayon de recherche "
            "et le type de contrat. Le sélecteur « Afficher » permet "
            "de limiter le nombre de résultats à 10, 20 ou tous "
            "(« Max »)."))
        C.append(("body",
            f"Sources actives à ce jour : "
            f"{', '.join(active) if active else 'aucune'}"
            + (f" + {len(custom)} source(s) personnalisée(s)"
               if custom else "")
            + "."))
        C.append(("h2", "Sélection multiple"))
        C.append(("body",
            "Cochez plusieurs offres puis cliquez sur « Ajouter aux "
            "candidatures » pour toutes les ajouter en une fois. "
            "« Tout sélectionner » coche l'ensemble des résultats "
            "affichés."))
        C.append(("h2", "Ajout manuel"))
        C.append(("body",
            "Le bouton « Ajout manuel » permet d'enregistrer une offre "
            "trouvée hors de l'application (intitulé, entreprise, lieu, "
            "URL, e-mail, description)."))

        C.append(("h1", "2. Candidatures"))
        C.append(("body",
            "Toutes les offres ajoutées sont listées ici avec leur "
            "statut (À envoyer, Envoyé, Entretien, Refusé, Accepté). "
            "Chaque statut a sa couleur ; le menu déroulant à droite "
            "permet de la mettre à jour à la volée."))
        C.append(("h2", "Postuler par e-mail"))
        C.append(("body",
            "Si l'offre comporte une adresse e-mail, vous pouvez "
            "rédiger la lettre de motivation, prévisualiser le mail "
            "d'accompagnement et envoyer le tout (lettre + CV en "
            "pièces jointes) directement depuis l'application."))

        C.append(("h1", "3. Routine"))
        C.append(("body",
            "La routine relance la recherche automatiquement selon une "
            "fréquence configurable (heures / jours). Les paramètres "
            "par défaut reprennent ceux de la recherche automatique : "
            "mots-clés, lieu, rayon et type de contrat."))

        C.append(("h1", "4. Mes infos"))
        C.append(("body",
            "Importez votre CV (PDF / image) : l'application en "
            "extrait automatiquement votre nom, vos compétences "
            "et vos langues. Vous pouvez ensuite ajuster les champs "
            "manuellement. Importez également votre lettre de "
            "motivation type pour servir de référence stylistique "
            "à l'IA."))

        C.append(("h1", "5. Paramètres"))
        C.append(("h2", "Moteur IA"))
        C.append(("body",
            f"Moteur IA actuel : {ai_engine}. "
            "Les options sont : Ollama (local, gratuit), OpenAI "
            "(GPT-4o-mini, payant) ou Claude (Anthropic, payant). "
            "Si l'IA est indisponible, un modèle de lettre/mail de "
            "secours est utilisé automatiquement."))
        C.append(("h2", "Identifiants Gmail"))
        C.append(("body",
            "Pour envoyer des e-mails, configurez votre adresse Gmail "
            "et un mot de passe d'application (à générer sur "
            "myaccount.google.com/apppasswords). Aucun mot de passe "
            "n'est envoyé à un serveur tiers."))
        C.append(("h2", "Clés API"))
        C.append(("body",
            "France Travail, OpenAI et Anthropic se configurent "
            "individuellement dans l'onglet Paramètres."))

        C.append(("h1", "6. Aide"))
        C.append(("body",
            "Le bouton « ? » en bas à gauche ouvre cette page d'aide. "
            "Le formulaire « Support » envoie votre message via votre "
            "Gmail si celui-ci est configuré dans Paramètres ; sinon, "
            "votre application mail par défaut s'ouvre avec le message "
            "pré-rempli."))
        C.append(("body",
            f"Document généré par Candidature Bot v{APP_VERSION} — "
            "il reflète toujours la version installée."))
        return C

    # ══════════════════════════════════════════════════════════
    # 🔄 Système de mise à jour à distance
    # ══════════════════════════════════════════════════════════
    def _set_update_status(self, text, color="gray"):
        """Met à jour le label d'état (thread-safe)."""
        try:
            if hasattr(self, "_update_status_label") and \
               self._update_status_label.winfo_exists():
                self._update_status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    @staticmethod
    def _version_tuple(v):
        """Convertit '1.0.1' / 'v1.2.3-beta' → (1,0,1) pour comparaison."""
        v = (v or "0").strip().lstrip("vV").split("-")[0].split("+")[0]
        parts = []
        for x in v.split("."):
            try:
                parts.append(int(x))
            except ValueError:
                parts.append(0)
        return tuple(parts) or (0,)

    def _check_for_updates(self):
        """Lance la vérification dans un thread (UI non-bloquante)."""
        self._set_update_status("⏳ Vérification...", "gray")
        threading.Thread(target=self._check_for_updates_async,
                         daemon=True).start()

    def _check_for_updates_async(self):
        try:
            import requests
            resp = requests.get(UPDATE_MANIFEST_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            latest = data.get("version", "0")
            if self._version_tuple(latest) > self._version_tuple(APP_VERSION):
                self.after(0, lambda: self._show_update_available(data))
            else:
                self.after(0, lambda: self._set_update_status(
                    f"✅ Vous avez la dernière version (v{APP_VERSION}).",
                    "#27ae60"))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._set_update_status(
                f"❌ Impossible de vérifier : {err}", "#e74c3c"))

    def _show_update_available(self, data):
        version = data.get("version", "?")
        notes = (data.get("notes") or "").strip()
        released = data.get("released", "")
        msg = f"Une nouvelle version est disponible : v{version}"
        if released:
            msg += f"  (publiée le {released})"
        msg += f"\n\nVersion actuelle : v{APP_VERSION}\n\n"
        if notes:
            msg += f"Nouveautés :\n{notes}\n\n"
        msg += ("Installer maintenant ?\n"
                "L'application redémarrera automatiquement après l'install.")
        if messagebox.askyesno("🔄 Mise à jour disponible", msg):
            self._set_update_status("⏳ Téléchargement...", "gray")
            threading.Thread(target=self._install_update_async,
                             args=(data,), daemon=True).start()
        else:
            self._set_update_status(
                f"ℹ️ Mise à jour v{version} disponible (annulée).", "gray")

    def _install_update_async(self, data):
        """Télécharge le ZIP, l'extrait, sauvegarde l'ancien, remplace les
        fichiers (sauf config.json / data/ / .env), puis redémarre."""
        zip_path = None
        extract_root = None
        # Limite à 100 Mo pour éviter un DoS disque sur URL malveillante
        MAX_DOWNLOAD = 100 * 1024 * 1024
        try:
            import requests
            url = data.get("url")
            if not url:
                raise RuntimeError("URL du ZIP manquante dans le manifest.")
            if not (url.startswith("http://") or url.startswith("https://")):
                raise RuntimeError(f"URL invalide ({url[:30]}...).")

            # 1. Téléchargement
            self.after(0, lambda: self._set_update_status(
                "⏳ Téléchargement du paquet...", "gray"))
            zip_path = os.path.join(
                tempfile.gettempdir(),
                f"candidaturebot_{int(time.time())}.zip"
            )
            downloaded = 0
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            downloaded += len(chunk)
                            if downloaded > MAX_DOWNLOAD:
                                raise RuntimeError(
                                    f"Téléchargement > {MAX_DOWNLOAD // (1024*1024)} Mo — abandon."
                                )
                            f.write(chunk)

            # 2. Extraction
            self.after(0, lambda: self._set_update_status(
                "⏳ Extraction...", "gray"))
            extract_root = tempfile.mkdtemp(prefix="cbot_update_")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_root)

            # Si le ZIP contient un dossier racine unique, on descend dedans
            # SAUF s'il s'agit déjà du bundle .app lui-même (cas macOS).
            # Sinon on rentrerait DANS CandidatureBot.app, et l'étape
            # suivante ne trouverait pas de .app à installer.
            extract_dir = extract_root
            entries = os.listdir(extract_dir)
            if len(entries) == 1 and \
               os.path.isdir(os.path.join(extract_dir, entries[0])) and \
               not entries[0].endswith(".app"):
                extract_dir = os.path.join(extract_dir, entries[0])

            # 3. Détection : app frozen sur macOS → on cherche un .app
            #    dans le ZIP et on délègue à un script de swap externe
            #    (impossible d'écraser un .app en cours d'exécution
            #    depuis le process lui-même).
            if app_paths.is_frozen() and sys.platform == "darwin":
                self._install_macos_bundle(extract_dir, data, extract_root, zip_path)
                # Le script a pris le relais : on ne nettoie PAS extract_root
                # (le swap script a besoin du .app extrait dedans).
                extract_root = None
                zip_path = None
                return

            # 4. Backup avant écrasement (mode source / non-macOS)
            self.after(0, lambda: self._set_update_status(
                "⏳ Sauvegarde de l'ancienne version...", "gray"))
            app_dir = str(app_paths.app_install_dir())
            backup_dir = str(
                app_paths.backups_dir() /
                f"v{APP_VERSION}_{int(time.time())}"
            )
            os.makedirs(backup_dir, exist_ok=True)
            for fname in os.listdir(app_dir):
                if fname in ("data", "config.json", ".env",
                             ".git", "venv", "__pycache__"):
                    continue
                src = os.path.join(app_dir, fname)
                if os.path.isfile(src):
                    try:
                        shutil.copy2(src, backup_dir)
                    except Exception as exc:
                        print(f"[update] backup skip {fname}: {exc}")

            # 5. Remplacement des fichiers (on protège les données utilisateur)
            self.after(0, lambda: self._set_update_status(
                "⏳ Installation...", "gray"))
            PROTECTED = {"config.json", "data", ".env",
                         ".git", "venv", "__pycache__"}
            for item in os.listdir(extract_dir):
                if item in PROTECTED:
                    continue
                src = os.path.join(extract_dir, item)
                dst = os.path.join(app_dir, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

            # 6. Redémarrage
            new_v = data.get("version", "?")
            self.after(0, lambda: self._set_update_status(
                f"✅ Mise à jour v{new_v} installée — redémarrage...",
                "#27ae60"))
            self.after(1500, self._restart_app)
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._set_update_status(
                f"❌ Échec de l'installation : {err}", "#e74c3c"))
        finally:
            # Nettoyage des temp pour éviter une fuite disque
            try:
                if zip_path and os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception:
                pass
            try:
                if extract_root and os.path.exists(extract_root):
                    shutil.rmtree(extract_root, ignore_errors=True)
            except Exception:
                pass

    def _restart_app(self):
        """Relance proprement l'application avec le même Python."""
        try:
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception:
            # Fallback : message à l'utilisateur si execl échoue (rare)
            messagebox.showinfo(
                "Mise à jour installée",
                "Veuillez relancer Candidature Bot manuellement."
            )
            self.destroy()

    def _install_macos_bundle(self, extract_dir, data, extract_root, zip_path):
        """Stratégie macOS pour app frozen :
        On NE PEUT PAS écraser un .app actif depuis lui-même. On écrit
        donc un petit script bash qui :
          1. attend que le PID courant disparaisse,
          2. déplace l'ancien .app dans un backup horodaté,
          3. déplace le nouveau .app au bon endroit,
          4. relance l'app via `open`,
          5. se supprime lui-même.
        Le script est lancé en `subprocess` détaché pour survivre à
        notre `destroy()`."""
        import subprocess

        # 1. Localise le .app extrait
        app_in_zip = None
        # Cas a : extract_dir EST déjà le bundle .app
        if extract_dir.rstrip("/").endswith(".app") and os.path.isdir(extract_dir):
            app_in_zip = extract_dir
        # Cas b : .app à la racine de l'extract
        if not app_in_zip:
            for entry in os.listdir(extract_dir):
                full = os.path.join(extract_dir, entry)
                if entry.endswith(".app") and os.path.isdir(full):
                    app_in_zip = full
                    break
        # Cas c : .app dans une sous-arborescence
        if not app_in_zip:
            for root, dirs, _files in os.walk(extract_dir):
                for d in dirs:
                    if d.endswith(".app"):
                        app_in_zip = os.path.join(root, d)
                        break
                if app_in_zip:
                    break
        if not app_in_zip:
            raise RuntimeError(
                "Aucun bundle .app trouvé dans le ZIP de mise à jour. "
                "Pour les utilisateurs macOS, le ZIP doit contenir "
                "CandidatureBot.app à sa racine."
            )

        # 2. Localise l'app courante : sys.executable est typiquement
        #    /chemin/CandidatureBot.app/Contents/MacOS/CandidatureBot
        current_exe = os.path.abspath(sys.executable)
        if ".app/" not in current_exe:
            raise RuntimeError(
                f"Impossible de déterminer l'app courante depuis {current_exe}"
            )
        current_app = current_exe.split(".app/")[0] + ".app"

        # 3. Backup destination (data/backups/app_<ts>/)
        backup_root = str(app_paths.backups_dir() /
                          f"app_v{APP_VERSION}_{int(time.time())}")
        os.makedirs(backup_root, exist_ok=True)

        # 4. Génère le script de swap
        pid = os.getpid()
        new_v = data.get("version", "?")
        script_lines = [
            "#!/bin/bash",
            "set -e",
            "",
            f"# Swap de mise à jour vers v{new_v}",
            f"PID={pid}",
            f'CURRENT_APP="{current_app}"',
            f'NEW_APP="{app_in_zip}"',
            f'BACKUP_DIR="{backup_root}"',
            f'EXTRACT_ROOT="{extract_root}"',
            f'ZIP_PATH="{zip_path}"',
            "",
            "# 1. Attend la fin du process courant (max 60s)",
            "for i in $(seq 1 120); do",
            '  if ! kill -0 "$PID" 2>/dev/null; then break; fi',
            "  sleep 0.5",
            "done",
            "sleep 1  # marge pour macOS",
            "",
            "# 2. Backup de l'ancien .app",
            'if [ -d "$CURRENT_APP" ]; then',
            '  mv "$CURRENT_APP" "$BACKUP_DIR/" 2>/dev/null || rm -rf "$CURRENT_APP"',
            "fi",
            "",
            "# 3. Installe le nouveau .app",
            'mv "$NEW_APP" "$CURRENT_APP"',
            "",
            "# 4. Retire le quarantaine flag pour éviter Gatekeeper",
            'xattr -cr "$CURRENT_APP" 2>/dev/null || true',
            "",
            "# 5. Relance la nouvelle app",
            'open "$CURRENT_APP"',
            "",
            "# 6. Cleanup des temp",
            'rm -rf "$EXTRACT_ROOT" 2>/dev/null || true',
            'rm -f "$ZIP_PATH" 2>/dev/null || true',
            "",
            "# 7. Self-destruct du script",
            'rm -f "$0"',
            "",
        ]
        script = "\n".join(script_lines)

        script_path = os.path.join(
            tempfile.gettempdir(),
            f"cbot_swap_{int(time.time())}.sh"
        )
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(script_path, 0o755)

        # 5. UI : informe l'utilisateur
        self.after(0, lambda: self._set_update_status(
            f"✅ v{new_v} prête — fermeture pour finaliser l'installation...",
            "#27ae60"))

        # 6. Lance le script détaché (survit à notre destroy)
        subprocess.Popen(
            ["/bin/bash", script_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # 7. Quitte l'app après un délai (laisse le user lire le message)
        def _quit():
            try:
                self.destroy()
            except Exception:
                pass
            os._exit(0)
        self.after(2000, _quit)


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # On force le CWD vers le dossier inscriptible pour neutraliser
    # tous les chemins relatifs résiduels ("data/...", ".env"...).
    try:
        os.chdir(str(app_paths.app_data_dir()))
    except Exception:
        pass
    # S'assure que les dossiers nécessaires existent
    app_paths.data_dir()
    app_paths.pdfs_dir()
    app = App()
    app.mainloop()
