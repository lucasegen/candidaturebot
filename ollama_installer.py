"""
Installation magique d'Ollama + modèle gemma2:2b.
- Sur macOS : utilise osascript pour demander les droits admin (popup natif).
- Sur Linux : utilise sudo (mot de passe terminal).
- Sur Windows : ouvre la page de download.

Callbacks :
  progress_cb(message)  → appelé pour chaque étape
  done_cb(success, err) → appelé à la fin
"""
import os
import sys
import ssl
import shutil
import subprocess
import platform
import threading
import time
import urllib.request


DEFAULT_MODEL = "gemma2:2b"


def _download(url, dest, progress_cb=None, chunk=1024 * 256):
    """Téléchargement robuste (contourne les bugs SSL macOS).
    Priorité : requests+certifi → urllib avec contexte SSL dégradé si échec.
    """
    # 1) Tentative via requests (certifi embarqué)
    try:
        import requests
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            with open(dest, "wb") as f:
                for block in r.iter_content(chunk):
                    if not block:
                        continue
                    f.write(block)
                    done += len(block)
                    if progress_cb and total:
                        progress_cb(int(done * 100 / total))
        return
    except Exception as e_req:
        last = e_req

    # 2) Fallback : urllib avec contexte SSL sans vérif (dernier recours)
    try:
        ctx = ssl.create_default_context()
    except Exception:
        ctx = ssl._create_unverified_context()
    try:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        pass
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            while True:
                block = r.read(chunk)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if progress_cb and total:
                    progress_cb(int(done * 100 / total))
        return
    except Exception as e_url:
        raise RuntimeError(
            f"Téléchargement impossible : {e_url}. "
            "Vérifie ta connexion internet. "
            "Sur macOS, lance aussi : /Applications/Python\\ 3.x/Install\\ Certificates.command"
        )


# Chemins habituels où Ollama s'installe sur chaque OS.
# IMPORTANT : quand on tourne dans un .app PyInstaller lancé depuis le
# Finder, le PATH ne contient PAS /usr/local/bin ni /opt/homebrew/bin →
# `shutil.which("ollama")` retourne None même si Ollama est installé.
# On cherche donc explicitement aux emplacements connus.
_OLLAMA_PATHS = [
    "/usr/local/bin/ollama",                                # macOS Intel / Linux
    "/opt/homebrew/bin/ollama",                             # macOS Apple Silicon (Homebrew)
    "/Applications/Ollama.app/Contents/Resources/ollama",   # macOS Ollama.app bundlé
    os.path.expanduser("~/.ollama/bin/ollama"),             # install custom
    "C:\\Program Files\\Ollama\\ollama.exe",                # Windows
]


def find_ollama_binary():
    """Retourne le chemin absolu du binaire Ollama, ou None s'il n'est
    pas trouvé. Cherche en priorité dans le PATH, puis dans les chemins
    standards (utile pour les apps frozen qui n'ont pas le PATH système)."""
    via_path = shutil.which("ollama")
    if via_path:
        return via_path
    for p in _OLLAMA_PATHS:
        if p and os.path.exists(p):
            return p
    return None


def is_ollama_installed():
    return find_ollama_binary() is not None


def is_ollama_running():
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def list_installed_models():
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def start_ollama_server():
    """Lance `ollama serve` en background si pas déjà actif.
    Utilise le chemin absolu du binaire pour fonctionner depuis un .app
    bundle où le PATH n'inclut pas /usr/local/bin."""
    if is_ollama_running():
        return True
    binary = find_ollama_binary()
    if not binary:
        return False
    try:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if platform.system() != "Windows":
            kwargs["start_new_session"] = True
        subprocess.Popen([binary, "serve"], **kwargs)
        # Attend que le serveur réponde (max 10s)
        for _ in range(20):
            if is_ollama_running():
                return True
            time.sleep(0.5)
    except Exception:
        pass
    return is_ollama_running()


