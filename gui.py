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
import theme

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
THEME = theme.Colors
ICONS = theme

# Chemins centralisés (cross-platform, compatible PyInstaller).
# En mode source on retombe sur le dossier du projet pour ne pas
# casser le développement habituel.
CONFIG_PATH = str(app_paths.config_path())
APP_VERSION = "1.0.22"
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
        "indeed": True,         # débloqué par Scrapling (TLS fingerprint Chrome)
        "linkedin": True,
        "apec": False,
        "welcometothejungle": True,
        "hellowork": True,
        "talent": True,         # nouveau via Scrapling
        "jooble": True,         # nouveau via Scrapling
        "adzuna": False,        # nécessite clé API gratuite developer.adzuna.com
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
# WIDGET : ChipsEditor — éditeur de tags wrappés
# ══════════════════════════════════════════════════════════════
class ChipsEditor(ctk.CTkFrame):
    """Éditeur de chips (tags) avec wrap automatique.

    Utilise un Text widget en interne pour bénéficier du wrap natif de Tk
    (window_create dans un Text wrapped → les chips passent à la ligne tout
    seuls quand le conteneur est plein).

    API :
        editor = ChipsEditor(parent, values=["Python", "Django"],
                             placeholder="+ ajouter", on_change=callback)
        editor.get_values() → list[str]
        editor.set_values(values)
    """
    def __init__(self, parent, values=None, placeholder="+ ajouter",
                 on_change=None, height=80, **kwargs):
        super().__init__(
            parent,
            fg_color=theme.Colors.bg_panel,
            border_color=theme.Colors.border,
            border_width=1, corner_radius=6,
            height=height,
            **kwargs
        )
        self.pack_propagate(False)
        self._values = list(values or [])
        self._placeholder = placeholder
        self._on_change = on_change

        # Text widget : wrap natif. On bloque l'input clavier.
        self._txt = tk.Text(
            self, wrap="word", bd=0, highlightthickness=0,
            bg=theme.Colors.bg_panel, cursor="arrow",
            font=("Helvetica", 1),  # police minuscule pour minimiser hauteur de ligne
        )
        self._txt.pack(fill="both", expand=True, padx=6, pady=6)
        # Bloque la saisie clavier (le widget reste utilisable pour embed)
        self._txt.bind("<Key>", lambda e: "break")
        self._txt.bind("<Button-1>", lambda e: "break")
        self._render()

    def _render(self):
        self._txt.config(state="normal")
        self._txt.delete("1.0", "end")
        for v in self._values:
            chip = self._make_chip(v)
            self._txt.window_create("end", window=chip, padx=2, pady=2)
        add_btn = self._make_add()
        self._txt.window_create("end", window=add_btn, padx=2, pady=2)
        self._txt.config(state="disabled")

    def _make_chip(self, value):
        f = ctk.CTkFrame(
            self._txt, fg_color=theme.Colors.bg_panel_alt,
            corner_radius=10, height=22
        )
        lbl = ctk.CTkLabel(
            f, text=value, font=ctk.CTkFont(size=11),
            fg_color="transparent", text_color=theme.Colors.text_primary
        )
        lbl.pack(side="left", padx=(9, 4), pady=2)
        x_lbl = ctk.CTkLabel(
            f, text="×", font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", text_color=theme.Colors.text_muted,
            cursor="hand2", width=14
        )
        x_lbl.pack(side="left", padx=(0, 6))
        x_lbl.bind("<Button-1>", lambda e, v=value: self._remove(v))
        # Hover sur le × pour le faire ressortir
        x_lbl.bind("<Enter>",
                   lambda e, w=x_lbl: w.configure(text_color=theme.Colors.red_danger))
        x_lbl.bind("<Leave>",
                   lambda e, w=x_lbl: w.configure(text_color=theme.Colors.text_muted))
        return f

    def _make_add(self):
        f = ctk.CTkFrame(
            self._txt, fg_color="transparent",
            border_color=theme.Colors.border, border_width=1,
            corner_radius=10, height=22, cursor="hand2"
        )
        lbl = ctk.CTkLabel(
            f, text=self._placeholder, font=ctk.CTkFont(size=11),
            fg_color="transparent", text_color=theme.Colors.text_muted
        )
        lbl.pack(padx=10, pady=2)
        f.bind("<Button-1>", self._prompt_add)
        lbl.bind("<Button-1>", self._prompt_add)
        # Hover
        def _hover(_e=None):
            f.configure(border_color=theme.Colors.accent)
            lbl.configure(text_color=theme.Colors.accent_hover)
        def _leave(_e=None):
            f.configure(border_color=theme.Colors.border)
            lbl.configure(text_color=theme.Colors.text_muted)
        f.bind("<Enter>", _hover)
        f.bind("<Leave>", _leave)
        lbl.bind("<Enter>", _hover)
        lbl.bind("<Leave>", _leave)
        return f

    def _prompt_add(self, event=None):
        val = simpledialog.askstring(
            "Ajouter", "Nouvelle valeur :",
            parent=self.winfo_toplevel()
        )
        if val and val.strip():
            v = val.strip()
            if v.lower() not in (x.lower() for x in self._values):
                self._values.append(v)
                self._render()
                if self._on_change:
                    try: self._on_change(self._values)
                    except Exception: pass

    def _remove(self, value):
        if value in self._values:
            self._values.remove(value)
            self._render()
            if self._on_change:
                try: self._on_change(self._values)
                except Exception: pass

    def get_values(self):
        return list(self._values)

    def set_values(self, values):
        self._values = list(values or [])
        # Si le widget a été détruit (ex : navigation page), on garde
        # la valeur en mémoire mais on évite de re-render un widget mort.
        try:
            if self.winfo_exists() and self._txt.winfo_exists():
                self._render()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Candidature Bot")
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
            self.sidebar, text="CANDIDATURE\nBOT",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(30, 25))

        # Icônes line-art HD (gris inactif / blanc actif)
        def _mk(fn):
            ina = theme.ctk_icon(fn, size=18, color=THEME.text_secondary)
            act = theme.ctk_icon(fn, size=18, color="#FFFFFF")
            return ina, act
        self._nav_icons = {
            "RECHERCHE":     _mk(theme.icon_search),
            "CANDIDATURES":  _mk(theme.icon_list),
            "ROUTINE":       _mk(theme.icon_loop),
            "MES INFOS":     _mk(theme.icon_user),
            "PARAMÈTRES":    _mk(theme.icon_settings),
        }

        nav = [
            ("RECHERCHE",    self.show_search),
            ("CANDIDATURES", self.show_tracker),
            ("ROUTINE",      self.show_routine),
            ("MES INFOS",    self.show_profile),
            ("PARAMÈTRES",   self.show_settings),
        ]
        self.nav_btns = {}
        for i, (label, cmd) in enumerate(nav, 1):
            ina_icon, _ = self._nav_icons[label]
            b = ctk.CTkButton(
                self.sidebar, text=label, command=cmd,
                image=ina_icon, compound="left",
                height=40, anchor="w", corner_radius=8,
                fg_color="transparent",
                text_color=THEME.text_secondary,
                hover_color=THEME.bg_hover,
                font=ctk.CTkFont(size=13, weight="bold")
            )
            b.grid(row=i, column=0, padx=10, pady=2, sticky="ew")
            self.nav_btns[label] = b

        # Bouton d'aide en bas du sidebar — icône cercle interrogation HD
        help_icon = theme.ctk_icon(theme.icon_question, size=20,
                                    color=THEME.text_secondary)
        ctk.CTkButton(
            self.sidebar, text="", image=help_icon,
            width=36, height=36, corner_radius=18,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            command=self._open_help_window
        ).grid(row=11, column=0, padx=15, pady=(0, 15), sticky="w")

    def _set_active(self, label):
        for l, b in self.nav_btns.items():
            ina_icon, _ = self._nav_icons.get(l, (None, None))
            b.configure(
                fg_color="transparent",
                text_color=THEME.text_secondary,
                image=ina_icon,
            )
        if label in self.nav_btns:
            _, act_icon = self._nav_icons.get(label, (None, None))
            self.nav_btns[label].configure(
                fg_color=THEME.accent,
                hover_color=THEME.accent_hover,
                text_color="white",
                image=act_icon,
            )

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
        self._set_active("RECHERCHE")
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

        title_txt = ("Recherche automatique" if self.search_mode == "auto"
                     else "Ajout manuel d'une offre")
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
        toggle = ctk.CTkFrame(header, fg_color=THEME.bg_panel_alt, corner_radius=8)
        toggle.pack(side="right")

        def mk(label, mode):
            active = (self.search_mode == mode)
            return ctk.CTkButton(
                toggle, text=label,
                height=32, width=140,
                corner_radius=6,
                fg_color=(THEME.accent if active else "transparent"),
                text_color=("white" if active else THEME.text_secondary),
                hover_color=(THEME.accent_hover if active else THEME.bg_hover),
                command=lambda m=mode: self._switch_mode(m),
                font=ctk.CTkFont(size=12, weight=("bold" if active else "normal"))
            )

        mk("Recherche auto", "auto").pack(side="left", padx=3, pady=3)
        mk("Ajout manuel", "manuel").pack(side="left", padx=3, pady=3)

    def _switch_mode(self, mode):
        self.search_mode = mode
        self.cfg.setdefault("recherche", {})["mode"] = mode
        save_config(self.cfg)
        self.show_search()

    # ── Mode AUTO ────────────────────────────────────────────
    def _render_auto(self):
        rech = self.cfg.get("recherche", {})

        filter_bar = ctk.CTkFrame(self.search_body, fg_color=THEME.bg_panel_alt, corner_radius=10)
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

        # Pagination sticky : sous les filtres, au-dessus du scroll, visible
        # seulement quand max_page > 0. Pack manuel dans _display_offres.
        self.pagination_bar = ctk.CTkFrame(
            self.search_body, fg_color=THEME.bg_panel_alt, corner_radius=8
        )
        # On NE pack PAS ici — sera packé dans _display_offres si pagination utile

        self.search_box = ctk.CTkScrollableFrame(self.search_body)
        self.search_box.pack(fill="both", expand=True, pady=(0, 10))

        # IMPORTANT : on crée la barre de boutons (et donc self.search_btn)
        # AVANT d'appeler _display_offres pour le cache. Sinon _display_offres
        # tente de configurer un widget détruit et l'exception silencieuse
        # interrompt la suite du rendu (zone vide sans boutons).
        btn_frame = ctk.CTkFrame(self.search_body, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        self.search_btn = ctk.CTkButton(
            btn_frame, text="Lancer la recherche",
            image=theme.ctk_icon(theme.icon_search, size=16, color="#FFFFFF"),
            compound="left",
            command=self.run_search, height=42, corner_radius=20,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.search_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self._searching = False

        ctk.CTkButton(
            btn_frame, text="Gérer les sources",
            command=self.show_sources_manager, height=42,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        ).pack(side="left", padx=(5, 5))

        ctk.CTkButton(
            btn_frame, text="PARAMÈTRES",
            command=self.show_settings, height=42,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_secondary
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
                state="normal", text="Lancer la recherche",
                fg_color=THEME.accent, hover_color=THEME.accent_hover
            )
            if hasattr(self, "progress_label") and self.progress_label.winfo_exists():
                self.progress_label.configure(text="Recherche annulée.")
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
            state="normal", text="Arrêter la recherche",
            fg_color=THEME.red_danger, hover_color=THEME.red_hover
        )
        for w in self.search_box.winfo_children():
            w.destroy()

        self.progress_label = ctk.CTkLabel(
            self.search_box, text="Connexion aux sources...", text_color="gray"
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

    # Nombre de cartes affichées par page dans la recherche (perf)
    SEARCH_PAGE_SIZE = 25

    def _display_offres(self, offres, error=None):
        self._searching = False
        self.search_btn.configure(
            state="normal", text="Lancer la recherche",
            fg_color=THEME.accent, hover_color=THEME.accent_hover
        )
        # Reset pagination quand on relance une recherche
        # (mais pas quand on re-applique le filtre/limite sur cache)
        if not getattr(self, "_search_keep_page", False):
            self._search_page = 0
        self._search_keep_page = False
        for w in self.search_box.winfo_children():
            w.destroy()
        # Vide aussi la barre de pagination sticky (cas error/empty)
        if hasattr(self, "pagination_bar"):
            for w in self.pagination_bar.winfo_children():
                w.destroy()
            try:
                self.pagination_bar.pack_forget()
            except Exception:
                pass

        if error:
            ctk.CTkLabel(
                self.search_box, text=f"Erreur :\n{error}",
                text_color=THEME.red_danger, justify="left", wraplength=600
            ).pack(pady=20, padx=20, anchor="w")
            return

        if not offres:
            self._last_search_offres = []
            ctk.CTkLabel(
                self.search_box,
                text="Aucune offre trouvée.\nVérifie tes sources et filtres.",
                text_color=THEME.text_muted, justify="center"
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

        action_bar = ctk.CTkFrame(self.search_box, fg_color=THEME.bg_panel_alt, corner_radius=8)
        action_bar.pack(fill="x", padx=5, pady=(5, 8))

        def _count_text(n_sel):
            if displayed_count < total_count:
                return (f"{displayed_count} / {total_count} "
                        f"offre(s) affichée(s)  —  {n_sel} sélectionnée(s)")
            return (f"{total_count} offre(s) trouvée(s)  —  "
                    f"{n_sel} sélectionnée(s)")

        count_label = ctk.CTkLabel(
            action_bar,
            text=_count_text(0),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME.green_ok
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
                messagebox.showinfo("Information", "Aucune offre sélectionnée.")
                return
            added = 0
            for i in selected_idx:
                if self._postule_buttons.get(i, {}).get("done"):
                    continue  # déjà ajoutée
                self._postuler(offres[i], silent=True, ui_idx=i)
                added += 1
            messagebox.showinfo(
                "Ajout effectué", f"{added} offre(s) ajoutée(s) aux candidatures."
            )
            _refresh_count()

        ctk.CTkButton(
            action_bar, text="Ajouter aux candidatures",
            command=_add_selected, height=32,
            fg_color=THEME.accent, hover_color=THEME.accent_hover
        ).pack(side="right", padx=10, pady=6)

        SOURCE_COLORS = {
            "france_travail":     THEME.blue_link,
            "indeed":             THEME.red_danger,
            "linkedin":           THEME.blue_link,
            "apec":               THEME.amber,
            "welcometothejungle": THEME.green_ok,
        }

        # Set des offres déjà candidates (pour griser le bouton)
        already = set()
        for c in self.cfg.get("candidatures", []):
            key = (c.get("entreprise", ""), c.get("poste", ""), c.get("url", ""))
            already.add(key)

        # Pre-création des BooleanVars pour TOUTES les offres (pas que la
        # page) — sinon "Tout sélectionner" ne marche que sur la page.
        for i, _o in enumerate(offres):
            if i not in self._offres_selection:
                self._offres_selection[i] = ctk.BooleanVar(value=False)

        # Pagination : on ne RENDER que les cartes de la page courante
        page_size = self.SEARCH_PAGE_SIZE
        max_page = max(0, (displayed_count - 1) // page_size)
        if not hasattr(self, "_search_page"):
            self._search_page = 0
        self._search_page = max(0, min(self._search_page, max_page))
        page_start = self._search_page * page_size
        page_end = min(page_start + page_size, displayed_count)

        for i in range(page_start, page_end):
            o = offres[i]
            card = ctk.CTkFrame(self.search_box, corner_radius=8)
            card.pack(fill="x", pady=4, padx=5)
            card.grid_columnconfigure(1, weight=1)

            # Case à cocher à gauche (BooleanVar déjà pré-créé)
            sel_var = self._offres_selection[i]
            ctk.CTkCheckBox(
                card, text="", variable=sel_var,
                command=_refresh_count,
                checkbox_width=20, checkbox_height=20, width=20
            ).grid(row=0, column=0, rowspan=3, padx=(12, 4), pady=8, sticky="n")

            source = o.get("source", "custom")
            badge_color = SOURCE_COLORS.get(source, THEME.statut_entretien)

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

            # Sous-ligne info : séparateur · entre les champs
            email_suffix = f"   ·   {o.get('email')}" if o.get("email") else ""
            sep = "   ·   "
            parts = [
                o.get('entreprise', ''),
                o.get('lieu', ''),
                o.get('contrat', ''),
            ]
            parts = [p for p in parts if p]
            ctk.CTkLabel(
                card,
                text=sep.join(parts) + email_suffix,
                text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
            ).grid(row=2, column=1, sticky="w", padx=4, pady=(0, 8))

            btn_col = ctk.CTkFrame(card, fg_color="transparent")
            btn_col.grid(row=0, column=2, rowspan=3, padx=12, pady=8, sticky="e")

            if o.get("url"):
                ctk.CTkButton(
                    btn_col, text="Voir l'offre", width=100, height=30,
                    fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
                    text_color=THEME.text_primary,
                    command=lambda url=o.get("url"): self._open_url(url)
                ).pack(side="left", padx=(0, 6))

            key = (o.get("entreprise", ""), o.get("titre", ""), o.get("url", ""))
            is_already = key in already
            btn = ctk.CTkButton(
                btn_col, text=("Ajoutée" if is_already else "Ajouter"),
                width=100, height=30,
                fg_color=(THEME.green_ok if is_already else THEME.accent),
                hover_color=(THEME.green_hover if is_already else THEME.accent_hover),
                state=("disabled" if is_already else "normal"),
                command=lambda off=o, ii=i: self._postuler(off, ui_idx=ii)
            )
            btn.pack(side="left")
            self._postule_buttons[i] = {"btn": btn, "done": is_already}

        # ── Pagination STICKY (entre filtres et liste, visible si besoin)
        if max_page > 0 and hasattr(self, "pagination_bar"):
            # Insère AVANT search_box (juste sous les filtres)
            try:
                self.pagination_bar.pack(
                    fill="x", pady=(0, 8), padx=0,
                    before=self.search_box
                )
            except Exception:
                self.pagination_bar.pack(fill="x", pady=(0, 8))

            def _prev():
                self._search_page = max(0, self._search_page - 1)
                self._search_keep_page = True
                self._display_offres(self._last_search_offres)

            def _next():
                self._search_page = min(max_page, self._search_page + 1)
                self._search_keep_page = True
                self._display_offres(self._last_search_offres)

            ctk.CTkButton(
                self.pagination_bar, text="← Précédent",
                command=_prev,
                state=("normal" if self._search_page > 0 else "disabled"),
                width=110, height=30, corner_radius=15,
                fg_color=THEME.bg_panel, hover_color=THEME.bg_hover,
                text_color=THEME.text_primary,
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="left", padx=(8, 4), pady=6)

            ctk.CTkLabel(
                self.pagination_bar,
                text=f"Page {self._search_page + 1} / {max_page + 1}   "
                     f"({page_start + 1}–{page_end} sur {displayed_count})",
                text_color=THEME.text_secondary,
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="left", expand=True, pady=6)

            ctk.CTkButton(
                self.pagination_bar, text="Suivant →",
                command=_next,
                state=("normal" if self._search_page < max_page else "disabled"),
                width=110, height=30, corner_radius=15,
                fg_color=THEME.bg_panel, hover_color=THEME.bg_hover,
                text_color=THEME.text_primary,
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="right", padx=(4, 8), pady=6)

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
                    text="Ajoutée", state="disabled",
                    fg_color=THEME.green_ok, hover_color=THEME.green_hover
                )
                info["done"] = True

    # ── Mode MANUEL (intégré dans Rechercher) ────────────────
    def _render_manual(self):
        # Zone import image / URL
        import_zone = ctk.CTkFrame(self.search_body, fg_color=THEME.bg_panel_alt, corner_radius=10)
        import_zone.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            import_zone, text="Importer une offre",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        # Zone OCR : image
        img_row = ctk.CTkFrame(import_zone, fg_color="transparent")
        img_row.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(img_row, text="Image :", width=80, anchor="w").pack(side="left")
        self.drop_label = ctk.CTkLabel(
            img_row,
            text="Clique ici pour sélectionner une image (OCR automatique)",
            text_color=THEME.text_muted, cursor="hand2", fg_color=THEME.bg_hover,
            corner_radius=6, anchor="w", padx=12, pady=8
        )
        self.drop_label.pack(side="left", fill="x", expand=True)
        self.drop_label.bind("<Button-1>", lambda e: self._import_image_ocr())

        # URL d'analyse
        url_row = ctk.CTkFrame(import_zone, fg_color="transparent")
        url_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(url_row, text="URL :", width=80, anchor="w").pack(side="left")
        self.manual_url_entry = ctk.CTkEntry(
            url_row, height=32, placeholder_text="https://exemple.com/offre-poste"
        )
        self.manual_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            url_row, text="Analyser la page",
            command=self._analyze_manual_url,
            height=32, width=150,
            fg_color=THEME.accent, hover_color=THEME.accent_hover
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
            btn_row, text="Ajouter aux candidatures",
            command=self._save_manual, height=42,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(
            btn_row, text="Générer lettre",
            command=self._generate_lettre_manual, height=42,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            btn_row, text="Effacer",
            command=self._clear_manual, height=42,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_secondary
        ).pack(side="left")

    def _import_image_ocr(self):
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp")]
        )
        if not path:
            return
        self.drop_label.configure(text="Analyse OCR en cours...", text_color=THEME.text_muted)

        def task():
            try:
                img = Image.open(path)
                text = pytesseract.image_to_string(img, lang="fra")
                data = self._parse_ocr(text)
                self.after(0, lambda: self._fill_manual(data))
            except Exception as e:
                err_ocr = str(e)
                self.after(0, lambda err_ocr=err_ocr: self.drop_label.configure(
                    text=f"Erreur OCR : {err_ocr}", text_color=THEME.red_danger))

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
            messagebox.showwarning("Attention", "Colle une URL d'abord.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.manual_url_entry.delete(0, "end")
            self.manual_url_entry.insert(0, url)

        self.drop_label.configure(text="Analyse de la page en cours...", text_color=THEME.text_muted)

        def task():
            try:
                from scraper import OffreScraper
                scraper = OffreScraper(self.cfg)
                data = scraper.analyze_url(url)
                if "titre" in data and "poste" not in data:
                    data["poste"] = data.pop("titre")
                self.after(0, lambda: self._fill_manual(data))
                self.after(0, lambda: self.drop_label.configure(
                    text="Page analysée — vérifie et corrige si besoin",
                    text_color=THEME.green_ok
                ))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self.drop_label.configure(
                    text=f"Erreur analyse : {err[:80]}", text_color=THEME.red_danger))

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
            text="Clique ici pour sélectionner une image (OCR automatique)",
            text_color=THEME.text_muted
        )

    def _save_manual(self):
        def get(key):
            w = self.manual_fields[key]
            if isinstance(w, ctk.CTkTextbox):
                return w.get("1.0", "end").strip()
            return w.get().strip()

        if not get("entreprise") and not get("poste"):
            messagebox.showwarning("Attention", "Remplis au moins l'entreprise ou le poste.")
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
        messagebox.showinfo("Ajout effectué", "Offre ajoutée à tes candidatures !")
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
    def _test_scrapling(self):
        """Test live : essaie d'importer Scrapling et de faire un GET réel.
        Affiche le résultat dans le label de statut."""
        if not hasattr(self, "_scrapling_status_label"):
            return
        self._scrapling_status_label.configure(
            text="Test en cours...", text_color=THEME.text_muted)

        def task():
            try:
                from scrapling import Fetcher
                r = Fetcher.get("https://httpbin.org/get", timeout=10,
                                stealthy_headers=True)
                status = r.status
                ua = ""
                try:
                    import json as _j
                    body = _j.loads(r.html_content or "{}")
                    ua = body.get("headers", {}).get("User-Agent", "")[:40]
                except Exception:
                    pass
                msg = f"OK — HTTP {status}, UA = {ua or 'inconnu'}"
                color = THEME.green_ok
            except ImportError as e:
                msg = f"ÉCHEC import : {e}"
                color = THEME.red_danger
            except Exception as e:
                msg = f"ÉCHEC requête : {type(e).__name__} — {str(e)[:60]}"
                color = THEME.red_danger
            self.after(0, lambda: self._scrapling_status_label.configure(
                text=msg, text_color=color))

        threading.Thread(target=task, daemon=True).start()

    # Mapping source_key → domain (pour les logos via favicons Google)
    _SOURCE_DOMAINS = {
        "france_travail":     "francetravail.fr",
        "indeed":             "indeed.com",
        "linkedin":           "linkedin.com",
        "apec":               "apec.fr",
        "welcometothejungle": "welcometothejungle.com",
        "hellowork":          "hellowork.com",
        "talent":             "talent.com",
        "jooble":             "jooble.org",
        "adzuna":             "adzuna.com",
    }

    def _fetch_logo(self, domain, size=32):
        """Récupère le favicon d'un domaine via Google s2 + cache local.
        Retourne un CTkImage prêt à utiliser, ou None si échec."""
        try:
            logos_dir = app_paths.data_dir() / "logos"
            logos_dir.mkdir(exist_ok=True)
            cache_path = logos_dir / f"{domain}_{size}.png"

            # Charge depuis cache si existe
            if cache_path.exists() and cache_path.stat().st_size > 100:
                img = Image.open(cache_path).convert("RGBA")
            else:
                # Download via Google s2 (stable, gratuit, pas de clé)
                import urllib.request, ssl as _ssl
                try:
                    import certifi as _crt
                    ctx = _ssl.create_default_context(cafile=_crt.where())
                except Exception:
                    ctx = _ssl.create_default_context()
                url = (f"https://www.google.com/s2/favicons"
                       f"?domain={domain}&sz={size * 2}")
                req = urllib.request.Request(
                    url, headers={"User-Agent": "CandidatureBot/1.0"}
                )
                with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
                    data = r.read()
                cache_path.write_bytes(data)
                from io import BytesIO
                img = Image.open(BytesIO(data)).convert("RGBA")

            # Resize anti-aliasé à la taille demandée
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            return ctk.CTkImage(light_image=img, dark_image=img,
                                size=(size, size))
        except Exception as e:
            print(f"[logo] {domain}: {e}")
            return None

    def show_sources_manager(self):
        win = ctk.CTkToplevel(self)
        win.title("Gérer les sources de recherche")
        win.geometry("600x650")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 300
        py = self.winfo_y() + self.winfo_height() // 2 - 325
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="SOURCES DE RECHERCHE",
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
            "france_travail":     ("France Travail",      "API officielle — Client ID/Secret requis (gratuit)"),
            "indeed":             ("Indeed",              "Scraping via Scrapling — débloqué (TLS Chrome)"),
            "linkedin":           ("LinkedIn",            "Scraping — fonctionne, ~100 résultats max"),
            "apec":               ("APEC",                "API publique — cadres (endpoint instable)"),
            "welcometothejungle": ("Welcome to the Jungle", "API publique — startups (clé Algolia volatile)"),
            "hellowork":          ("HelloWork",           "Scraping — marché français, sans clé"),
            "talent":             ("Talent.com",          "Meta-aggregator — beaucoup d'offres FR"),
            "jooble":             ("Jooble",              "Meta-aggregator — agrège plusieurs sources"),
            "adzuna":             ("Adzuna",              "API gratuite (1000 req/mois) — clé requise"),
        }

        self.source_switches = {}

        ctk.CTkLabel(
            scroll, text="Plateformes intégrées",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 8))

        for key, (label, desc) in BUILTIN.items():
            row = ctk.CTkFrame(scroll, fg_color=THEME.bg_panel_alt, corner_radius=8)
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(1, weight=1)

            # Logo du site (favicon Google, caché en local)
            domain = self._SOURCE_DOMAINS.get(key, "")
            logo_lbl = ctk.CTkLabel(row, text="", width=40)
            logo_lbl.grid(row=0, column=0, padx=(12, 4), pady=8)
            if domain:
                # Téléchargement en thread pour ne pas bloquer l'UI
                def _load_logo(d=domain, lbl=logo_lbl):
                    img = self._fetch_logo(d, size=32)
                    if img is not None:
                        try:
                            if lbl.winfo_exists():
                                self.after(0, lambda: lbl.configure(image=img))
                        except Exception:
                            pass
                threading.Thread(target=_load_logo, daemon=True).start()

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=1, sticky="w", padx=(4, 12), pady=8)
            ctk.CTkLabel(info, text=label, font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            ctk.CTkLabel(info, text=desc, text_color="gray",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")

            sw = ctk.CTkSwitch(row, text="")
            if sources.get(key, False):
                sw.select()
            else:
                sw.deselect()
            sw.grid(row=0, column=2, padx=(0, 12))
            self.source_switches[key] = sw

        # Bouton "Tester Scrapling" : vérifie que la lib HTTP fonctionne dans le bundle
        test_row = ctk.CTkFrame(scroll, fg_color="transparent")
        test_row.pack(fill="x", pady=(12, 4))
        ctk.CTkButton(
            test_row, text="Tester Scrapling",
            command=self._test_scrapling,
            height=32, width=180, corner_radius=16,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")
        self._scrapling_status_label = ctk.CTkLabel(
            test_row, text="", text_color=THEME.text_muted,
            font=ctk.CTkFont(size=11)
        )
        self._scrapling_status_label.pack(side="left", padx=(10, 0))

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
                row = ctk.CTkFrame(self.custom_frame, fg_color=THEME.bg_panel_alt, corner_radius=8)
                row.pack(fill="x", pady=3)
                row.grid_columnconfigure(0, weight=1)

                ctk.CTkLabel(
                    row,
                    text=site.get('nom', 'Site ' + str(i+1)),
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
                    action_frame, text="Modifier", width=70, height=28,
                    fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
                    text_color=THEME.text_primary,
                    command=lambda idx=i: edit_custom(idx)
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    action_frame, text="X", width=32, height=28,
                    fg_color=THEME.bg_panel_alt, hover_color=THEME.red_danger,
                    text_color=THEME.text_primary,
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
                text="Indique un user/password si le site en demande.\n"
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
            w, entries = _custom_form_window("Nouveau site de recherche")
            def do_add():
                new_site = {k: e.get().strip() for k, e in entries.items()}
                if not new_site.get("nom") or not new_site.get("url_base"):
                    messagebox.showwarning("Attention",
                        "Remplis au moins le nom et l'URL de recherche.",
                        parent=w)
                    return
                custom_sources.append(new_site)
                save_config(self.cfg)
                refresh_custom()
                w.destroy()
            ctk.CTkButton(w, text="Ajouter", command=do_add, height=38).pack(pady=15)
            bring_to_front(w)

        def edit_custom(idx):
            site = custom_sources[idx]
            w, entries = _custom_form_window(
                f"Modifier — {site.get('nom','Site')}", existing=site)
            def do_save():
                for k, e in entries.items():
                    custom_sources[idx][k] = e.get().strip()
                save_config(self.cfg)
                refresh_custom()
                w.destroy()
            ctk.CTkButton(w, text="Sauvegarder", command=do_save, height=38).pack(pady=15)
            bring_to_front(w)

        def delete_custom(idx):
            if messagebox.askyesno("Supprimer ?",
                                   f"Supprimer « {custom_sources[idx].get('nom','ce site')} » ?",
                                   parent=win):
                custom_sources.pop(idx)
                save_config(self.cfg)
                refresh_custom()

        ctk.CTkButton(
            scroll, text="Ajouter un site personnalisé",
            command=add_custom, height=36,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        ).pack(anchor="w", pady=(8, 0))

        refresh_custom()

        def save_sources():
            for key, sw in self.source_switches.items():
                sources[key] = sw.get() == 1
            save_config(self.cfg)
            messagebox.showinfo("Sauvegardé", "Sources sauvegardées !", parent=win)
            win.destroy()
            self.show_search()

        ctk.CTkButton(
            win, text="Sauvegarder", command=save_sources, height=42,
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
        win.title("Génération lettre de motivation")
        win.geometry("780x780")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 390
        py = self.winfo_y() + self.winfo_height() // 2 - 390
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win,
            text=f"{offre.get('titre') or offre.get('poste','?')} — {offre.get('entreprise','?')}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(18, 6), padx=20, anchor="w")

        # ── Sélecteur de ton (cumulables) ────────────────────
        ton_bar = ctk.CTkFrame(win, fg_color=THEME.bg_panel_alt, corner_radius=8)
        ton_bar.pack(fill="x", padx=20, pady=(0, 6))
        ctk.CTkLabel(
            ton_bar, text="Ton (cumulable) :",
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
        instr_bar = ctk.CTkFrame(win, fg_color=THEME.bg_panel_alt, corner_radius=8)
        instr_bar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(
            instr_bar, text="Instructions libres (optionnel) :",
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
            text_area.insert("1.0", "Génération en cours...")

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
                err_msg = f"Erreur : {e}\n\n{traceback.format_exc()}"
                win.after(0, lambda err_msg=err_msg: _set_text(err_msg))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 18))

        ctk.CTkButton(
            btn_row, text="Générer avec ces réglages",
            command=lambda: (text_area.delete("1.0", "end"),
                             text_area.insert("1.0", "Génération en cours..."),
                             threading.Thread(target=generate, daemon=True).start()),
            fg_color=THEME.accent, hover_color=THEME.accent_hover, height=38
        ).pack(side="left", padx=(0, 5))

        def copy_text():
            txt = text_area.get("1.0", "end").strip()
            win.clipboard_clear()
            win.clipboard_append(txt)
            messagebox.showinfo("Copié", "Copié !", parent=win)

        ctk.CTkButton(
            btn_row, text="Copier",
            command=copy_text, height=38,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="Sauvegarder dans profil",
            command=lambda: self._save_lettre_to_profil(
                text_area.get("1.0", "end").strip(), win),
            height=38,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        ).pack(side="left", padx=(0, 5))

        # Si on vient d'une candidature, permet une sauvegarde liée à celle-ci
        if idx is not None:
            def _save_to_candidature():
                txt = text_area.get("1.0", "end").strip()
                if not txt or txt.startswith("Génération") or txt.startswith("Erreur"):
                    messagebox.showwarning("Attention", "Rien à sauvegarder.", parent=win)
                    return
                try:
                    self.cfg["candidatures"][idx]["lettre"] = txt
                    save_config(self.cfg)
                    messagebox.showinfo("Sauvegardé", "Lettre sauvegardée pour cette candidature !", parent=win)
                    if on_save:
                        on_save(txt)
                    win.destroy()
                except (IndexError, KeyError) as e:
                    messagebox.showerror("Erreur", f"Impossible de sauvegarder : {e}", parent=win)

            ctk.CTkButton(
                btn_row, text="Lier à cette candidature",
                command=_save_to_candidature,
                fg_color=THEME.green_ok, hover_color=THEME.green_hover, height=38
            ).pack(side="left")

        # Génère automatiquement uniquement si pas de lettre préexistante
        if not existing_lettre:
            threading.Thread(target=generate, daemon=True).start()
        bring_to_front(win)

    def _save_lettre_to_profil(self, txt, win):
        self.cfg.setdefault("profil", {})["lettre_type"] = txt
        save_config(self.cfg)
        messagebox.showinfo("Sauvegardé", "Lettre sauvegardée dans ton profil !", parent=win)

    # ══════════════════════════════════════════════════════════
    # 📋 CANDIDATURES
    # ══════════════════════════════════════════════════════════
    def show_tracker(self):
        self._set_active("CANDIDATURES")
        self._remember_tab("tracker")
        self._clear_main()

        # En-tête
        ctk.CTkLabel(
            self.main, text="MES CANDIDATURES",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", pady=(0, 4))

        candidatures = self.cfg.get("candidatures", [])
        stats = {}
        for c in candidatures:
            s = c.get("statut", "À envoyer")
            stats[s] = stats.get(s, 0) + 1

        # Sous-titre stats compactes
        substats = f"{len(candidatures)} candidatures"
        if stats.get("À envoyer"):
            substats += f"  ·  {stats['À envoyer']} à envoyer"
        if stats.get("Entretien"):
            substats += f"  ·  {stats['Entretien']} entretien"
        ctk.CTkLabel(
            self.main, text=substats,
            text_color=THEME.text_muted, font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(0, 14))

        # ── Filtres : recherche + statut + lieu ────────────────
        self._tracker_search_var = ctk.StringVar(value="")
        self._tracker_filter_statut_var = ctk.StringVar(
            value=self.cfg.get("ui", {}).get("tracker_filter", "Tous"))
        self._tracker_filter_lieu_var = ctk.StringVar(value="Tous lieux")

        filters_row = ctk.CTkFrame(self.main, fg_color="transparent")
        filters_row.pack(fill="x", pady=(0, 10))

        search_entry = ctk.CTkEntry(
            filters_row, textvariable=self._tracker_search_var,
            placeholder_text="Rechercher entreprise ou poste...",
            height=36
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _on_filter_change(_=None):
            self.cfg.setdefault("ui", {})["tracker_filter"] = self._tracker_filter_statut_var.get()
            save_config(self.cfg)
            self._refresh_tracker_list(scroll_frame)

        # Build options statut with counts
        stat_opts = ["Tous"]
        for s in ["À envoyer", "Envoyée", "Relancée", "Entretien", "Refusée", "Acceptée"]:
            n = stats.get(s, 0)
            stat_opts.append(f"{s}" + (f" ({n})" if n else ""))

        ctk.CTkOptionMenu(
            filters_row, variable=self._tracker_filter_statut_var,
            values=stat_opts, width=170, height=36,
            command=_on_filter_change,
            fg_color=THEME.bg_panel_alt, button_color=THEME.bg_panel_alt,
            button_hover_color=THEME.bg_hover, text_color=THEME.text_primary,
            dropdown_fg_color=THEME.bg_panel_alt
        ).pack(side="left", padx=(0, 8))

        # Build options lieu (distinct values)
        lieux = sorted({c.get("lieu", "").strip() for c in candidatures
                        if c.get("lieu")} | {"Tous lieux"})
        ctk.CTkOptionMenu(
            filters_row, variable=self._tracker_filter_lieu_var,
            values=lieux if len(lieux) > 1 else ["Tous lieux"],
            width=170, height=36,
            command=_on_filter_change,
            fg_color=THEME.bg_panel_alt, button_color=THEME.bg_panel_alt,
            button_hover_color=THEME.bg_hover, text_color=THEME.text_primary,
            dropdown_fg_color=THEME.bg_panel_alt
        ).pack(side="left")

        # Recherche : re-render à chaque keystroke (debounce via after)
        self._tracker_search_after = None
        def _on_search_change(*_args):
            if self._tracker_search_after:
                self.after_cancel(self._tracker_search_after)
            self._tracker_search_after = self.after(
                250, lambda: self._refresh_tracker_list(scroll_frame))
        self._tracker_search_var.trace_add("write", _on_search_change)

        # ── Bulk action bar ────────────────────────────────────
        self._tracker_selection = {}
        self._tracker_page = 0
        action_row = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel_alt, corner_radius=8)
        action_row.pack(fill="x", pady=(0, 8))

        self._tracker_select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            action_row, text="Tout sélectionner",
            variable=self._tracker_select_all_var,
            command=lambda: self._tracker_toggle_all(scroll_frame),
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=12, pady=8)

        self._tracker_sel_count_label = ctk.CTkLabel(
            action_row, text="0 sélectionnée(s)",
            text_color=THEME.text_muted, font=ctk.CTkFont(size=11)
        )
        self._tracker_sel_count_label.pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            action_row, text="Supprimer",
            image=theme.ctk_icon(theme.icon_trash, size=14, color="#FFFFFF"),
            compound="left",
            command=lambda: self._tracker_delete_selected(scroll_frame),
            height=30, width=130, corner_radius=15,
            fg_color=THEME.red_danger, hover_color=THEME.red_hover,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="right", padx=(4, 10), pady=6)

        ctk.CTkButton(
            action_row, text="Préparer dossiers",
            image=theme.ctk_icon(theme.icon_folder, size=14, color="#FFFFFF"),
            compound="left",
            command=lambda: self._prepare_application_folder_bulk(scroll_frame),
            height=30, width=160, corner_radius=15,
            fg_color=THEME.bg_panel, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="right", padx=4, pady=6)

        ctk.CTkButton(
            action_row, text="Exporter CSV",
            image=theme.ctk_icon(theme.icon_download, size=14, color="#FFFFFF"),
            compound="left",
            command=self._export_csv,
            height=30, width=130, corner_radius=15,
            fg_color=THEME.bg_panel, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="right", padx=4, pady=6)

        # ── En-tête tableau ─────────────────────────────────────
        thead = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel, corner_radius=6)
        thead.pack(fill="x", pady=(0, 2))
        thead.grid_columnconfigure(2, weight=1)
        col_header_kw = dict(text_color=THEME.text_muted,
                             font=ctk.CTkFont(size=10, weight="bold"))
        ctk.CTkLabel(thead, text="", width=32, **col_header_kw)\
            .grid(row=0, column=0, padx=10, pady=8)
        ctk.CTkLabel(thead, text="STATUT", width=120, anchor="w", **col_header_kw)\
            .grid(row=0, column=1, padx=4, pady=8, sticky="w")
        ctk.CTkLabel(thead, text="ENTREPRISE / POSTE", anchor="w", **col_header_kw)\
            .grid(row=0, column=2, padx=4, pady=8, sticky="w")
        ctk.CTkLabel(thead, text="LIEU", width=140, anchor="w", **col_header_kw)\
            .grid(row=0, column=3, padx=4, pady=8, sticky="w")
        ctk.CTkLabel(thead, text="LIEN", width=80, **col_header_kw)\
            .grid(row=0, column=4, padx=4, pady=8)

        # ── Scrollable rows ─────────────────────────────────────
        scroll_frame = ctk.CTkScrollableFrame(self.main, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True)
        self._refresh_tracker_list(scroll_frame)

    # Palette des couleurs de statut (utilisée à plusieurs endroits)
    STATUT_COLORS = {
        "À envoyer": THEME.statut_a_envoyer,
        "Envoyée":   THEME.statut_envoyee,
        "Relancée":  THEME.statut_relancee,
        "Entretien": THEME.statut_entretien,
        "Refusée":   THEME.statut_refusee,
        "Acceptée":  THEME.statut_acceptee,
    }

    @staticmethod
    def _statut_hover(color):
        """Retourne une variante légèrement plus claire pour le hover."""
        hover = {
            THEME.statut_a_envoyer: "#95a5a6",
            THEME.statut_envoyee:   "#7bb8df",
            THEME.statut_relancee:  "#f8c570",
            THEME.statut_entretien: "#b178c2",
            THEME.statut_refusee:   THEME.red_hover,
            THEME.statut_acceptee:  THEME.green_hover,
        }
        return hover.get(color, color)

    # Nombre max de cartes à rendre par page (perf : Tk devient lent au-delà)
    TRACKER_PAGE_SIZE = 30

    def _refresh_tracker_list(self, container):
        for w in container.winfo_children():
            w.destroy()

        candidatures = self.cfg.get("candidatures", [])
        STATUTS = ["À envoyer", "Envoyée", "Relancée", "Entretien", "Refusée", "Acceptée"]
        STATUT_COLORS = self.STATUT_COLORS

        # Récupère les filtres
        search_q = (getattr(self, "_tracker_search_var", None).get().strip().lower()
                    if hasattr(self, "_tracker_search_var") else "")
        statut_raw = (getattr(self, "_tracker_filter_statut_var", None).get()
                      if hasattr(self, "_tracker_filter_statut_var") else "Tous")
        # Retire le " (N)" éventuel à la fin
        statut_f = statut_raw.split(" (")[0]
        lieu_f = (getattr(self, "_tracker_filter_lieu_var", None).get()
                  if hasattr(self, "_tracker_filter_lieu_var") else "Tous lieux")

        # Filtrage
        def _match(c):
            if statut_f != "Tous" and c.get("statut", "À envoyer") != statut_f:
                return False
            if lieu_f and lieu_f != "Tous lieux" and c.get("lieu", "") != lieu_f:
                return False
            if search_q:
                blob = " ".join([
                    c.get("entreprise", ""), c.get("poste", ""),
                    c.get("titre", ""), c.get("lieu", "")
                ]).lower()
                if search_q not in blob:
                    return False
            return True

        filtered = [
            (len(candidatures) - 1 - i, c)
            for i, c in enumerate(reversed(candidatures))
            if _match(c)
        ]

        if not filtered:
            ctk.CTkLabel(
                container,
                text="Aucune candidature ne correspond aux filtres.",
                text_color=THEME.text_muted
            ).pack(pady=40)
            self._tracker_update_selection_count()
            return

        # Pagination
        total = len(filtered)
        page_size = self.TRACKER_PAGE_SIZE
        max_page = max(0, (total - 1) // page_size)
        if not hasattr(self, "_tracker_page"):
            self._tracker_page = 0
        self._tracker_page = max(0, min(self._tracker_page, max_page))
        page = self._tracker_page
        start = page * page_size
        end = min(start + page_size, total)
        page_items = filtered[start:end]

        if not hasattr(self, "_tracker_selection"):
            self._tracker_selection = {}
        valid_indices = {real_i for real_i, _ in filtered}
        for k in list(self._tracker_selection.keys()):
            if k not in valid_indices:
                self._tracker_selection.pop(k, None)

        # ── Render des table rows compactes ─────────────────────
        for real_i, c in page_items:
            statut = c.get("statut", "À envoyer")
            statut_color = STATUT_COLORS.get(statut, THEME.statut_a_envoyer)

            row = ctk.CTkFrame(container, fg_color=THEME.bg_panel_alt, corner_radius=6)
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(2, weight=1)

            # Col 0 — checkbox
            sel_var = self._tracker_selection.get(real_i)
            if sel_var is None:
                sel_var = ctk.BooleanVar(value=False)
                self._tracker_selection[real_i] = sel_var
            ctk.CTkCheckBox(
                row, text="", variable=sel_var, width=22,
                checkbox_width=18, checkbox_height=18,
                command=self._tracker_update_selection_count
            ).grid(row=0, column=0, padx=(10, 0), pady=10)

            # Col 1 — dropdown statut (compact, couleur du statut)
            statut_var = ctk.StringVar(value=statut)
            statut_menu = ctk.CTkOptionMenu(
                row, variable=statut_var, values=STATUTS, width=108, height=26,
                fg_color=statut_color, button_color=statut_color,
                button_hover_color=self._statut_hover(statut_color),
                text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                dropdown_font=ctk.CTkFont(size=11)
            )
            statut_menu.grid(row=0, column=1, padx=4, pady=6)

            def _on_change(val, idx=real_i, menu=statut_menu, rw=row, container_=container):
                self._update_statut(idx, val)
                new_color = STATUT_COLORS.get(val, THEME.statut_a_envoyer)
                menu.configure(
                    fg_color=new_color, button_color=new_color,
                    button_hover_color=self._statut_hover(new_color),
                )
                cur_filter = self._tracker_filter_statut_var.get().split(" (")[0]
                if cur_filter != "Tous" and cur_filter != val:
                    self._refresh_tracker_list(container_)
            statut_menu.configure(command=_on_change)

            # Col 2 — entreprise / poste (click ouvre workflow)
            info = ctk.CTkFrame(row, fg_color="transparent", cursor="hand2")
            info.grid(row=0, column=2, sticky="ew", padx=4, pady=6)
            ent = c.get('entreprise', '—')
            poste = c.get('poste') or c.get('titre', '—')
            ent_lbl = ctk.CTkLabel(
                info, text=ent,
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w", cursor="hand2"
            )
            ent_lbl.pack(side="left", padx=(0, 6))
            poste_lbl = ctk.CTkLabel(
                info, text=f"— {poste}",
                text_color=THEME.text_secondary, font=ctk.CTkFont(size=12),
                anchor="w", cursor="hand2"
            )
            poste_lbl.pack(side="left")

            # Col 3 — lieu (cliquable aussi)
            lieu_lbl = ctk.CTkLabel(
                row, text=c.get('lieu', '—'),
                text_color=THEME.text_muted, font=ctk.CTkFont(size=12),
                anchor="w", width=140, cursor="hand2"
            )
            lieu_lbl.grid(row=0, column=3, sticky="w", padx=4, pady=6)

            # ── Click uniquement entre dropdown statut et bouton Voir ──
            # (info + lieu seulement, PAS la row entière)
            _click = lambda _e, i=real_i: self._open_candidature_workflow(i)
            for w in (info, ent_lbl, poste_lbl, lieu_lbl):
                w.bind("<Button-1>", _click)
            # Effet hover : highlight UNIQUEMENT la zone cliquable
            def _enter(_e, rw=row): rw.configure(fg_color=THEME.bg_hover)
            def _leave(_e, rw=row): rw.configure(fg_color=THEME.bg_panel_alt)
            for w in (info, ent_lbl, poste_lbl, lieu_lbl):
                w.bind("<Enter>", _enter, add="+")
                w.bind("<Leave>", _leave, add="+")

            # Col 4 — bouton "Voir" (lien direct)
            if c.get("url"):
                ctk.CTkButton(
                    row, text="Voir",
                    image=theme.ctk_icon(theme.icon_external, size=12,
                                         color=THEME.blue_link),
                    compound="left",
                    width=72, height=28,
                    fg_color=THEME.bg_panel, hover_color=THEME.bg_hover,
                    text_color=THEME.blue_link,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda url=c["url"]: self._open_url(url)
                ).grid(row=0, column=4, padx=(4, 10), pady=6)
            else:
                ctk.CTkLabel(
                    row, text="—",
                    text_color=THEME.text_muted, font=ctk.CTkFont(size=11),
                    width=72
                ).grid(row=0, column=4, padx=(4, 10), pady=6)

        # ── Footer pagination ────────────────────────────────────
        if max_page > 0:
            pager = ctk.CTkFrame(container, fg_color="transparent")
            pager.pack(fill="x", pady=(8, 4))

            ctk.CTkButton(
                pager, text="← Précédent",
                command=lambda: self._tracker_change_page(container, -1),
                state=("normal" if page > 0 else "disabled"),
                width=110, height=30,
                fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
                text_color=THEME.text_primary
            ).pack(side="left", padx=(8, 4))

            ctk.CTkLabel(
                pager,
                text=f"Page {page + 1} / {max_page + 1}  "
                     f"({start + 1}–{end} sur {total})",
                text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
            ).pack(side="left", expand=True)

            ctk.CTkButton(
                pager, text="Suivant →",
                command=lambda: self._tracker_change_page(container, +1),
                state=("normal" if page < max_page else "disabled"),
                width=110, height=30,
                fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
                text_color=THEME.text_primary
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
                    text_color=(THEME.green_ok if count > 0 else THEME.text_muted)
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
            messagebox.showinfo("Information", "Aucune candidature sélectionnée.")
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
        messagebox.showinfo("Suppression", f"{len(selected_ids)} candidature(s) supprimée(s).")

    def _update_statut(self, idx, val):
        self.cfg["candidatures"][idx]["statut"] = val
        save_config(self.cfg)

    def _delete_candidature(self, idx, container):
        if messagebox.askyesno("Supprimer ?", "Supprimer cette candidature ?"):
            self.cfg["candidatures"].pop(idx)
            save_config(self.cfg)
            self._refresh_tracker_list(container)

    # ════════════════════════════════════════════════════════════
    # WORKFLOW FULLSCREEN — 3 étapes (Lettre → Mail → Envoi)
    # ════════════════════════════════════════════════════════════
    def _open_candidature_workflow(self, idx):
        """Ouvre une fenêtre modale taille app : workflow lettre/mail/envoi."""
        candidatures = self.cfg.get("candidatures", [])
        if not (0 <= idx < len(candidatures)):
            return
        offre = candidatures[idx]

        # Anti-doublon
        existing = getattr(self, "_workflow_win", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify(); existing.lift(); existing.focus_force()
                    return
            except Exception:
                pass

        win = ctk.CTkToplevel(self)
        self._workflow_win = win
        win.title("Candidature")
        # Taille = même que l'app, centrée
        self.update_idletasks()
        w = max(self.winfo_width(), 1000)
        h = max(self.winfo_height(), 700)
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW",
                     lambda: (setattr(self, "_workflow_win", None), win.destroy()))

        # ── État interne ───────────────────────────────────────
        try:
            import tones as _tones
            default_tone = _tones.default_tone()
            tones_list = _tones.list_tones()
        except Exception:
            default_tone = "classique"
            tones_list = [("classique", "Classique", "")]

        wf_state = {
            "idx": idx,
            "step": 1,
            "tone": default_tone,
            "lettre": "",
            "mail": "",
            "dest_email": (offre.get("email") or "").strip(),
        }

        # ── Header ─────────────────────────────────────────────
        header = ctk.CTkFrame(win, fg_color=THEME.bg_panel, height=70)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        h_inner = ctk.CTkFrame(header, fg_color="transparent")
        h_inner.pack(side="left", padx=20, pady=12, fill="y")
        ent = offre.get('entreprise', '—')
        poste = offre.get('poste') or offre.get('titre', '—')
        ctk.CTkLabel(
            h_inner, text=f"{ent} — {poste}",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            h_inner,
            text=f"{offre.get('lieu', '—')}  ·  {offre.get('source', '—')}"
                 f"  ·  {offre.get('statut', 'À envoyer')}",
            text_color=THEME.text_muted, font=ctk.CTkFont(size=11)
        ).pack(anchor="w", pady=(2, 0))
        # Close
        ctk.CTkButton(
            header, text="",
            image=theme.ctk_icon(theme.icon_close, size=18, color=THEME.text_secondary),
            width=36, height=36, corner_radius=18,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.red_danger,
            command=lambda: (setattr(self, "_workflow_win", None), win.destroy())
        ).pack(side="right", padx=20)

        # ── Stepper ─────────────────────────────────────────────
        stepper = ctk.CTkFrame(win, fg_color=THEME.bg_panel, height=60)
        stepper.pack(fill="x")
        stepper.pack_propagate(False)
        step_labels = ["Lettre", "Mail", "Envoi"]
        step_widgets = []
        stepper_inner = ctk.CTkFrame(stepper, fg_color="transparent")
        stepper_inner.pack(expand=True, pady=14)
        for i, lbl in enumerate(step_labels, 1):
            sframe = ctk.CTkFrame(stepper_inner, fg_color="transparent")
            sframe.pack(side="left", padx=4)
            num_lbl = ctk.CTkLabel(
                sframe, text=str(i), width=28, height=28,
                fg_color=THEME.bg_panel_alt, text_color=THEME.text_muted,
                corner_radius=14,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            num_lbl.pack(side="left", padx=(0, 6))
            txt_lbl = ctk.CTkLabel(
                sframe, text=lbl, text_color=THEME.text_muted,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            txt_lbl.pack(side="left")
            step_widgets.append((num_lbl, txt_lbl))
            if i < len(step_labels):
                ctk.CTkFrame(stepper_inner, fg_color=THEME.border,
                             width=40, height=2).pack(side="left", padx=6)

        def _update_stepper():
            for i, (n, t) in enumerate(step_widgets, 1):
                if i < wf_state["step"]:
                    n.configure(fg_color=THEME.green_ok, text_color="white", text="✓")
                    t.configure(text_color=THEME.text_primary)
                elif i == wf_state["step"]:
                    n.configure(fg_color=THEME.accent, text_color="white", text=str(i))
                    t.configure(text_color=THEME.text_primary)
                else:
                    n.configure(fg_color=THEME.bg_panel_alt,
                                text_color=THEME.text_muted, text=str(i))
                    t.configure(text_color=THEME.text_muted)

        # ── Body ───────────────────────────────────────────────
        body = ctk.CTkFrame(win, fg_color=THEME.bg_panel_alt)
        body.pack(fill="both", expand=True, side="top")

        # ── Footer (navigation) ────────────────────────────────
        footer = ctk.CTkFrame(win, fg_color=THEME.bg_panel, height=70)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # On va re-render footer aussi à chaque étape
        def _clear(parent):
            for w in parent.winfo_children():
                w.destroy()

        def _render():
            _clear(body); _clear(footer); _update_stepper()
            if wf_state["step"] == 1:
                self._wf_step1_lettre(body, footer, wf_state, tones_list, _render, win)
            elif wf_state["step"] == 2:
                self._wf_step2_mail(body, footer, wf_state, _render, win)
            elif wf_state["step"] == 3:
                self._wf_step3_envoi(body, footer, wf_state, _render, win)

        _render()
        bring_to_front(win)

    def _wf_step1_lettre(self, body, footer, st, tones_list, render, win):
        """Étape 1 : choix du ton + génération + édition de la lettre."""
        wrap = ctk.CTkScrollableFrame(body, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            wrap, text="1. Lettre de motivation",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            wrap, text="Choisis le ton, génère via IA, modifie si besoin.",
            text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(0, 14))

        # Sélecteur de ton (4 cards)
        ctk.CTkLabel(
            wrap, text="TON DE LA LETTRE",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(anchor="w", pady=(0, 8))

        tones_row = ctk.CTkFrame(wrap, fg_color="transparent")
        tones_row.pack(fill="x", pady=(0, 14))
        TONE_ICONS = {
            "classique": theme.icon_book,
            "dynamique": theme.icon_bolt,
            "creatif":   theme.icon_bulb,
            "direct":    theme.icon_target,
        }
        tone_cards = {}
        def _on_tone(key):
            st["tone"] = key
            for k, card in tone_cards.items():
                if k == key:
                    card.configure(border_color=THEME.accent,
                                   fg_color=THEME.bg_panel)
                else:
                    card.configure(border_color=THEME.border,
                                   fg_color=THEME.bg_panel)
        for key, label, desc in tones_list:
            card = ctk.CTkFrame(
                tones_row, fg_color=THEME.bg_panel,
                border_width=2, border_color=(THEME.accent if key == st["tone"] else THEME.border),
                corner_radius=10
            )
            card.pack(side="left", padx=4, expand=True, fill="both")
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(padx=12, pady=10, fill="both")
            icon_fn = TONE_ICONS.get(key, theme.icon_book)
            ctk.CTkLabel(inner, text="",
                         image=theme.ctk_icon(icon_fn, size=22,
                                              color=THEME.text_primary)
            ).pack(anchor="w", pady=(0, 4))
            ctk.CTkLabel(inner, text=label,
                         font=ctk.CTkFont(size=13, weight="bold")
            ).pack(anchor="w")
            ctk.CTkLabel(inner, text=desc,
                         text_color=THEME.text_muted, font=ctk.CTkFont(size=10),
                         wraplength=180, justify="left"
            ).pack(anchor="w", pady=(2, 0))
            # Click anywhere on card
            for w in [card, inner] + list(inner.winfo_children()):
                w.bind("<Button-1>", lambda _e, k=key: _on_tone(k))
            tone_cards[key] = card

        # Zone de texte de la lettre
        lettre_box = ctk.CTkTextbox(wrap, height=280,
                                    fg_color=THEME.bg_panel,
                                    font=ctk.CTkFont(size=12),
                                    wrap="word")
        lettre_box.pack(fill="both", expand=True, pady=(8, 8))
        if st.get("lettre"):
            lettre_box.insert("1.0", st["lettre"])
        self._isolate_textbox_scroll(lettre_box)

        # Indicateur de progression visible (spinner Braille + texte)
        loader_row = ctk.CTkFrame(wrap, fg_color="transparent", height=24)
        loader_row.pack(fill="x", pady=(2, 0))
        loader_row.pack_propagate(False)
        spinner = ctk.CTkLabel(loader_row, text="",
                               text_color=THEME.accent,
                               font=ctk.CTkFont(size=14, weight="bold"))
        spinner.pack(side="left")
        status_lbl = ctk.CTkLabel(loader_row, text="",
                                  text_color=THEME.text_muted,
                                  font=ctk.CTkFont(size=11))
        status_lbl.pack(side="left", padx=(8, 0))

        FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        st.setdefault("_step1_spinning", False)
        st.setdefault("_step1_spin_idx", 0)

        def _spin_tick():
            if not st["_step1_spinning"]:
                return
            try:
                if not spinner.winfo_exists():
                    return
                spinner.configure(text=FRAMES[st["_step1_spin_idx"] % len(FRAMES)])
                st["_step1_spin_idx"] += 1
                self.after(80, _spin_tick)
            except Exception:
                pass

        # Refs pour pouvoir disable pendant la gen
        regen_btn = {}
        next_btn = {}
        cancel_btn = {}

        def _set_busy(busy):
            st["_step1_spinning"] = busy
            if busy:
                status_lbl.configure(text="Génération en cours…",
                                     text_color=THEME.accent)
                _spin_tick()
                try:
                    lettre_box.configure(state="disabled",
                                         fg_color=THEME.bg_panel_alt)
                except Exception:
                    pass
                for b in (regen_btn.get("w"), next_btn.get("w"), cancel_btn.get("w")):
                    if b is not None:
                        try: b.configure(state="disabled")
                        except Exception: pass
            else:
                spinner.configure(text="")
                status_lbl.configure(text="✓ Généré",
                                     text_color=THEME.green_ok)
                try:
                    lettre_box.configure(state="normal",
                                         fg_color=THEME.bg_panel)
                except Exception:
                    pass
                for b in (regen_btn.get("w"), next_btn.get("w"), cancel_btn.get("w")):
                    if b is not None:
                        try: b.configure(state="normal")
                        except Exception: pass

        def _regen():
            _set_busy(True)
            offre = self.cfg["candidatures"][st["idx"]]
            def task():
                try:
                    from ai_engine import AIEngine
                    engine = AIEngine(config=self.cfg)
                    txt = engine.generate_cover_letter(
                        offre, config=self.cfg, tone=st["tone"]
                    )
                except Exception as e:
                    txt = f"[Erreur génération : {e}]"
                def _apply():
                    if not lettre_box.winfo_exists():
                        return
                    try: lettre_box.configure(state="normal")
                    except Exception: pass
                    lettre_box.delete("1.0", "end")
                    lettre_box.insert("1.0", txt)
                    st["lettre"] = txt
                    _set_busy(False)
                self.after(0, _apply)
            threading.Thread(target=task, daemon=True).start()

        # ── Auto-génération à l'ouverture si la lettre est vide ──
        if not st.get("lettre"):
            self.after(150, _regen)

        # ── Footer : Annuler [G] · Régénérer [Centre] · Suivant [D]
        cancel_btn["w"] = ctk.CTkButton(
            footer, text="Annuler",
            command=lambda: (setattr(self, "_workflow_win", None), win.destroy()),
            height=36, corner_radius=18, width=110,
            fg_color="transparent", hover_color=THEME.bg_hover,
            border_width=1, border_color=THEME.border,
            text_color=THEME.text_secondary
        )
        cancel_btn["w"].pack(side="left", padx=20, pady=16)

        def _next():
            st["lettre"] = lettre_box.get("1.0", "end").strip()
            st["step"] = 2
            render()
        next_btn["w"] = ctk.CTkButton(
            footer, text="Suivant : Mail →",
            command=_next, height=36, corner_radius=18, width=170,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        next_btn["w"].pack(side="right", padx=20, pady=16)

        regen_btn["w"] = ctk.CTkButton(
            footer, text="Régénérer",
            image=theme.ctk_icon(theme.icon_refresh, size=14,
                                 color=THEME.text_primary),
            compound="left",
            command=_regen, height=36, width=140, corner_radius=18,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        regen_btn["w"].pack(expand=True, pady=16)

    def _wf_step2_mail(self, body, footer, st, render, win):
        """Étape 2 : mail d'accompagnement."""
        wrap = ctk.CTkScrollableFrame(body, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(
            wrap, text="2. Mail d'accompagnement",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            wrap, text="Court, professionnel, mentionne la lettre et le CV en PJ.",
            text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(0, 14))

        mail_box = ctk.CTkTextbox(wrap, height=280, fg_color=THEME.bg_panel,
                                  font=ctk.CTkFont(size=12), wrap="word")
        mail_box.pack(fill="both", expand=True, pady=(0, 8))
        if st.get("mail"):
            mail_box.insert("1.0", st["mail"])
        self._isolate_textbox_scroll(mail_box)

        # Indicateur de progression visible (loader + texte)
        loader_row = ctk.CTkFrame(wrap, fg_color="transparent", height=24)
        loader_row.pack(fill="x", pady=(2, 0))
        loader_row.pack_propagate(False)
        spinner = ctk.CTkLabel(loader_row, text="",
                               text_color=THEME.accent,
                               font=ctk.CTkFont(size=14, weight="bold"))
        spinner.pack(side="left")
        status_lbl = ctk.CTkLabel(loader_row, text="",
                                  text_color=THEME.text_muted,
                                  font=ctk.CTkFont(size=11))
        status_lbl.pack(side="left", padx=(8, 0))

        # Animation spinner (Braille rotation)
        FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        st.setdefault("_step2_spin_idx", 0)
        st.setdefault("_step2_spinning", False)
        st.setdefault("_step2_after_id", None)

        def _spin_tick():
            if not st["_step2_spinning"]:
                return
            try:
                if not spinner.winfo_exists():
                    return
                spinner.configure(text=FRAMES[st["_step2_spin_idx"] % len(FRAMES)])
                st["_step2_spin_idx"] += 1
                st["_step2_after_id"] = self.after(80, _spin_tick)
            except Exception:
                pass

        # Boutons (déclarés ici pour pouvoir les désactiver pendant la gen)
        regen_btn = {}
        next_btn = {}
        back_btn = {}

        def _set_busy(busy):
            st["_step2_spinning"] = busy
            if busy:
                status_lbl.configure(text="Génération en cours…",
                                     text_color=THEME.accent)
                _spin_tick()
                try:
                    mail_box.configure(state="disabled",
                                       fg_color=THEME.bg_panel_alt)
                except Exception:
                    pass
                for b in (regen_btn.get("w"), next_btn.get("w"), back_btn.get("w")):
                    if b is not None:
                        try: b.configure(state="disabled")
                        except Exception: pass
            else:
                spinner.configure(text="")
                status_lbl.configure(text="✓ Généré",
                                     text_color=THEME.green_ok)
                try:
                    mail_box.configure(state="normal",
                                       fg_color=THEME.bg_panel)
                except Exception:
                    pass
                for b in (regen_btn.get("w"), next_btn.get("w"), back_btn.get("w")):
                    if b is not None:
                        try: b.configure(state="normal")
                        except Exception: pass

        def _regen():
            _set_busy(True)
            offre = self.cfg["candidatures"][st["idx"]]
            def task():
                try:
                    from ai_engine import AIEngine
                    engine = AIEngine(config=self.cfg)
                    txt = engine.generate_email(offre, config=self.cfg)
                except Exception as e:
                    txt = f"[Erreur génération : {e}]"
                def _apply():
                    if not mail_box.winfo_exists():
                        return
                    # Activer temporairement pour pouvoir écrire
                    try: mail_box.configure(state="normal")
                    except Exception: pass
                    mail_box.delete("1.0", "end")
                    mail_box.insert("1.0", txt)
                    st["mail"] = txt
                    _set_busy(False)
                self.after(0, _apply)
            threading.Thread(target=task, daemon=True).start()

        # Auto-gen à l'ouverture si vide
        if not st.get("mail"):
            self.after(150, _regen)

        # ── Footer : Précédent [G] · Régénérer [Centre] · Suivant [D]
        def _back():
            st["mail"] = mail_box.get("1.0", "end").strip()
            st["step"] = 1
            render()
        def _next():
            st["mail"] = mail_box.get("1.0", "end").strip()
            st["step"] = 3
            render()
        back_btn["w"] = ctk.CTkButton(
            footer, text="← Précédent", command=_back,
            height=36, corner_radius=18, width=130,
            fg_color="transparent", hover_color=THEME.bg_hover,
            border_width=1, border_color=THEME.border,
            text_color=THEME.text_secondary
        )
        back_btn["w"].pack(side="left", padx=20, pady=16)
        next_btn["w"] = ctk.CTkButton(
            footer, text="Suivant : Envoi →", command=_next,
            height=36, corner_radius=18, width=170,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        next_btn["w"].pack(side="right", padx=20, pady=16)
        regen_btn["w"] = ctk.CTkButton(
            footer, text="Régénérer",
            image=theme.ctk_icon(theme.icon_refresh, size=14,
                                 color=THEME.text_primary),
            compound="left",
            command=_regen, height=36, width=140, corner_radius=18,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        regen_btn["w"].pack(expand=True, pady=16)

    def _wf_step3_envoi(self, body, footer, st, render, win):
        """Étape 3 : envoi (adaptatif selon présence email)."""
        wrap = ctk.CTkScrollableFrame(body, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(
            wrap, text="3. Envoi de la candidature",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(0, 4))

        has_email = bool(st["dest_email"] and "@" in st["dest_email"])

        if has_email:
            ctk.CTkLabel(
                wrap, text="L'email RH a été détecté dans l'offre — envoi en 1 clic.",
                text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
            ).pack(anchor="w", pady=(0, 18))

            card = ctk.CTkFrame(
                wrap, fg_color=THEME.bg_panel,
                border_width=1, border_color=THEME.green_ok,
                corner_radius=12
            )
            card.pack(fill="x", pady=8)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(padx=20, pady=24)
            ctk.CTkLabel(
                inner, text="",
                image=theme.ctk_icon(theme.icon_mail, size=32,
                                     color=THEME.green_ok)
            ).pack(pady=(0, 8))
            ctk.CTkLabel(
                inner, text="Email destinataire détecté",
                text_color=THEME.green_ok,
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack()
            ctk.CTkLabel(
                inner, text=st["dest_email"],
                font=ctk.CTkFont(family="Helvetica", size=14, weight="bold"),
                fg_color=THEME.bg_panel_alt, corner_radius=6
            ).pack(pady=(8, 12), ipadx=16, ipady=6)
            ctk.CTkLabel(
                inner, text="Avec en pièces jointes : Lettre.pdf · CV.pdf",
                text_color=THEME.text_muted, font=ctk.CTkFont(size=11)
            ).pack()

            def _send_gmail():
                self._wf_send_via_gmail(st, win)
            ctk.CTkButton(
                inner, text="Envoyer maintenant via Gmail",
                image=theme.ctk_icon(theme.icon_send, size=16,
                                     color="#FFFFFF"),
                compound="left",
                command=_send_gmail,
                height=42, corner_radius=21, width=320,
                fg_color=THEME.accent, hover_color=THEME.accent_hover,
                font=ctk.CTkFont(size=13, weight="bold")
            ).pack(pady=(16, 0))

            # Lien voir autres méthodes
            def _show_alt():
                # Force le mode "pas d'email" en réinitialisant dest_email
                st["dest_email"] = ""
                render()
            ctk.CTkButton(
                wrap, text="Voir les autres méthodes d'envoi",
                command=_show_alt,
                fg_color="transparent", hover_color=THEME.bg_hover,
                text_color=THEME.text_muted,
                font=ctk.CTkFont(size=11, underline=True)
            ).pack(pady=(8, 0))

        else:
            ctk.CTkLabel(
                wrap, text="Aucun email RH dans l'offre. Choisis une méthode :",
                text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
            ).pack(anchor="w", pady=(0, 14))

            self._wf_render_alt_methods(wrap, st, win)

        # Footer
        def _back():
            st["step"] = 2
            render()
        ctk.CTkButton(
            footer, text="← Précédent", command=_back,
            height=36, corner_radius=18, width=130,
            fg_color="transparent", hover_color=THEME.bg_hover,
            border_width=1, border_color=THEME.border,
            text_color=THEME.text_secondary
        ).pack(side="left", padx=20, pady=16)
        ctk.CTkButton(
            footer, text="Marquer comme envoyée",
            image=theme.ctk_icon(theme.icon_check, size=14, color="#FFFFFF"),
            compound="left",
            command=lambda: self._wf_mark_sent(st, win),
            height=36, corner_radius=18, width=220,
            fg_color=THEME.green_ok, hover_color=THEME.green_hover,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="right", padx=20, pady=16)

    def _wf_render_alt_methods(self, wrap, st, win):
        """Rend les 4 méthodes alternatives quand pas d'email."""
        offre = self.cfg["candidatures"][st["idx"]]
        # Bandeau warning
        info = ctk.CTkFrame(wrap, fg_color=THEME.bg_panel,
                            border_width=1, border_color=THEME.amber,
                            corner_radius=8)
        info.pack(fill="x", pady=(0, 14))
        ir = ctk.CTkFrame(info, fg_color="transparent")
        ir.pack(padx=14, pady=10, fill="x")
        ctk.CTkLabel(ir, text="",
                     image=theme.ctk_icon(theme.icon_warning, size=18,
                                          color=THEME.amber)
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            ir, text="LinkedIn et Indeed ne fournissent pas l'email RH dans 95% des offres.\n"
                    "Voici 4 méthodes pour candidater quand même :",
            text_color=THEME.text_secondary, font=ctk.CTkFont(size=11),
            justify="left"
        ).pack(side="left")

        # Grid 2×2 des méthodes
        grid = ctk.CTkFrame(wrap, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        def _make_card(parent, icon_fn, num, title, desc, cta_text,
                       on_click, recommended=False, row=0, col=0,
                       extra_widget=None):
            border = THEME.green_ok if recommended else THEME.border
            bg = (THEME.bg_panel
                  if not recommended else THEME.bg_panel)
            card = ctk.CTkFrame(parent, fg_color=bg, border_width=1,
                                border_color=border, corner_radius=10)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(padx=14, pady=14, fill="both", expand=True)
            head = ctk.CTkFrame(inner, fg_color="transparent")
            head.pack(fill="x", pady=(0, 8))
            mc = "#FFFFFF" if not recommended else THEME.green_ok
            mfg = (THEME.bg_panel_alt if not recommended
                   else "#1a2e1a")
            ctk.CTkLabel(head, text="",
                         image=theme.ctk_icon(icon_fn, size=18, color=mc),
                         width=32, height=32, fg_color=mfg, corner_radius=8
            ).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(head, text=f"{num}. {title}",
                         font=ctk.CTkFont(size=13, weight="bold")
            ).pack(side="left")
            if recommended:
                ctk.CTkLabel(head, text="RECOMMANDÉ",
                             fg_color=THEME.green_ok, text_color="white",
                             corner_radius=4,
                             font=ctk.CTkFont(size=9, weight="bold")
                ).pack(side="right", padx=(0, 4), pady=(4, 0), ipadx=6, ipady=2)
            ctk.CTkLabel(inner, text=desc,
                         text_color=THEME.text_secondary,
                         font=ctk.CTkFont(size=11),
                         wraplength=300, justify="left"
            ).pack(anchor="w", pady=(0, 8))
            if extra_widget:
                extra_widget(inner)
            else:
                ctk.CTkButton(
                    inner, text=cta_text, command=on_click,
                    height=30, corner_radius=15,
                    fg_color=(THEME.green_ok if recommended else THEME.accent),
                    hover_color=(THEME.green_hover if recommended else THEME.accent_hover),
                    font=ctk.CTkFont(size=11, weight="bold")
                ).pack(anchor="w", pady=(2, 0))

        # 1. Ouvrir l'offre
        _make_card(grid, theme.icon_external, 1,
                   "Ouvrir l'offre dans le navigateur",
                   "Ouvre l'annonce dans Safari. Clique 'Postuler' sur le site → uploads les PDF + colle le mail dans le formulaire intégré.",
                   "Ouvrir l'offre",
                   lambda: self._wf_open_offer(offre),
                   recommended=True, row=0, col=0)

        # 2. Préparer dossier
        _make_card(grid, theme.icon_folder, 2,
                   "Préparer un dossier",
                   "Génère Candidature_<Entreprise>.zip avec Lettre.pdf, CV.pdf et mail.txt. Tu drag-drop dans n'importe quel formulaire web.",
                   "Générer le dossier",
                   lambda: self._wf_prepare_folder(st, win),
                   row=0, col=1)

        # 3. Copier presse-papier
        def _copy_extra(inner_parent):
            row = ctk.CTkFrame(inner_parent, fg_color="transparent")
            row.pack(fill="x", pady=(2, 0))
            ctk.CTkButton(
                row, text="Copier lettre",
                command=lambda: self._wf_copy_clip(st["lettre"], "Lettre"),
                height=28, width=110, corner_radius=14,
                fg_color=THEME.accent, hover_color=THEME.accent_hover,
                font=ctk.CTkFont(size=10, weight="bold")
            ).pack(side="left", padx=(0, 4))
            ctk.CTkButton(
                row, text="Copier mail",
                command=lambda: self._wf_copy_clip(st["mail"], "Mail"),
                height=28, width=110, corner_radius=14,
                fg_color=THEME.accent, hover_color=THEME.accent_hover,
                font=ctk.CTkFont(size=10, weight="bold")
            ).pack(side="left")
        _make_card(grid, theme.icon_copy, 3,
                   "Copier dans le presse-papier",
                   "Choisis ce que tu copies. Idéal pour coller dans LinkedIn DM, WhatsApp pro, formulaire texte web.",
                   "", None,
                   row=1, col=0, extra_widget=_copy_extra)

        # 4. Envoyer mail direct
        def _send_direct_extra(inner_parent):
            row = ctk.CTkFrame(inner_parent, fg_color="transparent")
            row.pack(fill="x", pady=(2, 0))
            email_var = ctk.StringVar()
            ent = ctk.CTkEntry(row, textvariable=email_var,
                               placeholder_text="rh@entreprise.com",
                               height=30, fg_color=THEME.bg_panel_alt)
            ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ctk.CTkButton(
                row, text="Envoyer",
                image=theme.ctk_icon(theme.icon_send, size=12,
                                     color="#FFFFFF"),
                compound="left",
                command=lambda: self._wf_send_to_address(
                    st, email_var.get().strip(), win),
                height=30, width=100, corner_radius=15,
                fg_color=THEME.accent, hover_color=THEME.accent_hover,
                font=ctk.CTkFont(size=11, weight="bold")
            ).pack(side="left")
        _make_card(grid, theme.icon_send, 4,
                   "Envoyer un mail direct",
                   "Tu connais l'email RH ? Saisis-le et envoie via Gmail SMTP avec les PJ.",
                   "", None,
                   row=1, col=1, extra_widget=_send_direct_extra)

    # ─── 4 méthodes d'envoi (helpers) ──────────────────────────
    def _wf_generate_pdfs(self, st):
        """Génère lettre.pdf (à partir du texte de l'étape 1) + retourne
        liste de pièces jointes (lettre, CV si existant)."""
        from pdf_generator import generate_lettre_pdf
        offre = self.cfg["candidatures"][st["idx"]]
        profil = self.cfg.get("profil", {})
        # Génère la lettre PDF (si non vide)
        attachments = []
        if st.get("lettre"):
            try:
                pdf_path = generate_lettre_pdf(
                    st["lettre"], profil, offre
                )
                attachments.append(pdf_path)
            except Exception as e:
                print(f"[workflow] PDF lettre échec : {e}")
        # CV (si présent)
        cv_path = self.cfg.get("documents", {}).get("cv_path", "")
        if cv_path and os.path.exists(cv_path):
            attachments.append(cv_path)
        return attachments

    def _wf_send_via_gmail(self, st, win):
        """Envoie via Gmail SMTP à l'email détecté de l'offre."""
        self._wf_send_to_address(st, st["dest_email"], win)

    def _wf_send_to_address(self, st, address, win):
        """Envoie le mail à `address` via Gmail SMTP avec PJ."""
        address = (address or "").strip()
        if not address or "@" not in address:
            messagebox.showwarning("Email invalide",
                                   "Saisis une adresse email valide.")
            return
        offre = self.cfg["candidatures"][st["idx"]]
        body = st.get("mail", "").strip()
        if not body:
            messagebox.showwarning("Mail vide",
                                   "Génère ou écris le mail (étape 2) avant l'envoi.")
            return
        # Subject : on essaie d'extraire la première ligne du mail si elle
        # commence par "Objet :" sinon on synthétise
        subject = ""
        for ln in body.splitlines():
            if ln.lower().startswith("objet"):
                subject = ln.split(":", 1)[-1].strip()
                break
        if not subject:
            poste = offre.get("poste") or offre.get("titre", "?")
            subject = f"Candidature — {poste}"

        attachments = self._wf_generate_pdfs(st)

        def task():
            try:
                from mail_sender import MailSender
                sender = MailSender(config=self.cfg)
                sender.send(address, subject, body, attachments=attachments)
                self.after(0, lambda: self._wf_mark_sent(st, win,
                                                         silent=False,
                                                         success_msg=f"Envoyé à {address}"))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror(
                    "Échec envoi", f"Impossible d'envoyer le mail :\n{err}"))
        threading.Thread(target=task, daemon=True).start()
        messagebox.showinfo("Envoi en cours",
                            f"Envoi à {address} en cours…")

    def _wf_open_offer(self, offre):
        url = offre.get("url", "").strip()
        if not url:
            messagebox.showinfo("Pas de lien",
                                "Aucune URL d'offre disponible pour cette candidature.")
            return
        self._open_url(url)

    def _wf_prepare_folder(self, st, win):
        """Génère un ZIP avec Lettre.pdf + CV.pdf + mail.txt, ouvre le Finder."""
        offre = self.cfg["candidatures"][st["idx"]]
        try:
            zip_path = self._prepare_application_folder(
                [st["idx"]], lettre_override={st["idx"]: st.get("lettre", "")},
                mail_override={st["idx"]: st.get("mail", "")}
            )
            # Ouvre le Finder à l'emplacement
            import subprocess
            subprocess.run(["open", "-R", str(zip_path)])
            messagebox.showinfo("Dossier prêt",
                                f"Dossier créé :\n{zip_path}\n\n"
                                f"Glisse-le dans le formulaire de candidature.")
        except Exception as e:
            messagebox.showerror("Échec",
                                 f"Création du dossier impossible :\n{e}")

    def _wf_copy_clip(self, content, label):
        if not content:
            messagebox.showwarning("Rien à copier",
                                   f"Le contenu de '{label}' est vide.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.update()
            messagebox.showinfo("Copié",
                                f"{label} copié dans le presse-papier.")
        except Exception as e:
            messagebox.showerror("Échec", str(e))

    def _wf_mark_sent(self, st, win, silent=False, success_msg=None):
        """Marque comme envoyée et ferme le workflow."""
        try:
            self.cfg["candidatures"][st["idx"]]["statut"] = "Envoyée"
            save_config(self.cfg)
        except Exception:
            pass
        if not silent and success_msg:
            messagebox.showinfo("Candidature envoyée", success_msg)
        setattr(self, "_workflow_win", None)
        try:
            win.destroy()
        except Exception:
            pass
        # Re-render la liste si on est sur la page candidatures
        try:
            if self.cfg.get("ui", {}).get("last_tab") == "tracker":
                self.show_tracker()
        except Exception:
            pass

    def _prepare_application_folder(self, indices, lettre_override=None,
                                     mail_override=None):
        """Génère 1 ZIP par candidature dans ~/Downloads/CandidatureBot/.
        Retourne le chemin du dernier ZIP créé (pour ouvrir le Finder)."""
        from pdf_generator import generate_lettre_pdf
        from pathlib import Path
        import zipfile, tempfile, re

        out_dir = Path.home() / "Downloads" / "CandidatureBot"
        out_dir.mkdir(parents=True, exist_ok=True)
        profil = self.cfg.get("profil", {})
        cv_path = self.cfg.get("documents", {}).get("cv_path", "")
        last_zip = None
        for idx in indices:
            if not (0 <= idx < len(self.cfg.get("candidatures", []))):
                continue
            c = self.cfg["candidatures"][idx]
            ent = re.sub(r"[^\w\-]+", "_", (c.get("entreprise") or "Entreprise"))[:30]
            zip_path = out_dir / f"Candidature_{ent}.zip"

            # Génère lettre.pdf dans temp
            tmp = Path(tempfile.mkdtemp(prefix="cbot_zip_"))
            try:
                lettre_text = (lettre_override or {}).get(idx, "")
                if lettre_text:
                    try:
                        pdf = generate_lettre_pdf(lettre_text, profil, c,
                                                  dest_dir=str(tmp))
                    except Exception:
                        pdf = None
                else:
                    pdf = None
                mail_text = (mail_override or {}).get(idx, "")

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    if pdf and os.path.exists(pdf):
                        zf.write(pdf, arcname=f"Lettre_{ent}.pdf")
                    if cv_path and os.path.exists(cv_path):
                        zf.write(cv_path, arcname=f"CV_{os.path.basename(cv_path)}")
                    if mail_text:
                        zf.writestr("mail.txt", mail_text)
            finally:
                import shutil as _sh
                _sh.rmtree(tmp, ignore_errors=True)
            last_zip = zip_path
        return last_zip

    def _prepare_application_folder_bulk(self, container):
        """Bulk : prépare 1 ZIP par candidature cochée. Pour chaque, on
        génère lettre + mail via l'IA, puis on crée le ZIP avec
        Lettre.pdf + CV.pdf + mail.txt. Affiche une popup de progression."""
        sel = sorted([k for k, v in (getattr(self, "_tracker_selection", {}) or {}).items()
                      if v.get()])
        if not sel:
            messagebox.showinfo("Information",
                                "Aucune candidature sélectionnée.")
            return

        # Popup de progression (modale, non bloquante)
        prog_win = ctk.CTkToplevel(self)
        prog_win.title("Préparation des dossiers")
        prog_win.geometry("420x180")
        prog_win.transient(self)
        prog_win.grab_set()
        prog_win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 210
        py = self.winfo_y() + self.winfo_height() // 2 - 90
        prog_win.geometry(f"+{px}+{py}")
        ctk.CTkLabel(
            prog_win, text="Génération des dossiers en cours…",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(22, 10))
        prog_lbl = ctk.CTkLabel(
            prog_win, text=f"0 / {len(sel)}",
            text_color=THEME.text_secondary, font=ctk.CTkFont(size=12)
        )
        prog_lbl.pack()
        prog_bar = ctk.CTkProgressBar(
            prog_win, mode="determinate", height=10, width=340,
            progress_color=THEME.accent
        )
        prog_bar.pack(pady=(12, 0), padx=20)
        prog_bar.set(0)
        sub_lbl = ctk.CTkLabel(
            prog_win, text="", text_color=THEME.text_muted,
            font=ctk.CTkFont(size=10), wraplength=380, justify="center"
        )
        sub_lbl.pack(pady=(8, 0))
        bring_to_front(prog_win)

        def task():
            try:
                from ai_engine import AIEngine
                engine = AIEngine(config=self.cfg)
                lettre_override = {}
                mail_override = {}
                last_zip = None
                for n, idx in enumerate(sel, 1):
                    c = self.cfg["candidatures"][idx]
                    ent = c.get("entreprise", "?")
                    self.after(0, lambda n=n, ent=ent: (
                        prog_lbl.configure(text=f"{n} / {len(sel)}"),
                        sub_lbl.configure(text=f"Génération pour {ent}…"),
                        prog_bar.set((n - 1) / max(len(sel), 1)),
                    ))
                    # Lettre IA (ton classique par défaut)
                    try:
                        lettre = engine.generate_cover_letter(
                            c, config=self.cfg, tone="classique"
                        )
                        lettre_override[idx] = lettre
                    except Exception as e:
                        print(f"[bulk-folder] lettre {ent} échec : {e}")
                    # Mail IA
                    try:
                        mail = engine.generate_email(c, config=self.cfg)
                        mail_override[idx] = mail
                    except Exception as e:
                        print(f"[bulk-folder] mail {ent} échec : {e}")

                # Bonus : génère les ZIP au fil de l'eau, pas en bloc
                last_zip = self._prepare_application_folder(
                    sel, lettre_override=lettre_override,
                    mail_override=mail_override
                )

                def _done():
                    try:
                        prog_win.destroy()
                    except Exception:
                        pass
                    if last_zip:
                        import subprocess
                        subprocess.run(["open", "-R", str(last_zip)])
                    messagebox.showinfo(
                        "Dossiers prêts",
                        f"{len(sel)} dossier(s) créé(s) dans :\n"
                        f"~/Downloads/CandidatureBot/\n\n"
                        f"Chaque ZIP contient : Lettre.pdf · CV.pdf · mail.txt"
                    )
                self.after(0, _done)
            except Exception as e:
                err = str(e)
                def _err():
                    try: prog_win.destroy()
                    except Exception: pass
                    messagebox.showerror("Échec", err)
                self.after(0, _err)

        threading.Thread(target=task, daemon=True).start()

    def _send_candidature(self, offre, idx, container):
        """Popup preview → envoyer candidature par mail (legacy, gardé pour bouton 'Mail' éventuel)"""
        email_dest = (offre.get("email") or "").strip()

        win = ctk.CTkToplevel(self)
        win.title("Prévisualisation candidature")
        win.geometry("720x720")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 360
        py = self.winfo_y() + self.winfo_height() // 2 - 360
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win,
            text=f"{offre.get('entreprise','?')} — {offre.get('poste','?')}",
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
        lettre_status_frame = ctk.CTkFrame(win, fg_color=THEME.bg_panel_alt, corner_radius=8)
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
                    text=f"Lettre liée à cette candidature ({n} mots) — sera jointe en PDF",
                    text_color=THEME.green_ok
                )
            else:
                lettre_status_label.configure(
                    text="Aucune lettre liée — clique sur Lettre pour la rédiger",
                    text_color=THEME.amber
                )

        def _on_lettre_saved(_txt):
            _refresh_lettre_status()

        def _edit_lettre():
            self._open_lettre_window(offre, idx=idx, on_save=_on_lettre_saved)

        ctk.CTkButton(
            lettre_status_frame, text="Éditer / Générer la lettre",
            command=_edit_lettre,
            fg_color=THEME.accent, hover_color=THEME.accent_hover, height=32
        ).pack(side="right", padx=10, pady=6)

        _refresh_lettre_status()

        # ── Corps du mail (court) ─────────────────────────────
        ctk.CTkLabel(
            win,
            text="Corps du mail (court — la lettre et le CV sont en pièces jointes) :"
        ).pack(anchor="w", padx=20)
        body_box = ctk.CTkTextbox(win, height=240, font=ctk.CTkFont(size=12), wrap="word")
        body_box.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        body_box.insert("1.0", "Génération en cours...")

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
                err_msg = f"{e}\n{traceback.format_exc()}"
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
                messagebox.showwarning("Attention", "Indique un destinataire.", parent=win)
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
                        "Erreur PDF lettre",
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
                messagebox.showinfo("Envoyé", f"Mail envoyé à {current_email}{pj_info}")
                self._refresh_tracker_list(container)
            except Exception as e:
                messagebox.showerror("Erreur envoi", str(e), parent=win)

        ctk.CTkButton(
            btn_row, text="Régénérer mail",
            command=lambda: threading.Thread(target=generate, daemon=True).start(),
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary, height=38, width=150
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="Envoyer",
            command=do_send,
            fg_color=THEME.accent, hover_color=THEME.accent_hover, height=38, width=120
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="Annuler",
            command=win.destroy,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.red_danger,
            text_color=THEME.text_secondary, height=38, width=100
        ).pack(side="right")

        bring_to_front(win)

    # 🆕 Envoi en masse
    def _send_all_pending(self, container):
        candidatures = self.cfg.get("candidatures", [])
        pending = [(i, c) for i, c in enumerate(candidatures)
                   if c.get("statut") == "À envoyer"]
        if not pending:
            messagebox.showinfo("Information", "Aucune candidature « À envoyer ».")
            return

        missing_email = [c for _, c in pending if not c.get("email")]
        if missing_email:
            messagebox.showwarning(
                "Emails manquants",
                f"{len(missing_email)} candidature(s) n'ont pas d'email destinataire.\n"
                f"Elles seront ignorées. Ajoute-les manuellement via le bouton Mail."
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
        win.title("Envoi en lot")
        win.geometry("580x420")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 290
        py = self.winfo_y() + self.winfo_height() // 2 - 210
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="ENVOI EN LOT DES CANDIDATURES",
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
                        win.after(0, append, f">  {entreprise} — {poste}…")
                        mail = engine.generate_email(c, self.cfg)
                        lettre = engine.generate_cover_letter(c, self.cfg)
                        body = mail + "\n\n────────────────────\n\n" + lettre
                        subject = f"Candidature – {poste} – {p.get('prenom','')} {p.get('nom','')}"
                        sender.send(to=c["email"], subject=subject, body=body)
                        self.cfg["candidatures"][idx]["statut"] = "Envoyée"
                        save_config(self.cfg)
                        ok += 1
                        win.after(0, append, f"   OK envoyé à {c['email']}")
                    except Exception as e:
                        fail += 1
                        win.after(0, append, f"   ERREUR {str(e)[:120]}")
            except Exception as e:
                win.after(0, append, f"Erreur globale : {e}")
            finally:
                win.after(0, append, f"\nTerminé : {ok} envoyée(s), {fail} échec(s).")
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
                messagebox.showinfo("Export réussi", f"Export réussi !\n{path}")
        except Exception as e:
            messagebox.showerror("Erreur export", str(e))

    # ══════════════════════════════════════════════════════════
    # 🔁 ROUTINE : recherches automatiques récurrentes
    # ══════════════════════════════════════════════════════════
    def show_routine(self):
        self._set_active("ROUTINE")
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
            self.main, text="ROUTINE — RECHERCHES AUTOMATIQUES",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            self.main,
            text="Active une recherche récurrente en arrière-plan.\n"
                 "Tant que l'app est ouverte, elle se déclenche à la fréquence choisie.",
            text_color="gray", justify="left"
        ).pack(anchor="w", pady=(0, 14))

        # ── Activation ─────────────────────────────────────────
        switch_frame = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel_alt, corner_radius=10)
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
        freq_frame = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel_alt, corner_radius=10)
        freq_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            freq_frame, text="FRÉQUENCE",
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
        crit_frame = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel_alt, corner_radius=10)
        crit_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            crit_frame, text="CRITÈRES (INDÉPENDANTS DE LA RECHERCHE MANUELLE)",
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
        opt_frame = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel_alt, corner_radius=10)
        opt_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            opt_frame, text="AUTOMATISATION",
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
        hist_frame = ctk.CTkFrame(self.main, fg_color=THEME.bg_panel_alt, corner_radius=10)
        hist_frame.pack(fill="both", expand=True, pady=(0, 12))

        ctk.CTkLabel(
            hist_frame, text="DERNIÈRES EXÉCUTIONS",
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
            info_row, text="", text_color=THEME.green_ok,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.routine_save_status.pack(side="right")

        btn_row = ctk.CTkFrame(self.main, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            btn_row, text="Sauvegarder",
            command=self._save_routine, height=42,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="Lancer maintenant",
            command=lambda: threading.Thread(
                target=lambda: self._run_routine_search(manual=True),
                daemon=True
            ).start(),
            height=42, fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
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
                w.configure(text="Sauvegardé", text_color=THEME.green_ok)
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
        messagebox.showinfo("Sauvegardé", "Routine sauvegardée.")
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
                    "Routine",
                    f"{len(new_offres)} nouvelle(s) offre(s) trouvée(s)\n"
                    f"{added} ajoutée(s) automatiquement"
                )
            self.after(0, _report)

    # ══════════════════════════════════════════════════════════
    # 🖱️ Scroll helper : isole le wheel d'un textbox du parent
    # ══════════════════════════════════════════════════════════
    def _isolate_textbox_scroll(self, textbox):
        """Quand le curseur est sur le textbox :
        - si son contenu déborde → on scrolle dedans + on stoppe la propagation
        - si tout tient déjà dedans (yview = (0, 1)) → on laisse passer la
          molette au parent scrollable (sinon impossible de scroller la
          fenêtre quand on est au-dessus d'un textbox court)."""
        inner = getattr(textbox, "_textbox", None)
        if inner is None:
            return

        def _on_wheel(event):
            try:
                top, bot = inner.yview()
                overflowing = not (top <= 1e-3 and bot >= 1 - 1e-3)
                if not overflowing:
                    return  # ne pas break → parent reçoit la molette
                # Direction
                step = 0
                if getattr(event, "num", None) == 4:
                    step = -3
                elif getattr(event, "num", None) == 5:
                    step = 3
                elif getattr(event, "delta", 0):
                    step = -3 if event.delta > 0 else 3
                # Empêche d'aller au-delà des bornes (sinon "stuck")
                going_up_at_top = step < 0 and top <= 1e-3
                going_down_at_bot = step > 0 and bot >= 1 - 1e-3
                if going_up_at_top or going_down_at_bot:
                    return  # bord atteint → propage au parent
                inner.yview_scroll(step, "units")
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
        self._set_active("MES INFOS")
        self._remember_tab("profile")
        self._clear_main()

        p = self.cfg.setdefault("profil", {})
        exp = self.cfg.setdefault("experience", {})
        docs = self.cfg.setdefault("documents", {})

        # ── Header card : avatar + nom + complétude ──
        self._build_profile_header(self.main, p, exp, docs)

        # ── Body : 2 colonnes scrollables ──
        body = ctk.CTkScrollableFrame(self.main, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(12, 0))
        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self._build_identity_card(left, p)
        self._build_experience_card(left, exp)
        self._build_cv_card(right, docs)
        self._build_lettre_card(right, p, docs)

        # ── Footer sticky : info + bouton sauvegarder ──
        footer = ctk.CTkFrame(self.main, fg_color="transparent")
        footer.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(
            footer,
            text="Email & ville viennent de Paramètres / Recherche.",
            text_color=THEME.text_muted, font=ctk.CTkFont(size=11)
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="Sauvegarder",
            image=theme.ctk_icon(theme.icon_save, size=14, color="#FFFFFF"),
            compound="left",
            command=self.save_profile, height=36, width=160, corner_radius=18,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="right")

    # ── Helpers show_profile ────────────────────────────────────
    def _compute_initials(self, prenom, nom):
        a = (prenom or "").strip()
        b = (nom or "").strip()
        if a and b:
            return (a[0] + b[0]).upper()
        if a:
            return a[:2].upper()
        if b:
            return b[:2].upper()
        return "??"

    def _compute_profile_score(self, p, exp, docs):
        """Renvoie (score 0-100, str décrivant ce qui manque)."""
        checks = [
            ("Prénom",      bool((p.get("prenom") or "").strip())),
            ("Nom",         bool((p.get("nom") or "").strip())),
            ("Téléphone",   bool((p.get("telephone") or "").strip())),
            ("LinkedIn",    bool((p.get("linkedin") or "").strip())),
            ("Poste",       bool((p.get("poste_recherche") or "").strip())),
            ("Années",      int(exp.get("annees") or 0) > 0),
            ("Compétences", len(exp.get("competences") or []) > 0),
            ("Langues",     len(exp.get("langues") or []) > 0),
            ("CV",          bool(docs.get("cv_path")) and os.path.exists(docs.get("cv_path", ""))),
            ("Lettre",      bool((p.get("lettre_type") or "").strip()) or
                            (bool(docs.get("lettre_path")) and
                             os.path.exists(docs.get("lettre_path", "")))),
        ]
        passed = [name for name, ok in checks if ok]
        missing = [name for name, ok in checks if not ok]
        score = round(len(passed) * 100 / len(checks))
        missing_str = ", ".join(missing[:3]) if missing else ""
        if len(missing) > 3:
            missing_str += f" +{len(missing) - 3}"
        return score, missing_str

    def _compute_cv_ats(self, docs):
        """Renvoie (score 0-100 ou None, color)."""
        path = docs.get("cv_path", "")
        text = docs.get("cv_text", "")
        if not path or not text or not os.path.exists(path):
            return None, THEME.text_muted
        try:
            from cv_parser import ats_score
            report = ats_score(path, text=text)
            score = int(report.get("score", 0))
        except Exception:
            return None, THEME.text_muted
        if score >= 80:
            return score, THEME.green_ok
        if score >= 60:
            return score, THEME.amber
        return score, THEME.red_danger

    def _build_profile_header(self, parent, p, exp, docs):
        header = ctk.CTkFrame(
            parent, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=10
        )
        header.pack(fill="x")
        header.grid_columnconfigure(1, weight=1)

        # Avatar circulaire avec initiales
        initials = self._compute_initials(p.get("prenom"), p.get("nom"))
        avatar = ctk.CTkFrame(
            header, width=56, height=56,
            fg_color=THEME.accent, corner_radius=28
        )
        avatar.grid(row=0, column=0, padx=(18, 14), pady=14)
        avatar.grid_propagate(False)
        ctk.CTkLabel(
            avatar, text=initials,
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color="white"
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Bloc identité + contact
        info = ctk.CTkFrame(header, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=14)

        name = f"{(p.get('prenom') or '').strip()} {(p.get('nom') or '').strip()}".strip()
        if not name:
            name = "Profil incomplet"
        ctk.CTkLabel(
            info, text=name,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME.text_primary, anchor="w"
        ).pack(anchor="w")

        role = (p.get("poste_recherche") or "—") or "—"
        years = int(exp.get("annees") or 0)
        role_line = role
        if years:
            role_line += f"  ·  {years} an{'s' if years > 1 else ''} d'expérience"
        ctk.CTkLabel(
            info, text=role_line,
            font=ctk.CTkFont(size=12),
            text_color=THEME.text_secondary, anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        contact_parts = []
        if p.get("telephone"):
            contact_parts.append(p["telephone"])
        if p.get("linkedin"):
            ln = p["linkedin"]
            if ln.startswith("http"):
                ln = ln.replace("https://", "").replace("http://", "")
            contact_parts.append(ln)
        if contact_parts:
            ctk.CTkLabel(
                info, text="  ·  ".join(contact_parts),
                font=ctk.CTkFont(size=11),
                text_color=THEME.text_muted, anchor="w"
            ).pack(anchor="w", pady=(3, 0))

        # Bloc complétude à droite
        comp = ctk.CTkFrame(header, fg_color="transparent")
        comp.grid(row=0, column=2, padx=(0, 18), pady=14, sticky="e")

        score, missing = self._compute_profile_score(p, exp, docs)
        color = (THEME.green_ok if score >= 80
                 else THEME.amber if score >= 50
                 else THEME.red_danger)

        top_row = ctk.CTkFrame(comp, fg_color="transparent")
        top_row.pack(anchor="e")
        ctk.CTkLabel(
            top_row, text="Complétude",
            font=ctk.CTkFont(size=10),
            text_color=THEME.text_secondary
        ).pack(side="left", padx=(0, 70))
        ctk.CTkLabel(
            top_row, text=f"{score}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color
        ).pack(side="left")

        bar = ctk.CTkProgressBar(
            comp, width=150, height=6,
            fg_color=THEME.bg_panel_alt,
            progress_color=color
        )
        bar.set(score / 100.0)
        bar.pack(pady=(5, 3), anchor="e")

        if missing:
            ctk.CTkLabel(
                comp, text=f"Manque : {missing}",
                font=ctk.CTkFont(size=10),
                text_color=THEME.text_muted
            ).pack(anchor="e")

    def _make_card(self, parent, title, action_widget=None):
        """Crée une card avec titre + zone de contenu. Renvoie la zone."""
        card = ctk.CTkFrame(
            parent, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=8
        )
        card.pack(fill="x", pady=(0, 12))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(
            head, text=title.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME.text_secondary
        ).pack(side="left")
        if action_widget is not None:
            action_widget.pack(in_=head, side="right")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        return body

    def _build_identity_card(self, parent, p):
        body = self._make_card(parent, "Identité")
        body.grid_columnconfigure(1, weight=1)

        fields = [
            ("Prénom",     "prenom"),
            ("Nom",        "nom"),
            ("Téléphone",  "telephone"),
            ("LinkedIn",   "linkedin"),
            ("Poste",      "poste_recherche"),
        ]
        self.profile_entries = {}
        for i, (lbl, key) in enumerate(fields):
            ctk.CTkLabel(
                body, text=lbl, font=ctk.CTkFont(size=12),
                text_color=THEME.text_secondary, width=78, anchor="w"
            ).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=4)
            e = ctk.CTkEntry(body, height=30, font=ctk.CTkFont(size=12))
            e.insert(0, p.get(key, ""))
            e.grid(row=i, column=1, sticky="ew", pady=4)
            self.profile_entries[key] = e

    def _build_experience_card(self, parent, exp):
        body = self._make_card(parent, "Expérience")
        body.grid_columnconfigure(0, weight=1)

        # Années
        years_row = ctk.CTkFrame(body, fg_color="transparent")
        years_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(
            years_row, text="Années", font=ctk.CTkFont(size=12),
            text_color=THEME.text_secondary, width=78, anchor="w"
        ).pack(side="left", padx=(0, 10))
        self.exp_annees_entry = ctk.CTkEntry(years_row, height=30, width=80,
                                              font=ctk.CTkFont(size=12))
        self.exp_annees_entry.insert(0, str(exp.get("annees", 0)))
        self.exp_annees_entry.pack(side="left")

        # Compétences
        ctk.CTkLabel(
            body, text="Compétences", font=ctk.CTkFont(size=12),
            text_color=THEME.text_secondary, anchor="w"
        ).grid(row=1, column=0, sticky="w", pady=(2, 4))
        self.exp_comp_chips = ChipsEditor(
            body,
            values=exp.get("competences", []),
            placeholder="+ ajouter",
            height=70
        )
        self.exp_comp_chips.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        # Langues
        ctk.CTkLabel(
            body, text="Langues", font=ctk.CTkFont(size=12),
            text_color=THEME.text_secondary, anchor="w"
        ).grid(row=3, column=0, sticky="w", pady=(2, 4))
        self.exp_lang_chips = ChipsEditor(
            body,
            values=exp.get("langues", []),
            placeholder="+ ajouter",
            height=50
        )
        self.exp_lang_chips.grid(row=4, column=0, sticky="ew")

    def _build_cv_card(self, parent, docs):
        body = self._make_card(parent, "CV")

        cv_path = docs.get("cv_path", "")
        has_cv = bool(cv_path and os.path.exists(cv_path))

        # Preview : icône PDF + métadonnées
        preview = ctk.CTkFrame(
            body, fg_color=THEME.bg,
            border_color=THEME.border, border_width=1, corner_radius=6
        )
        preview.pack(fill="x", pady=(0, 8))

        icon = ctk.CTkFrame(
            preview, width=40, height=50,
            fg_color=THEME.bg_panel_alt,
            border_color=THEME.border, border_width=1, corner_radius=4
        )
        icon.pack(side="left", padx=(10, 10), pady=10)
        icon.pack_propagate(False)
        ext = (os.path.splitext(cv_path)[1].lstrip(".").upper() or "?") if has_cv else "—"
        ctk.CTkLabel(
            icon, text=ext, font=ctk.CTkFont(size=10, weight="bold"),
            text_color=THEME.accent
        ).place(relx=0.5, rely=0.5, anchor="center")

        info = ctk.CTkFrame(preview, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, pady=8, padx=(0, 10))

        # Nom fichier (stocké pour update après import)
        self.cv_file_label = ctk.CTkLabel(
            info,
            text=(os.path.basename(cv_path) if has_cv else "Aucun CV importé"),
            text_color=(THEME.text_primary if has_cv else THEME.text_muted),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.cv_file_label.pack(anchor="w", fill="x")

        # Métadonnées
        meta = ""
        if has_cv:
            try:
                size = os.path.getsize(cv_path)
                size_str = (f"{size // 1024} Ko" if size < 1_048_576
                            else f"{size / 1_048_576:.1f} Mo")
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cv_path))
                age_days = (datetime.datetime.now() - mtime).days
                if age_days < 1:
                    age = "aujourd'hui"
                elif age_days < 30:
                    age = f"il y a {age_days} j"
                else:
                    age = mtime.strftime("%b %Y")
                wc = len((docs.get("cv_text") or "").split())
                meta = f"{size_str}  ·  {wc} mots  ·  importé {age}"
            except Exception:
                meta = ""
        if meta:
            ctk.CTkLabel(
                info, text=meta, font=ctk.CTkFont(size=10),
                text_color=THEME.text_muted, anchor="w"
            ).pack(anchor="w")

        # Score ATS
        score, color = self._compute_cv_ats(docs)
        if score is not None:
            ats_row = ctk.CTkFrame(
                body, fg_color=THEME.bg_panel_alt, corner_radius=6
            )
            ats_row.pack(fill="x", pady=(0, 8))
            left_box = ctk.CTkFrame(ats_row, fg_color="transparent")
            left_box.pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                left_box, text="SCORE ATS",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=THEME.text_secondary
            ).pack(anchor="w")
            ctk.CTkLabel(
                left_box, text="Compatible avec les robots de tri",
                font=ctk.CTkFont(size=10),
                text_color=THEME.text_muted
            ).pack(anchor="w")
            ctk.CTkLabel(
                ats_row, text=str(score),
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color=color
            ).pack(side="right", padx=14, pady=6)

        # Actions
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            btn_row,
            text=("Remplacer" if has_cv else "Importer CV"),
            command=self._import_cv, height=30,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=12)
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text="Remplir depuis CV",
            command=self._autofill_from_cv, height=30,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=12)
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkButton(
            body, text="Analyse ATS détaillée",
            command=self._analyze_ats, height=28,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=12)
        ).pack(fill="x", pady=(6, 0))

    def _build_lettre_card(self, parent, p, docs):
        # Bouton Générer dans le header de la card
        gen_btn = ctk.CTkButton(
            None, text="Générer via IA",
            command=lambda: self._open_lettre_window({
                "titre": self.cfg.get("profil", {}).get("poste_recherche", ""),
                "poste": self.cfg.get("profil", {}).get("poste_recherche", ""),
                "entreprise": "",
                "description": ""
            }),
            height=24, width=110,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=11)
        )
        body = self._make_card(parent, "Lettre type", action_widget=gen_btn)

        # Note explicative
        ctk.CTkLabel(
            body,
            text="Texte de base utilisé si aucun fichier lettre.",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted, anchor="w"
        ).pack(anchor="w", pady=(0, 4))

        self.lettre_box = ctk.CTkTextbox(body, height=120, wrap="word",
                                          font=ctk.CTkFont(size=12))
        self.lettre_box.pack(fill="x", pady=(0, 8))
        self.lettre_box.insert("1.0", p.get("lettre_type", ""))
        self._isolate_textbox_scroll(self.lettre_box)

        # Lettre fichier (option alternative)
        lm_path = docs.get("lettre_path", "")
        has_lm = bool(lm_path and os.path.exists(lm_path))

        file_row = ctk.CTkFrame(body, fg_color="transparent")
        file_row.pack(fill="x")
        file_row.grid_columnconfigure(0, weight=1)
        self.lm_file_label = ctk.CTkLabel(
            file_row,
            text=("OU " + os.path.basename(lm_path) if has_lm
                  else "OU importer un .pdf / .docx"),
            font=ctk.CTkFont(size=11),
            text_color=(THEME.green_ok if has_lm else THEME.text_muted),
            anchor="w"
        )
        self.lm_file_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            file_row,
            text=("Remplacer" if has_lm else "Importer fichier"),
            command=self._import_lettre, height=26, width=130,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=11)
        ).grid(row=0, column=1, padx=(8, 0))

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
            if (hasattr(self, "exp_comp_chips")
                    and self.exp_comp_chips.winfo_exists()):
                exp["competences"] = self.exp_comp_chips.get_values()
        except Exception:
            pass
        try:
            if (hasattr(self, "exp_lang_chips")
                    and self.exp_lang_chips.winfo_exists()):
                exp["langues"] = self.exp_lang_chips.get_values()
        except Exception:
            pass

        save_config(self.cfg)
        return old_poste, p.get("poste_recherche", "")

    def save_profile(self):
        old_poste, new_poste = self._save_profile_silent()
        messagebox.showinfo("Sauvegardé", "Profil sauvegardé !")

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
                "CV non lisible",
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
            text=os.path.basename(path), text_color=THEME.green_ok
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
            text=os.path.basename(path), text_color=THEME.green_ok
        )
        messagebox.showinfo("Importé", f"Lettre importée : {os.path.basename(path)}")

    def _autofill_from_cv(self):
        docs = self.cfg.get("documents", {})
        text = docs.get("cv_text", "")
        if not text:
            messagebox.showwarning("Attention", "Importe d'abord un CV dans la section CV.")
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
                "Information",
                "Aucune info détectée automatiquement.\n\n"
                "Astuce : vérifie que Ollama est bien installé (Paramètres -> IA),\n"
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
        if "competences" in info and hasattr(self, "exp_comp_chips"):
            try:
                self.exp_comp_chips.set_values(info["competences"])
            except Exception:
                pass
        if "langues" in info and hasattr(self, "exp_lang_chips"):
            try:
                self.exp_lang_chips.set_values(info["langues"])
            except Exception:
                pass

        # Email → on l'enregistre côté Gmail (info du CV ≠ forcément mail d'envoi)
        detected = ", ".join(f"{k}={v}" for k, v in info.items() if k not in ("competences", "langues"))
        messagebox.showinfo(
            "Profil auto-rempli",
            f"Infos détectées :\n\n{detected}\n\n"
            f"Compétences : {len(info.get('competences', []))}\n"
            f"Langues : {len(info.get('langues', []))}\n\n"
            "Vérifie et corrige si besoin, puis clique sur Sauvegarder."
        )

    def _analyze_ats(self):
        docs = self.cfg.get("documents", {})
        path = docs.get("cv_path", "")
        text = docs.get("cv_text", "")
        if not path or not os.path.exists(path):
            messagebox.showwarning("Attention", "Importe d'abord un CV.")
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
        win.title("Analyse ATS")
        win.geometry("640x620")
        bring_to_front(win)

        ctk.CTkLabel(
            win,
            text=("Analyse ATS — Importé automatiquement" if auto else "Analyse ATS"),
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(16, 4), padx=20, anchor="w")

        score = report["score"]
        color = THEME.green_ok if score >= 80 else (THEME.amber if score >= 60 else
                                               THEME.amber if score >= 40 else THEME.red_danger)
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
                font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME.green_ok
            ).pack(anchor="w", pady=(5, 4))
            for icon, msg, _ in report["passed"]:
                ctk.CTkLabel(
                    scroll, text=f"{icon}  {msg}",
                    wraplength=560, justify="left", anchor="w"
                ).pack(anchor="w", padx=10, pady=1)

        if report["issues"]:
            ctk.CTkLabel(
                scroll, text="Ce que ça change pour toi si tu n'améliores pas",
                font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME.red_danger
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
        self._set_active("PARAMÈTRES")
        self._remember_tab("settings")
        self._clear_main()

        api = self.cfg.setdefault("api", {})
        rech = self.cfg.setdefault("recherche", {})
        srcs = self.cfg.setdefault("sources", {})

        # Header
        head = ctk.CTkFrame(self.main, fg_color="transparent")
        head.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            head, text="Paramètres",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=THEME.text_primary
        ).pack(side="left")
        ctk.CTkLabel(
            head, text="Comptes, modèle IA, préférences de recherche.",
            font=ctk.CTkFont(size=12),
            text_color=THEME.text_muted
        ).pack(side="left", padx=(12, 0), pady=(4, 0))

        # CTkTabview
        tabs = ctk.CTkTabview(
            self.main, fg_color=THEME.bg,
            segmented_button_fg_color=THEME.bg_panel_alt,
            segmented_button_selected_color=THEME.accent,
            segmented_button_selected_hover_color=THEME.accent_hover,
            segmented_button_unselected_color=THEME.bg_panel_alt,
            segmented_button_unselected_hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
        )
        tabs.pack(fill="both", expand=True, pady=(0, 0))

        tab_comptes = tabs.add("Comptes")
        tab_ia      = tabs.add("IA")
        tab_rech    = tabs.add("Recherche")
        tab_maj     = tabs.add("Mises à jour")

        # ── Onglet Comptes ──
        self._build_settings_comptes(tab_comptes, api, srcs)

        # ── Onglet IA ──
        self._build_settings_ia(tab_ia, api)

        # ── Onglet Recherche ──
        self._build_settings_recherche(tab_rech, rech)

        # ── Onglet MAJ ──
        self._build_settings_maj(tab_maj)

        # ── Footer sticky : Sauvegarder ──
        footer = ctk.CTkFrame(self.main, fg_color="transparent")
        footer.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(
            footer,
            text="Modifications auto-sauvegardées au changement de page.",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="Sauvegarder",
            image=theme.ctk_icon(theme.icon_save, size=14, color="#FFFFFF"),
            compound="left",
            command=self.save_settings, height=36, width=160, corner_radius=18,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="right")

    # ── Helpers status / connexion ──────────────────────────────
    def _is_gmail_configured(self, api):
        return bool((api.get("gmail_user") or "").strip()
                    and (api.get("gmail_password") or "").strip())

    def _is_ft_configured(self, api):
        return bool((api.get("ft_client_id") or "").strip()
                    and (api.get("ft_client_secret") or "").strip())

    def _is_adzuna_configured(self, api):
        return bool((api.get("adzuna_app_id") or "").strip()
                    and (api.get("adzuna_app_key") or "").strip())

    def _is_openai_configured(self, api):
        return bool((api.get("openai_key") or "").strip())

    def _is_anthropic_configured(self, api):
        return bool((api.get("anthropic_key") or "").strip())

    def _is_ollama_configured(self):
        try:
            from ollama_installer import is_ollama_installed, is_ollama_running
            return is_ollama_installed() and is_ollama_running()
        except Exception:
            return False

    def _service_card(self, parent, *, logo, name, sub,
                      status_text, status_color,
                      actions=None, expanded_body=None):
        """Construit une card de service avec status + boutons.

        actions : liste de (label, callback, primary=False)
        expanded_body : callable(frame) qui remplit le body du dépliage
        """
        card = ctk.CTkFrame(
            parent, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=8
        )
        card.pack(fill="x", pady=(0, 10))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=12)

        # Logo carré
        logo_box = ctk.CTkFrame(
            top, width=34, height=34,
            fg_color=THEME.bg_panel_alt, corner_radius=8
        )
        logo_box.pack(side="left", padx=(0, 12))
        logo_box.pack_propagate(False)
        ctk.CTkLabel(
            logo_box, text=logo,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=THEME.text_secondary
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Nom + description
        info = ctk.CTkFrame(top, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            info, text=name, font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME.text_primary, anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            info, text=sub, font=ctk.CTkFont(size=11),
            text_color=THEME.text_secondary, anchor="w"
        ).pack(anchor="w", pady=(1, 0))

        # Status (dot + texte)
        status = ctk.CTkFrame(top, fg_color="transparent")
        status.pack(side="left", padx=(10, 14))
        dot = ctk.CTkFrame(status, width=8, height=8, corner_radius=4,
                            fg_color=status_color)
        dot.pack(side="left", padx=(0, 6), pady=(2, 0))
        dot.pack_propagate(False)
        ctk.CTkLabel(
            status, text=status_text, font=ctk.CTkFont(size=11),
            text_color=status_color
        ).pack(side="left")

        # Actions
        if actions:
            btn_box = ctk.CTkFrame(top, fg_color="transparent")
            btn_box.pack(side="right")
            for action in actions:
                label, cmd = action[0], action[1]
                primary = len(action) > 2 and action[2]
                ctk.CTkButton(
                    btn_box, text=label, command=cmd,
                    height=28, width=92, corner_radius=6,
                    fg_color=(THEME.accent if primary else THEME.bg_panel_alt),
                    hover_color=(THEME.accent_hover if primary else THEME.bg_hover),
                    text_color=(("white" if primary else THEME.text_primary)),
                    font=ctk.CTkFont(size=11)
                ).pack(side="left", padx=(0, 6))

        # Body déplié
        if expanded_body is not None:
            sep = ctk.CTkFrame(card, height=1, fg_color=THEME.border)
            sep.pack(fill="x", padx=14)
            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=14, pady=(10, 12))
            try:
                expanded_body(body)
            except Exception as e:
                ctk.CTkLabel(
                    body, text=f"Erreur : {e}",
                    text_color=THEME.red_danger
                ).pack()

        return card

    def _entry_row(self, parent, label, attr_name, value, show=None,
                   placeholder=None):
        """Ligne label + entry à packer dans un body de card.
        Stocke le widget sous self.<attr_name>."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            row, text=label, font=ctk.CTkFont(size=11),
            text_color=THEME.text_secondary, width=110, anchor="w"
        ).pack(side="left")
        kwargs = {"height": 28, "font": ctk.CTkFont(size=11)}
        if show:
            kwargs["show"] = show
        if placeholder:
            kwargs["placeholder_text"] = placeholder
        entry = ctk.CTkEntry(row, **kwargs)
        entry.insert(0, value or "")
        entry.pack(side="left", fill="x", expand=True)
        setattr(self, attr_name, entry)
        return entry

    # ── Onglet Comptes ──────────────────────────────────────────
    def _build_settings_comptes(self, parent, api, srcs):
        wrap = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=2, pady=10)

        # Comptage
        configured = sum([
            self._is_gmail_configured(api),
            self._is_ft_configured(api),
            self._is_adzuna_configured(api),
        ])
        ctk.CTkLabel(
            wrap, text=f"{configured} sur 3 services configurés",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        ).pack(anchor="w", pady=(0, 8))

        # — Gmail —
        gmail_ok = self._is_gmail_configured(api)
        def _gmail_body(b):
            self._entry_row(b, "Adresse",      "gmail_user_entry",
                            api.get("gmail_user"),
                            placeholder="ton.adresse@gmail.com")
            self._entry_row(b, "Mot de passe", "gmail_pwd_entry",
                            api.get("gmail_password"), show="*",
                            placeholder="abcd efgh ijkl mnop")
            help_row = ctk.CTkFrame(b, fg_color="transparent")
            help_row.pack(fill="x", pady=(6, 0))
            ctk.CTkLabel(
                help_row,
                text="Le mot de passe est un \"Mot de passe d'application\" Google",
                font=ctk.CTkFont(size=10),
                text_color=THEME.text_muted, anchor="w"
            ).pack(side="left")
            ctk.CTkButton(
                help_row, text="Comment ?",
                command=self._show_gmail_info,
                height=22, width=80,
                fg_color="transparent", hover_color=THEME.bg_hover,
                text_color=THEME.blue_link,
                font=ctk.CTkFont(size=10, underline=True)
            ).pack(side="left", padx=(8, 0))

        self._service_card(
            wrap, logo="G", name="Gmail SMTP",
            sub=(api.get("gmail_user") if gmail_ok
                 else "Envoi automatique des candidatures"),
            status_text="Connecté" if gmail_ok else "Non configuré",
            status_color=THEME.green_ok if gmail_ok else THEME.amber,
            actions=([("Tester", self._test_gmail_connection)] if gmail_ok
                     else None),
            expanded_body=_gmail_body
        )

        # — France Travail —
        ft_ok = self._is_ft_configured(api)
        def _ft_body(b):
            self._entry_row(b, "Client ID",     "ft_id_entry",
                            api.get("ft_client_id"))
            self._entry_row(b, "Client Secret", "ft_secret_entry",
                            api.get("ft_client_secret"), show="*")
            link_row = ctk.CTkFrame(b, fg_color="transparent")
            link_row.pack(fill="x", pady=(6, 0))
            ctk.CTkButton(
                link_row, text="→ Créer un compte sur francetravail.io",
                command=lambda: self._open_url("https://francetravail.io/"),
                height=22, width=240,
                fg_color="transparent", hover_color=THEME.bg_hover,
                text_color=THEME.blue_link,
                font=ctk.CTkFont(size=10, underline=True)
            ).pack(side="left")

        self._service_card(
            wrap, logo="FT", name="France Travail",
            sub="Source officielle, gratuite, recommandée",
            status_text="Connecté" if ft_ok else "Non configuré",
            status_color=THEME.green_ok if ft_ok else THEME.amber,
            actions=([("Tester", self._test_ft_connection)] if ft_ok
                     else None),
            expanded_body=_ft_body
        )

        # — Adzuna avec toggle ON/OFF —
        adz_ok = self._is_adzuna_configured(api)
        adz_enabled = bool(srcs.get("adzuna", False))

        def _adz_body(b):
            self._entry_row(b, "App ID",  "adzuna_id_entry",
                            api.get("adzuna_app_id"))
            self._entry_row(b, "App Key", "adzuna_key_entry",
                            api.get("adzuna_app_key"), show="*")
            link_row = ctk.CTkFrame(b, fg_color="transparent")
            link_row.pack(fill="x", pady=(6, 0))
            ctk.CTkButton(
                link_row, text="→ Inscription gratuite (1000 req/mois)",
                command=lambda: self._open_url("https://developer.adzuna.com/signup"),
                height=22, width=240,
                fg_color="transparent", hover_color=THEME.bg_hover,
                text_color=THEME.blue_link,
                font=ctk.CTkFont(size=10, underline=True)
            ).pack(side="left")

        # Toggle Adzuna ON/OFF — modifie self.cfg directement
        def _toggle_adzuna():
            new_val = not bool(self.cfg.setdefault("sources", {}).get("adzuna", False))
            self.cfg["sources"]["adzuna"] = new_val
            save_config(self.cfg)
            # Re-rendre la page pour mettre à jour le statut
            self.after(50, self.show_settings)

        toggle_label = "Activé" if adz_enabled else "Désactivé"
        self._service_card(
            wrap, logo="AZ", name="Adzuna",
            sub="Facultatif — 1000 req/mois gratuites",
            status_text=("Activé" if adz_enabled and adz_ok
                         else "Désactivé" if not adz_enabled
                         else "Clé manquante"),
            status_color=(THEME.green_ok if adz_enabled and adz_ok
                          else THEME.text_muted if not adz_enabled
                          else THEME.amber),
            actions=[("Activé" if adz_enabled else "Désactivé",
                      _toggle_adzuna, adz_enabled)],
            expanded_body=_adz_body
        )

    # ── Onglet IA ──────────────────────────────────────────────
    def _build_settings_ia(self, parent, api):
        wrap = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=2, pady=10)

        # Moteur principal
        engine_card = ctk.CTkFrame(
            wrap, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=8
        )
        engine_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            engine_card, text="MOTEUR IA ACTIF",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME.text_secondary
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            engine_card,
            text="Ollama (local) est gratuit. OpenAI/Claude → plus rapide et qualitatif.",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        ).pack(anchor="w", padx=14, pady=(0, 8))

        engine_row = ctk.CTkFrame(engine_card, fg_color="transparent")
        engine_row.pack(fill="x", padx=14, pady=(0, 12))
        ai_engines = ["ollama", "openai", "claude", "template"]
        self.ai_engine_var = ctk.StringVar(value=api.get("ai_engine", "ollama"))
        ctk.CTkOptionMenu(
            engine_row, variable=self.ai_engine_var,
            values=ai_engines, width=200, height=32,
            fg_color=THEME.bg_panel_alt,
            button_color=THEME.bg_hover,
            button_hover_color=THEME.accent
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            engine_row, text="Tester la connexion",
            command=self._test_ai_connection,
            height=32, width=170,
            fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary,
            font=ctk.CTkFont(size=12)
        ).pack(side="left")
        self.ai_test_label = ctk.CTkLabel(
            engine_card, text="", font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        )
        self.ai_test_label.pack(anchor="w", padx=14, pady=(0, 10))

        # — Ollama —
        ollama_ok = self._is_ollama_configured()
        def _ollama_body(b):
            self._entry_row(b, "Modèle", "ollama_entry",
                            api.get("ollama_model", "gemma2:2b"),
                            placeholder="gemma2:2b")

        self._service_card(
            wrap, logo="OL", name="Ollama (local)",
            sub="IA gratuite, tourne sur ta machine",
            status_text="Opérationnel" if ollama_ok else "À installer",
            status_color=THEME.green_ok if ollama_ok else THEME.amber,
            actions=[("Installer", self._magic_install_ollama, True)] if not ollama_ok
                    else [("Réinstaller", self._magic_install_ollama)],
            expanded_body=_ollama_body
        )

        # — OpenAI —
        oai_ok = self._is_openai_configured(api)
        def _oai_body(b):
            self._entry_row(b, "Clé API", "openai_entry",
                            api.get("openai_key"), show="*",
                            placeholder="sk-...")
            ctk.CTkButton(
                b, text="→ Obtenir une clé sur platform.openai.com",
                command=lambda: self._open_url("https://platform.openai.com/api-keys"),
                height=22, width=300,
                fg_color="transparent", hover_color=THEME.bg_hover,
                text_color=THEME.blue_link,
                font=ctk.CTkFont(size=10, underline=True)
            ).pack(anchor="w", pady=(6, 0))

        self._service_card(
            wrap, logo="AI", name="OpenAI",
            sub="GPT-4o-mini — payant à l'usage (~0,001$ / candidature)",
            status_text="Clé configurée" if oai_ok else "Non configuré",
            status_color=THEME.green_ok if oai_ok else THEME.text_muted,
            expanded_body=_oai_body
        )

        # — Anthropic —
        an_ok = self._is_anthropic_configured(api)
        def _an_body(b):
            self._entry_row(b, "Clé API", "anthropic_entry",
                            api.get("anthropic_key"), show="*",
                            placeholder="sk-ant-...")
            ctk.CTkButton(
                b, text="→ Obtenir une clé sur console.anthropic.com",
                command=lambda: self._open_url("https://console.anthropic.com/settings/keys"),
                height=22, width=300,
                fg_color="transparent", hover_color=THEME.bg_hover,
                text_color=THEME.blue_link,
                font=ctk.CTkFont(size=10, underline=True)
            ).pack(anchor="w", pady=(6, 0))

        self._service_card(
            wrap, logo="AN", name="Anthropic Claude",
            sub="Claude Haiku — payant à l'usage (~0,002$ / candidature)",
            status_text="Clé configurée" if an_ok else "Non configuré",
            status_color=THEME.green_ok if an_ok else THEME.text_muted,
            expanded_body=_an_body
        )

    # ── Onglet Recherche ────────────────────────────────────────
    def _build_settings_recherche(self, parent, rech):
        wrap = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=2, pady=10)

        card = ctk.CTkFrame(
            wrap, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=8
        )
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            card, text="FILTRES PAR DÉFAUT",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME.text_secondary
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            card,
            text="Pré-remplit la page Recherche au lancement.",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        ).pack(anchor="w", padx=14, pady=(0, 10))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 12))

        self._entry_row(body, "Mots-clés", "mc_entry",
                        ", ".join(rech.get("mots_cles", [])),
                        placeholder="python, django, ...")
        self._entry_row(body, "Localisation", "loc_entry",
                        rech.get("localisation", ""),
                        placeholder="Paris")
        self._entry_row(body, "Rayon (km)", "km_entry",
                        str(rech.get("rayon_km", 30)))

        # Contrat — option menu (pas entry, donc pas dans _entry_row)
        contrat_row = ctk.CTkFrame(body, fg_color="transparent")
        contrat_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            contrat_row, text="Type de contrat",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_secondary, width=110, anchor="w"
        ).pack(side="left")
        self.contrat_var = ctk.StringVar(value=rech.get("contrat", "CDI"))
        ctk.CTkOptionMenu(
            contrat_row, variable=self.contrat_var,
            values=["Tous", "CDI", "CDD", "Stage", "Alternance", "Freelance"],
            width=200, height=28,
            fg_color=THEME.bg_panel_alt,
            button_color=THEME.bg_hover,
            button_hover_color=THEME.accent
        ).pack(side="left")

        # Card sources
        sources_card = ctk.CTkFrame(
            wrap, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=8
        )
        sources_card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            sources_card, text="SOURCES DE RECHERCHE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME.text_secondary
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            sources_card,
            text="Active / désactive les sites consultés (Indeed, LinkedIn, ...)",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        ).pack(anchor="w", padx=14, pady=(0, 10))
        ctk.CTkButton(
            sources_card, text="Gérer les sources →",
            command=self.show_sources_manager,
            height=32,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=14, pady=(0, 12))

    # ── Onglet Mises à jour ─────────────────────────────────────
    def _build_settings_maj(self, parent):
        wrap = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=2, pady=10)

        card = ctk.CTkFrame(
            wrap, fg_color=THEME.bg_panel,
            border_color=THEME.border, border_width=1, corner_radius=8
        )
        card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            card, text="VERSION INSTALLÉE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME.text_secondary
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            card, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=THEME.text_primary
        ).pack(anchor="w", padx=14, pady=(0, 4))
        ctk.CTkLabel(
            card,
            text="L'app vérifie les nouvelles versions sur GitHub Releases.",
            font=ctk.CTkFont(size=11),
            text_color=THEME.text_muted
        ).pack(anchor="w", padx=14, pady=(0, 12))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            btn_row, text="Vérifier les mises à jour",
            image=theme.ctk_icon(theme.icon_refresh, size=14, color="#FFFFFF"),
            compound="left",
            command=self._check_for_updates,
            height=36, width=240, corner_radius=18,
            fg_color=THEME.accent, hover_color=THEME.accent_hover,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        self._update_status_label = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=12),
            text_color=THEME.text_muted, wraplength=600, justify="left"
        )
        self._update_status_label.pack(anchor="w", padx=14, pady=(0, 12))

    # ── Tests de connexion ──────────────────────────────────────
    def _test_gmail_connection(self):
        """Test SMTP login sur le compte Gmail configuré."""
        user = self.cfg.get("api", {}).get("gmail_user", "").strip()
        pwd  = self.cfg.get("api", {}).get("gmail_password", "").strip()
        if not user or not pwd:
            messagebox.showwarning(
                "Gmail",
                "Renseigne d'abord l'adresse Gmail et le mot de passe d'application."
            )
            return

        def _test():
            try:
                import smtplib, ssl
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=8) as s:
                    s.login(user, pwd)
                self.after(0, lambda: messagebox.showinfo(
                    "Gmail OK",
                    f"Connexion SMTP réussie pour\n{user}"
                ))
            except smtplib.SMTPAuthenticationError:
                self.after(0, lambda: messagebox.showerror(
                    "Gmail — Erreur d'authentification",
                    "Le mot de passe est invalide.\n\n"
                    "Rappel : c'est un \"Mot de passe d'application\" (16 lettres) "
                    "généré sur myaccount.google.com/apppasswords — PAS ton mot de "
                    "passe Gmail habituel."
                ))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror(
                    "Gmail — Erreur",
                    f"Connexion impossible :\n{err[:200]}"
                ))
        threading.Thread(target=_test, daemon=True).start()

    def _test_ft_connection(self):
        """Test OAuth client_credentials sur l'API France Travail."""
        cid = self.cfg.get("api", {}).get("ft_client_id", "").strip()
        sec = self.cfg.get("api", {}).get("ft_client_secret", "").strip()
        if not cid or not sec:
            messagebox.showwarning(
                "France Travail",
                "Renseigne Client ID + Client Secret avant de tester."
            )
            return

        def _test():
            try:
                import urllib.parse, urllib.request, json as _json
                url = ("https://entreprise.francetravail.fr/connexion/oauth2/access_token"
                       "?realm=%2Fpartenaire")
                data = urllib.parse.urlencode({
                    "grant_type": "client_credentials",
                    "client_id": cid,
                    "client_secret": sec,
                    "scope": "api_offresdemploiv2 o2dsoffre"
                }).encode()
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    payload = _json.loads(r.read())
                if payload.get("access_token"):
                    self.after(0, lambda: messagebox.showinfo(
                        "France Travail OK",
                        "Token OAuth récupéré avec succès."
                    ))
                else:
                    self.after(0, lambda: messagebox.showerror(
                        "France Travail",
                        f"Réponse inattendue : {str(payload)[:200]}"
                    ))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror(
                    "France Travail — Erreur",
                    f"Connexion échouée :\n{err[:200]}"
                ))
        threading.Thread(target=_test, daemon=True).start()

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
            "Ton vrai mot de passe Gmail reste inchangé et privé."
        )
        ctk.CTkLabel(win, text=msg, justify="left", wraplength=480,
                     font=ctk.CTkFont(size=12)).pack(padx=20, anchor="w")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=15)
        ctk.CTkButton(
            btn_row, text="Ouvrir Google App Passwords",
            command=lambda: self._open_url("https://myaccount.google.com/apppasswords"),
            height=36, fg_color=THEME.accent, hover_color=THEME.accent_hover
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Fermer", command=win.destroy,
            height=36, fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        ).pack(side="left", padx=5)

        bring_to_front(win)

    def _test_ai_connection(self):
        self.ai_test_label.configure(text="Test en cours...", text_color=THEME.text_muted)
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
                        text="Connexion IA OK", text_color=THEME.green_ok))
                else:
                    self.after(0, lambda r=result: self.ai_test_label.configure(
                        text=f"Fallback template actif. {r[:80] if r else ''}",
                        text_color=THEME.amber))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self.ai_test_label.configure(
                    text=f"Erreur : {err[:100]}", text_color=THEME.red_danger))
        threading.Thread(target=task, daemon=True).start()

    # 🆕 Installateur magique Ollama
    def _magic_install_ollama(self):
        from ollama_installer import (is_ollama_installed, is_ollama_running,
                                       list_installed_models, DEFAULT_MODEL)

        win = ctk.CTkToplevel(self)
        win.title("Installation Ollama")
        win.geometry("580x480")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2 - 290
        py = self.winfo_y() + self.winfo_height() // 2 - 240
        win.geometry(f"+{px}+{py}")

        ctk.CTkLabel(
            win, text="INSTALLATION AUTOMATIQUE D'OLLAMA",
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
            status_txt = f"Ollama est opérationnel — modèle « {model_wanted} » prêt."
            status_color = THEME.green_ok
        elif installed and running:
            status_txt = f"Ollama installé mais le modèle « {model_wanted} » manque."
            status_color = THEME.amber
        elif installed:
            status_txt = "Ollama installé mais le serveur n'est pas lancé."
            status_color = THEME.amber
        else:
            status_txt = "Ollama n'est pas installé."
            status_color = THEME.red_danger

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
            btn_bar, text="Lancer l'installation",
            height=38, fg_color=THEME.accent, hover_color=THEME.accent_hover
        )
        change_btn = ctk.CTkButton(
            btn_bar, text="Télécharger un autre modèle",
            height=38, fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        )
        close_btn = ctk.CTkButton(
            btn_bar, text="Fermer", command=win.destroy,
            height=38, fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_hover,
            text_color=THEME.text_primary
        )

        def start(force_model=None):
            from ollama_installer import run_full_install, DEFAULT_MODEL
            model = force_model or model_wanted
            start_btn.configure(state="disabled", text="Installation…")
            change_btn.configure(state="disabled")

            def on_progress(msg):
                win.after(0, append, msg)

            def on_done(success, err):
                def finish():
                    if success:
                        append("")
                        append("Tout est prêt — l'IA est configurée sur Ollama.")
                        if hasattr(self, "ai_engine_var"):
                            self.ai_engine_var.set("ollama")
                        if hasattr(self, "ollama_entry"):
                            self.ollama_entry.delete(0, "end")
                            self.ollama_entry.insert(0, model)
                        if hasattr(self, "ai_test_label"):
                            self.ai_test_label.configure(
                                text="Ollama installé & connecté",
                                text_color=THEME.green_ok)
                        # Fin réussie → plus besoin de réinstaller, on grise
                        start_btn.configure(
                            text="Déjà installé",
                            state="disabled", fg_color=THEME.bg_panel_alt)
                        change_btn.configure(state="normal")
                    else:
                        append(f"\nÉchec : {err}")
                        start_btn.configure(text="Réessayer", state="normal")
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
                text="Déjà installé", state="disabled",
                fg_color=THEME.bg_panel_alt, hover_color=THEME.bg_panel_alt
            )
            append("Tout est opérationnel — rien à faire.")
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
        messagebox.showinfo("Sauvegardé", "Paramètres sauvegardés !")

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
        # Anti-doublon : si déjà ouverte, on la ramène au premier plan
        existing = getattr(self, "_help_win", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    bring_to_front(existing)
                    return
            except Exception:
                pass
        win = ctk.CTkToplevel(self)
        self._help_win = win
        # Quand le user ferme, on libère la référence
        win.protocol("WM_DELETE_WINDOW",
                     lambda w=win: (setattr(self, "_help_win", None),
                                    w.destroy()))
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
                font=ctk.CTkFont(size=22, weight="bold"),
                fg_color=THEME.bg_panel_alt,
                hover_color=THEME.bg_hover,
                text_color=THEME.text_primary,
                command=cmd,
            ).pack()
            ctk.CTkLabel(
                box, text=label, font=ctk.CTkFont(size=12)
            ).pack(pady=(6, 0))

        _icon(row, "PDF", "Manuel",
              lambda: (win.destroy(), self._open_user_manual_pdf()))
        _icon(row, "Mail", "Support",
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
                                text=f"{err}", text_color=THEME.red_danger)
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
                status.configure(text=f"{e}", text_color=THEME.red_danger)

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
        self._set_update_status("Vérification...", THEME.text_muted)
        threading.Thread(target=self._check_for_updates_async,
                         daemon=True).start()

    def _check_for_updates_async(self):
        """Fetch le manifest via urllib stdlib (évite conflit gzip avec
        curl_cffi). SSL context via certifi (sinon les bundles PyInstaller
        plantent en CERTIFICATE_VERIFY_FAILED — pas de CA store macOS)."""
        try:
            import json as _json
            import urllib.request, ssl
            try:
                import certifi
                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                ssl_ctx = ssl.create_default_context()
            req = urllib.request.Request(
                UPDATE_MANIFEST_URL,
                headers={
                    "User-Agent": "CandidatureBot-Updater/1.0",
                    "Accept-Encoding": "identity",  # pas de gzip
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}")
                body = resp.read().decode("utf-8", errors="replace")
            data = _json.loads(body)
            latest = data.get("version", "0")
            if self._version_tuple(latest) > self._version_tuple(APP_VERSION):
                self.after(0, lambda: self._show_update_available(data))
            else:
                self.after(0, lambda: self._set_update_status(
                    f"Vous avez la dernière version (v{APP_VERSION}).",
                    THEME.green_ok))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._set_update_status(
                f"Impossible de vérifier : {err}", THEME.red_danger))

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
        if messagebox.askyesno("Mise à jour disponible", msg):
            self._set_update_status("Téléchargement...", THEME.text_muted)
            threading.Thread(target=self._install_update_async,
                             args=(data,), daemon=True).start()
        else:
            self._set_update_status(
                f"Mise à jour v{version} disponible (annulée).", THEME.text_muted)

    def _install_update_async(self, data):
        """Télécharge le ZIP, l'extrait, sauvegarde l'ancien, remplace les
        fichiers (sauf config.json / data/ / .env), puis redémarre."""
        zip_path = None
        extract_root = None
        # Limite à 500 Mo (bundle inclut Scrapling/Playwright — peut peser ~150 Mo zippé)
        MAX_DOWNLOAD = 500 * 1024 * 1024
        try:
            import requests
            url = data.get("url")
            if not url:
                raise RuntimeError("URL du ZIP manquante dans le manifest.")
            if not (url.startswith("http://") or url.startswith("https://")):
                raise RuntimeError(f"URL invalide ({url[:30]}...).")

            # 1. Téléchargement
            self.after(0, lambda: self._set_update_status(
                "Téléchargement du paquet...", THEME.text_muted))
            zip_path = os.path.join(
                tempfile.gettempdir(),
                f"candidaturebot_{int(time.time())}.zip"
            )
            # Téléchargement via urllib pour éviter conflit gzip avec
            # curl_cffi/scrapling + SSL context via certifi pour les
            # bundles PyInstaller (CA store macOS absent).
            downloaded = 0
            import urllib.request as _urlrq
            import ssl as _ssl
            try:
                import certifi as _certifi
                _zip_ctx = _ssl.create_default_context(cafile=_certifi.where())
            except Exception:
                _zip_ctx = _ssl.create_default_context()
            zip_req = _urlrq.Request(url, headers={
                "User-Agent": "CandidatureBot-Updater/1.0",
                "Accept-Encoding": "identity",
            })
            with _urlrq.urlopen(zip_req, context=_zip_ctx, timeout=120) as r:
                if r.status >= 400:
                    raise RuntimeError(f"HTTP {r.status}")
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = r.read(64 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > MAX_DOWNLOAD:
                            raise RuntimeError(
                                f"Téléchargement > {MAX_DOWNLOAD // (1024*1024)} Mo — abandon."
                            )
                        f.write(chunk)

            # 2. Extraction
            self.after(0, lambda: self._set_update_status(
                "Extraction...", THEME.text_muted))
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
                "Sauvegarde de l'ancienne version...", THEME.text_muted))
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
                "Installation...", THEME.text_muted))
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
                f"Mise à jour v{new_v} installée — redémarrage...",
                THEME.green_ok))
            self.after(1500, self._restart_app)
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._set_update_status(
                f"Échec de l'installation : {err}", THEME.red_danger))
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
            f"v{new_v} prête — fermeture pour finaliser l'installation...",
            THEME.green_ok))

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