def _install_ollama_macos(progress_cb):
    """
    Télécharge l'app .dmg, l'extrait, copie dans /Applications/ via osascript.
    → Popup natif de mot de passe macOS pour les droits admin.
    """
    progress_cb("⬇️  Téléchargement d'Ollama.app…")
    dmg_url = "https://ollama.com/download/Ollama.dmg"
    tmp_dmg = "/tmp/Ollama_candidaturebot.dmg"

    def _p(pct):
        progress_cb(f"⬇️  Téléchargement d'Ollama.app… {pct}%")
    _download(dmg_url, tmp_dmg, progress_cb=_p)

    progress_cb("📦 Montage du .dmg…")
    # Utilise hdiutil non-interactif
    mnt = subprocess.run(
        ["hdiutil", "attach", tmp_dmg, "-nobrowse", "-quiet"],
        capture_output=True, text=True, timeout=60
    )
    if mnt.returncode != 0:
        raise RuntimeError(f"Montage DMG échoué : {mnt.stderr[:200]}")

    # Trouve le point de montage
    mount_point = None
    for line in mnt.stdout.splitlines():
        parts = line.split("\t")
        if parts and parts[-1].strip().startswith("/Volumes/"):
            mount_point = parts[-1].strip()
            break
    if not mount_point:
        # Fallback : chercher /Volumes/Ollama*
        for d in os.listdir("/Volumes"):
            if d.lower().startswith("ollama"):
                mount_point = f"/Volumes/{d}"
                break
    if not mount_point:
        raise RuntimeError("Impossible de localiser le DMG monté")

    src_app = os.path.join(mount_point, "Ollama.app")
    if not os.path.exists(src_app):
        # Démonte avant de raise
        subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], capture_output=True)
        raise RuntimeError("Ollama.app introuvable dans le DMG")

    progress_cb("🔑 Installation dans /Applications (mot de passe Mac requis)…")
    # osascript = popup natif de mot de passe macOS
    cmd = f'do shell script "cp -R \\"{src_app}\\" /Applications/ && xattr -rd com.apple.quarantine /Applications/Ollama.app" with administrator privileges'
    result = subprocess.run(
        ["osascript", "-e", cmd],
        capture_output=True, text=True, timeout=120
    )

    # Démonte le DMG dans tous les cas
    subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], capture_output=True)
    try:
        os.remove(tmp_dmg)
    except OSError:
        pass

    if result.returncode != 0:
        err = result.stderr.strip()
        if "User canceled" in err or "(-128)" in err:
            raise RuntimeError("Installation annulée par l'utilisateur")
        raise RuntimeError(f"Installation échouée : {err[:200]}")

    # Lance Ollama.app pour qu'il installe son binaire en ligne de commande
    progress_cb("🚀 Lancement d'Ollama.app…")
    subprocess.Popen(["open", "-a", "Ollama"])
    # Attend que le binaire apparaisse dans le PATH (jusqu'à 30s)
    for _ in range(60):
        if is_ollama_installed():
            return
        time.sleep(0.5)

    # Fallback : on essaie le chemin direct du binaire embarqué
    bundled = "/Applications/Ollama.app/Contents/Resources/ollama"
    if os.path.exists(bundled):
        # Crée un symlink dans /usr/local/bin (déjà fait par l'app normalement)
        progress_cb("🔗 Lien symbolique /usr/local/bin/ollama…")
        link_cmd = f'do shell script "ln -sf {bundled} /usr/local/bin/ollama" with administrator privileges'
        subprocess.run(["osascript", "-e", link_cmd], capture_output=True, text=True, timeout=60)


def _install_ollama_linux(progress_cb):
    progress_cb("⬇️  Téléchargement du script d'installation Ollama…")
    script_path = "/tmp/ollama_install.sh"
    _download("https://ollama.com/install.sh", script_path)
    os.chmod(script_path, 0o755)
    progress_cb("🔑 Installation via sudo (mot de passe demandé dans le terminal)…")
    result = subprocess.run(
        ["sudo", "-A", "sh", script_path],
        capture_output=True, text=True, timeout=600
    )
    try:
        os.remove(script_path)
    except OSError:
        pass
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:200] or "installation échouée")


def _install_ollama_windows(progress_cb):
    """Sur Windows on ouvre la page de download (pas d'install silencieuse)."""
    progress_cb("🌐 Ouverture de la page de téléchargement Ollama…")
    import webbrowser
    webbrowser.open("https://ollama.com/download/windows")
    raise RuntimeError("Télécharge et installe Ollama.exe, puis relance ce bouton.")


def install_ollama(progress_cb):
    """Installe Ollama selon l'OS détecté."""
    sysname = platform.system()
    if sysname == "Darwin":
        _install_ollama_macos(progress_cb)
    elif sysname == "Linux":
        _install_ollama_linux(progress_cb)
    elif sysname == "Windows":
        _install_ollama_windows(progress_cb)
    else:
        raise RuntimeError(f"OS non supporté : {sysname}")


def pull_model(model, progress_cb):
    """Télécharge un modèle via l'API HTTP d'Ollama (avec stream de progression)."""
    import requests, json as _json
    if not is_ollama_running():
        if not start_ollama_server():
            raise RuntimeError("Impossible de démarrer ollama serve")

    progress_cb(f"📥 Téléchargement du modèle {model}…")
    r = requests.post(
        "http://localhost:11434/api/pull",
        json={"name": model, "stream": True},
        stream=True, timeout=3600,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")

    last = ""
    for line in r.iter_lines():
        if not line:
            continue
        try:
            ev = _json.loads(line.decode("utf-8"))
        except Exception:
            continue
        status = ev.get("status", "")
        total = ev.get("total")
        done = ev.get("completed")
        if total and done:
            pct = int(done * 100 / total)
            msg = f"📥 {status} — {pct}%"
        else:
            msg = f"📥 {status}"
        if msg != last:
            progress_cb(msg)
            last = msg
        if ev.get("error"):
            raise RuntimeError(ev["error"])


def run_full_install(config, save_config, progress_cb, done_cb,
                     model=DEFAULT_MODEL):
    """
    Thread-safe : tout se fait en arrière-plan.
    Met à jour config['api']['ai_engine'] = 'ollama' et ['ollama_model'] = model.
    """
    def task():
        try:
            if not is_ollama_installed():
                progress_cb("⚙️  Ollama non détecté — installation…")
                install_ollama(progress_cb)

            progress_cb("🚀 Démarrage du serveur Ollama…")
            if not start_ollama_server():
                raise RuntimeError("serveur Ollama inaccessible")

            if model not in list_installed_models():
                pull_model(model, progress_cb)
            else:
                progress_cb(f"✅ Modèle {model} déjà installé")

            # Mise à jour config
            config.setdefault("api", {})["ai_engine"] = "ollama"
            config["api"]["ollama_model"] = model
            save_config(config)

            progress_cb("🎉 Installation terminée, IA opérationnelle !")
            done_cb(True, None)
        except Exception as e:
            done_cb(False, str(e))

    threading.Thread(target=task, daemon=True).start()
