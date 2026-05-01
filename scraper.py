"""
Scraper multi-sources : France Travail (API), Indeed, LinkedIn, APEC, Welcome to the Jungle.
+ support sites personnalisés (user/password, CSS selectors).

Stratégie : chaque source renvoie des dicts avec les clés normalisées :
  id, titre, entreprise, lieu, contrat, url, email, description, source
"""
import os
import json
import time
import hashlib
import urllib.parse as _urlp
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Headers navigateur réaliste pour contourner les blocages basiques
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_DEFAULT_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# Mapping du contrat choisi dans l'UI vers les codes de chaque API
# Valeur "Tous" (ou vide) → pas de filtre
_CONTRAT_MAP = {
    "CDI":        {"ft": "CDI",  "indeed": "fulltime",   "linkedin": "F", "apec": "CDI",         "wttj": "cdi"},
    "CDD":        {"ft": "CDD",  "indeed": "contract",   "linkedin": "C", "apec": "CDD",         "wttj": "cdd"},
    "Stage":      {"ft": "MIS",  "indeed": "internship", "linkedin": "I", "apec": "Stage",       "wttj": "internship"},
    "Alternance": {"ft": "E2",   "indeed": "internship", "linkedin": "I", "apec": "Alternance",  "wttj": "apprenticeship"},
    "Freelance":  {"ft": "FRE",  "indeed": "contract",   "linkedin": "C", "apec": "Freelance",   "wttj": "freelance"},
}


def _contrat_code(rech, source):
    c = (rech.get("contrat") or "").strip()
    if not c or c == "Tous":
        return None
    return _CONTRAT_MAP.get(c, {}).get(source)


def _hid(*parts):
    """Hash court pour dédup"""
    return hashlib.md5("|".join(p or "" for p in parts).encode()).hexdigest()[:10]


import re as _re
# Regex email standard, tolérante aux variantes habituelles
_EMAIL_RE = _re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
# Emails à exclure (systèmes, placeholders, trackers)
_EMAIL_BLACKLIST_PREFIXES = (
    "noreply", "no-reply", "donotreply", "no.reply", "notifications",
    "mailer-daemon", "postmaster", "webmaster",
)
_EMAIL_BLACKLIST_DOMAINS = (
    "sentry.io", "segment.com", "tracker.", "example.com", "test.com",
)


def _find_email(text):
    """Retourne le premier email 'candidature' plausible dans le texte, ou ''."""
    if not text:
        return ""
    for m in _EMAIL_RE.finditer(text):
        email = m.group(0).lower()
        local = email.split("@", 1)[0]
        domain = email.split("@", 1)[1] if "@" in email else ""
        if any(local.startswith(p) for p in _EMAIL_BLACKLIST_PREFIXES):
            continue
        if any(b in domain for b in _EMAIL_BLACKLIST_DOMAINS):
            continue
        return email
    return ""


class OffreScraper:
    def __init__(self, config):
        self.config = config
        self.offres_path = "data/offres.json"

    # ============================================================
    # Dispatcher
    # ============================================================
    def search_all(self, keywords=None, location=None, radius=None,
                   contrat=None, progress_cb=None):
        rech = self.config.setdefault("recherche", {})
        if keywords:
            rech["mots_cles"] = keywords if isinstance(keywords, list) else \
                [k.strip() for k in str(keywords).split(",") if k.strip()]
        if location:
            rech["localisation"] = location
        if radius is not None:
            try:
                rech["rayon_km"] = int(radius)
            except (ValueError, TypeError):
                rech["rayon_km"] = 30
        if contrat:
            rech["contrat"] = contrat

        sources = self.config.get("sources", {})
        custom = self.config.get("custom_sources", [])

        def notify(msg):
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        all_offres = []

        source_map = [
            ("france_travail",     "🇫🇷 France Travail",     self._src_france_travail),
            ("indeed",             "🔴 Indeed",              self._src_indeed),
            ("linkedin",           "🔵 LinkedIn",            self._src_linkedin),
            ("apec",               "🟠 APEC",                self._src_apec),
            ("welcometothejungle", "🟢 Welcome to the Jungle", self._src_wttj),
            ("hellowork",          "💼 HelloWork",           self._src_hellowork),
            ("adzuna",             "🔍 Adzuna",              self._src_adzuna),
        ]

        for key, label, fn in source_map:
            if not sources.get(key):
                continue
            notify(f"🔎 Recherche sur {label}…")
            try:
                offres = fn(rech) or []
                for o in offres:
                    o.setdefault("source", key)
                all_offres.extend(offres)
                notify(f"✅ {label} : {len(offres)} offre(s)")
            except Exception as e:
                notify(f"⚠️ {label} : {str(e)[:60]}")

        # Sources personnalisées (scraping générique)
        for site in custom:
            name = site.get("nom") or site.get("url_base", "custom")
            notify(f"🔎 {name}…")
            try:
                offres = self._src_custom(site, rech) or []
                for o in offres:
                    o.setdefault("source", f"custom:{name}")
                all_offres.extend(offres)
                notify(f"✅ {name} : {len(offres)} offre(s)")
            except Exception as e:
                notify(f"⚠️ {name} : {str(e)[:60]}")

        # Dédup par id
        seen = set()
        unique = []
        for o in all_offres:
            oid = o.get("id")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            unique.append(o)

        # Enrichissement : cherche un email plausible dans titre/description
        # si aucun n'a été fourni par l'API
        for o in unique:
            if o.get("email"):
                continue
            blob = " ".join([
                o.get("description", "") or "",
                o.get("titre", "") or "",
                o.get("entreprise", "") or "",
            ])
            found = _find_email(blob)
            if found:
                o["email"] = found

        self._save(unique, overwrite=False)
        notify(f"🎯 Total : {len(unique)} offre(s)")
        return unique

    # Conservé pour rétro-compat (main.py CLI)
    def search_and_save(self):
        offres = self._src_france_travail(self.config.get("recherche", {}))
        for o in offres:
            o.setdefault("source", "france_travail")
        self._save(offres)
        print(f"✅ {len(offres)} offres récupérées")

    # ============================================================
    # Sources individuelles
    # ============================================================
    def _src_france_travail(self, rech):
        api_cfg = self.config.get("api", {})
        # Plusieurs noms d'env vars supportés (compat anciens .env)
        client_id = (
            api_cfg.get("ft_client_id")
            or os.getenv("FT_CLIENT_ID")
            or os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
        )
        client_secret = (
            api_cfg.get("ft_client_secret")
            or os.getenv("FT_CLIENT_SECRET")
            or os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
        )
        if not client_id or not client_secret:
            raise RuntimeError("FT_CLIENT_ID/SECRET manquant (Paramètres)")

        # Token
        tok_url = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
        r = requests.post(tok_url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        }, timeout=15)
        r.raise_for_status()
        token = r.json()["access_token"]

        params = {
            "motsCles": ",".join(rech.get("mots_cles", [])),
            "commune": rech.get("localisation", ""),
            "distance": rech.get("rayon_km", 20),
            "range": "0-49",
        }
        contrat_code = _contrat_code(rech, "ft")
        if contrat_code:
            if contrat_code == "E2":
                params["natureContrat"] = "E2,FS,FJ,FI,FT"
            else:
                params["typeContrat"] = contrat_code
        headers = {"Authorization": f"Bearer {token}", "User-Agent": _UA}
        url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {r.status_code}")

        out = []
        for o in r.json().get("resultats", []):
            out.append({
                "id": f"ft_{o.get('id','')}",
                "titre": o.get("intitule", ""),
                "entreprise": o.get("entreprise", {}).get("nom", "N/A"),
                "lieu": o.get("lieuTravail", {}).get("libelle", ""),
                "contrat": o.get("typeContrat", ""),
                "description": o.get("description", ""),
                "url": o.get("origineOffre", {}).get("urlOrigine", ""),
                "email": o.get("contact", {}).get("courriel", ""),
            })
        return out

    def _src_indeed(self, rech):
        kw = " ".join(rech.get("mots_cles", [])) or ""
        loc = rech.get("localisation", "")
        qp = {"q": kw, "l": loc}
        jt = _contrat_code(rech, "indeed")
        if jt:
            qp["jt"] = jt
        q = _urlp.urlencode(qp)
        url = f"https://fr.indeed.com/jobs?{q}"

        # Session persistante + headers navigateur réalistes pour contourner
        # les protections basiques d'Indeed (note : Indeed utilise aussi
        # Cloudflare/PerimeterX, certains blocages sont incontournables sans proxy).
        sess = requests.Session()
        browser_headers = {
            **_DEFAULT_HEADERS,
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Cache-Control": "max-age=0",
        }
        sess.headers.update(browser_headers)

        try:
            # 1) On « chauffe » la session en visitant la homepage (cookies + anti-bot)
            try:
                sess.get("https://fr.indeed.com/", timeout=10)
                time.sleep(0.6)
            except requests.exceptions.RequestException:
                pass

            # 2) Requête de recherche avec Referer homepage
            r = sess.get(
                url,
                headers={
                    "Referer": "https://fr.indeed.com/",
                    "Sec-Fetch-Site": "same-origin",
                },
                timeout=15,
            )
            if r.status_code == 403:
                raise RuntimeError(
                    "HTTP 403 — Indeed bloque le scraping "
                    "(Cloudflare). Utilise LinkedIn / France Travail / WTTJ à la place."
                )
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            return self._parse_indeed(r.text, url)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"connexion : {e}")

    def _parse_indeed(self, html, base):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        out = []
        # Indeed change régulièrement. On cible les cartes les plus stables.
        for card in soup.select("div.job_seen_beacon, a.tapItem, div.cardOutline")[:30]:
            titre_el = card.select_one("h2 a, h2 span[title]")
            entreprise_el = card.select_one("[data-testid='company-name'], .companyName")
            lieu_el = card.select_one("[data-testid='text-location'], .companyLocation")
            link_el = card.select_one("a[href]")
            if not titre_el:
                continue
            titre = titre_el.get("title") or titre_el.get_text(strip=True)
            if not titre:
                continue
            href = link_el.get("href") if link_el else ""
            url = _urlp.urljoin("https://fr.indeed.com", href) if href else base
            out.append({
                "id": f"indeed_{_hid(titre, url)}",
                "titre": titre,
                "entreprise": entreprise_el.get_text(strip=True) if entreprise_el else "",
                "lieu": lieu_el.get_text(strip=True) if lieu_el else "",
                "contrat": "",
                "description": "",
                "url": url,
                "email": "",
            })
        return out

    def _src_linkedin(self, rech):
        kw = " ".join(rech.get("mots_cles", [])) or ""
        loc = rech.get("localisation", "")
        qp = {"keywords": kw, "location": loc}
        jt = _contrat_code(rech, "linkedin")
        if jt:
            qp["f_JT"] = jt
        q = _urlp.urlencode(qp)
        url = f"https://www.linkedin.com/jobs/search/?{q}"
        # Pagination : LinkedIn renvoie ~25 cartes par page via l'endpoint
        # guest. On boucle jusqu'à plafond pour récupérer ~75 résultats max
        # tout en restant raisonnable (4 requêtes successives).
        max_pages = self.config.get("recherche", {}).get("linkedin_pages", 4)
        page_size = 25  # imposé par l'endpoint guest
        all_html = []
        for page in range(max_pages):
            start = page * page_size
            api_url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/"
                f"seeMoreJobPostings/search?{q}&start={start}"
            )
            try:
                r = requests.get(api_url, headers=_DEFAULT_HEADERS, timeout=15)
            except requests.exceptions.RequestException as e:
                if page == 0:
                    raise RuntimeError(f"connexion : {e}")
                break  # erreur sur une page suivante → on garde ce qu'on a
            if r.status_code >= 400:
                if page == 0:
                    raise RuntimeError(
                        f"HTTP {r.status_code} (LinkedIn bloque souvent sans login)"
                    )
                break  # rate-limit après quelques pages → arrêt propre
            page_html = r.text
            # Si la page est vide (plus de résultats), on s'arrête
            if not page_html or len(page_html.strip()) < 100:
                break
            all_html.append(page_html)
            # Petite pause anti rate-limit entre pages
            if page < max_pages - 1:
                time.sleep(0.4)
        # On parse chaque page et on agrège
        out = []
        for html in all_html:
            out.extend(self._parse_linkedin(html, url))
        return out

    def _parse_linkedin(self, html, base):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        out = []
        # Plus de slice [:30] : la pagination remonte plusieurs pages,
        # le dédup côté search_all retire les doublons éventuels.
        for card in soup.select("li, div.base-card"):
            titre_el = card.select_one("h3.base-search-card__title, .job-search-card__title")
            entreprise_el = card.select_one(".base-search-card__subtitle, .job-search-card__subtitle")
            lieu_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
            if not titre_el:
                continue
            titre = titre_el.get_text(strip=True)
            href = link_el.get("href") if link_el else ""
            out.append({
                "id": f"linkedin_{_hid(titre, href)}",
                "titre": titre,
                "entreprise": entreprise_el.get_text(strip=True) if entreprise_el else "",
                "lieu": lieu_el.get_text(strip=True) if lieu_el else "",
                "contrat": "",
                "description": "",
                "url": href or base,
                "email": "",
            })
        return out

    def _src_apec(self, rech):
        kw = " ".join(rech.get("mots_cles", [])) or ""
        loc = rech.get("localisation", "")
        # L'APEC utilise une API JSON publique
        api = "https://www.apec.fr/cms/webservices/rechercheOffre"
        apec_contrat = _contrat_code(rech, "apec")
        payload = {
            "motsCles": kw,
            "lieux": [loc] if loc else [],
            "typesContrat": [apec_contrat] if apec_contrat else [],
            "pagination": {"range": {"startAt": 0, "endAt": 29}},
        }
        r = requests.post(api, json=payload, headers={
            **_DEFAULT_HEADERS,
            "Content-Type": "application/json",
            "Origin": "https://www.apec.fr",
            "Referer": "https://www.apec.fr/",
        }, timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except Exception:
            raise RuntimeError("JSON invalide")

        out = []
        for o in data.get("resultats", []):
            ident = o.get("numeroOffre") or o.get("@id", "")
            out.append({
                "id": f"apec_{ident or _hid(o.get('intitule',''))}",
                "titre": o.get("intitule", ""),
                "entreprise": o.get("nomCommercial") or o.get("libelleEntreprise", ""),
                "lieu": o.get("lieuTravail", {}).get("libelle", "")
                        if isinstance(o.get("lieuTravail"), dict) else str(o.get("lieuTravail", "")),
                "contrat": o.get("libelleTypeContrat", ""),
                "description": o.get("texteOffre") or o.get("descriptif", ""),
                "url": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{ident}" if ident else "",
                "email": "",
            })
        return out

    def _src_wttj(self, rech):
        kw = " ".join(rech.get("mots_cles", [])) or ""
        loc = rech.get("localisation", "")
        # Algolia public endpoint utilisé par WTTJ
        url = "https://csekhvms53-dsn.algolia.net/1/indexes/wttj_jobs_production_fr/query"
        params = {
            "x-algolia-application-id": "CSEKHVMS53",
            "x-algolia-api-key": "0f169f7e79e0d2f8c8f1e5b7a3f7a9e4",  # clé publique WTTJ
        }
        filters = []
        if loc:
            filters.append(f"office.city:{loc}")
        wttj_contrat = _contrat_code(rech, "wttj")
        if wttj_contrat:
            filters.append(f"contract_type:{wttj_contrat}")
        payload = {
            "query": kw,
            "hitsPerPage": 30,
            "page": 0,
            "filters": " AND ".join(filters) if filters else "",
        }
        try:
            r = requests.post(url, params=params, json=payload,
                              headers=_DEFAULT_HEADERS, timeout=15)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()
        except Exception as e:
            # Fallback : scrape HTML
            return self._wttj_html_fallback(kw, loc)

        out = []
        for hit in data.get("hits", []):
            slug = hit.get("slug") or hit.get("reference", "")
            out.append({
                "id": f"wttj_{hit.get('objectID') or _hid(hit.get('name',''))}",
                "titre": hit.get("name") or hit.get("title", ""),
                "entreprise": hit.get("organization", {}).get("name") if isinstance(hit.get("organization"), dict) else "",
                "lieu": (hit.get("office", {}) or {}).get("city", "") if isinstance(hit.get("office"), dict) else "",
                "contrat": hit.get("contract_type", ""),
                "description": hit.get("description", "") or hit.get("profile", ""),
                "url": f"https://www.welcometothejungle.com/fr/jobs/{slug}" if slug else "",
                "email": "",
            })
        return out

    def _wttj_html_fallback(self, kw, loc):
        q = _urlp.urlencode({"query": kw, "refinementList[offices.country_code][]": "FR"})
        r = requests.get(f"https://www.welcometothejungle.com/fr/jobs?{q}",
                         headers=_DEFAULT_HEADERS, timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for a in soup.select("a[href*='/fr/companies/'][href*='/jobs/']")[:20]:
            titre = a.get_text(strip=True)
            if not titre:
                continue
            out.append({
                "id": f"wttj_{_hid(titre, a.get('href',''))}",
                "titre": titre,
                "entreprise": "",
                "lieu": loc,
                "contrat": "",
                "description": "",
                "url": _urlp.urljoin("https://www.welcometothejungle.com", a.get("href", "")),
                "email": "",
            })
        return out

    # ============================================================
    # HelloWork — HTML scraping, marché français, pas d'auth requise
    # ============================================================
    def _src_hellowork(self, rech):
        kw = " ".join(rech.get("mots_cles", [])) or ""
        loc = rech.get("localisation", "")
        params = {"k": kw, "l": loc} if kw or loc else {}
        # 2 pages max pour ne pas se faire rate-limit
        all_html = []
        for page in range(1, 3):
            qp = dict(params)
            if page > 1:
                qp["p"] = page
            q = _urlp.urlencode(qp)
            url = f"https://www.hellowork.com/fr-fr/emploi/recherche.html?{q}"
            try:
                r = requests.get(url, headers=_DEFAULT_HEADERS, timeout=15)
            except requests.exceptions.RequestException:
                if page == 1:
                    raise
                break
            if r.status_code == 403:
                if page == 1:
                    raise RuntimeError("HelloWork 403 (anti-bot)")
                break
            if r.status_code >= 400:
                if page == 1:
                    raise RuntimeError(f"HTTP {r.status_code}")
                break
            all_html.append(r.text)
            if page < 2:
                time.sleep(0.5)

        from bs4 import BeautifulSoup
        out = []
        # Structure HelloWork (Apr 2026) : <div data-id-storage-target=...>
        # contenant un <h3> avec "TITRE+ENTREPRISE", puis spans avec
        # lieu / contrat / salaire / date séparés.
        # Le get_text(separator="|") nous donne :
        #   "Monteur Chauffagiste H/F | ENGIE | Paris 1er - 75 | CDI | 28 000 € | Voir l'offre | il y a 7 jours"
        for html in all_html:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("[data-id-storage-target]")
            if not cards:
                cards = soup.select("article, li.serp-item")  # fallback
            for card in cards:
                # Lien vers l'offre (toujours /fr-fr/emplois/<id>.html)
                link_el = card.select_one("a[href*='/emplois/'], a[href*='/offres/']")
                href = link_el.get("href") if link_el else ""
                full_url = _urlp.urljoin("https://www.hellowork.com", href) if href else ""

                # Titre : on prend le h3 (contient titre + entreprise collés)
                h3 = card.select_one("h3, h2")
                if not h3:
                    continue
                # Récupère le texte segmenté par "|"
                tokens = [t.strip() for t in card.get_text(separator="|").split("|")
                          if t.strip() and t.strip() != "Voir l'offre"]
                if not tokens:
                    continue

                # Heuristique : 1er token = titre, 2ème = entreprise,
                # 3ème = lieu, 4ème = contrat (si présent)
                titre = tokens[0]
                entreprise = tokens[1] if len(tokens) > 1 else ""
                lieu = tokens[2] if len(tokens) > 2 else ""
                contrat = tokens[3] if len(tokens) > 3 else ""

                # Filtre : si "il y a" / "j" dans contrat, c'était une date
                if any(s in contrat.lower() for s in ("il y a", " j", "jour", "heure")):
                    contrat = ""
                if not titre or len(titre) < 4:
                    continue

                out.append({
                    "id": f"hellowork_{_hid(titre, full_url)}",
                    "titre": titre,
                    "entreprise": entreprise,
                    "lieu": lieu,
                    "contrat": contrat,
                    "description": "",
                    "url": full_url,
                    "email": "",
                })
        return out

    # ============================================================
    # Adzuna — API JSON publique, clé gratuite (1000 req/mois)
    #   Inscription : https://developer.adzuna.com/signup
    # ============================================================
    def _src_adzuna(self, rech):
        api_cfg = self.config.get("api", {})
        app_id = api_cfg.get("adzuna_app_id") or os.getenv("ADZUNA_APP_ID")
        app_key = api_cfg.get("adzuna_app_key") or os.getenv("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            raise RuntimeError(
                "Clés Adzuna manquantes — inscription gratuite sur "
                "developer.adzuna.com (Paramètres → API Adzuna)"
            )
        kw = " ".join(rech.get("mots_cles", [])) or ""
        loc = rech.get("localisation", "")
        # Adzuna paginate : 50 résultats par page, on prend 2 pages = 100 max
        out = []
        for page in (1, 2):
            url = f"https://api.adzuna.com/v1/api/jobs/fr/search/{page}"
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": kw,
                "where": loc,
                "results_per_page": 50,
                "content-type": "application/json",
            }
            try:
                r = requests.get(url, params=params,
                                 headers={"User-Agent": _UA}, timeout=15)
            except requests.exceptions.RequestException as e:
                if page == 1:
                    raise RuntimeError(f"connexion : {e}")
                break
            if r.status_code >= 400:
                if page == 1:
                    raise RuntimeError(f"HTTP {r.status_code}")
                break
            try:
                data = r.json()
            except Exception:
                if page == 1:
                    raise RuntimeError("Réponse Adzuna invalide")
                break
            results = data.get("results") or []
            if not results:
                break
            for o in results:
                ident = str(o.get("id", ""))
                out.append({
                    "id": f"adzuna_{ident or _hid(o.get('title',''))}",
                    "titre": o.get("title", "").strip(),
                    "entreprise": (o.get("company") or {}).get("display_name", ""),
                    "lieu": (o.get("location") or {}).get("display_name", ""),
                    "contrat": o.get("contract_type", ""),
                    "description": o.get("description", ""),
                    "url": o.get("redirect_url", ""),
                    "email": "",
                })
            if page < 2:
                time.sleep(0.3)
        return out

    # ============================================================
    # Site personnalisé : GET avec user/password basic auth + sélecteurs CSS
    # ============================================================
    def _src_custom(self, site, rech):
        url_base = site.get("url_base", "").strip()
        if not url_base:
            return []

        user = site.get("user") or site.get("username") or ""
        pwd = site.get("password") or ""
        # Permet d'insérer les mots-clés / lieu dans l'URL via {keywords} {location}
        kw = " ".join(rech.get("mots_cles", []))
        loc = rech.get("localisation", "")
        try:
            url = url_base.format(
                keywords=_urlp.quote(kw),
                location=_urlp.quote(loc),
            )
        except (KeyError, IndexError):
            url = url_base

        auth = (user, pwd) if (user or pwd) else None
        r = requests.get(url, headers=_DEFAULT_HEADERS, auth=auth, timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")

        # Sélecteurs CSS optionnels
        sel_item = site.get("selector_item")
        sel_title = site.get("selector_title")
        sel_link = site.get("selector_link")
        if not sel_item or not sel_title:
            # Pas configuré : retourne juste une offre "page complète" signalée
            return [{
                "id": f"custom_{_hid(url)}",
                "titre": f"Page de {site.get('nom', 'site personnalisé')}",
                "entreprise": site.get("nom", ""),
                "lieu": "",
                "contrat": "",
                "description": "Configure des sélecteurs CSS pour extraire les offres.",
                "url": url,
                "email": "",
            }]

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for it in soup.select(sel_item)[:30]:
            title_el = it.select_one(sel_title)
            if not title_el:
                continue
            titre = title_el.get_text(strip=True)
            link_el = it.select_one(sel_link) if sel_link else (title_el if title_el.name == "a" else title_el.find("a"))
            href = link_el.get("href") if link_el else ""
            out.append({
                "id": f"custom_{_hid(titre, href)}",
                "titre": titre,
                "entreprise": site.get("nom", ""),
                "lieu": "",
                "contrat": "",
                "description": "",
                "url": _urlp.urljoin(url, href) if href else url,
                "email": "",
            })
        return out

    # ============================================================
    # Ajout manuel
    # ============================================================
    def add_manual(self, url_or_data):
        """Appelé depuis main.py (CLI) ou gui.py."""
        if isinstance(url_or_data, dict):
            offre = url_or_data
            offre.setdefault("id", f"manuel_{_hid(offre.get('url',''), offre.get('titre',''))}")
            offre.setdefault("source", "manuel")
        else:
            url = url_or_data
            offre = {
                "id": f"manuel_{_hid(url)}",
                "titre": input("Intitulé du poste : ").strip(),
                "entreprise": input("Entreprise : ").strip(),
                "lieu": input("Lieu : ").strip(),
                "description": input("Description : ").strip(),
                "url": url,
                "email": input("Email recruteur : ").strip(),
                "source": "manuel",
            }
        existing = self._load()
        existing.append(offre)
        self._save(existing, overwrite=True)
        return offre

    # ============================================================
    # Analyse d'une URL externe (nouvelle fonctionnalité)
    # ============================================================
    def analyze_url(self, url):
        """Récupère le contenu d'une page et extrait les infos basiques."""
        r = requests.get(url, headers=_DEFAULT_HEADERS, timeout=15)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        for t in soup(["script", "style", "noscript"]):
            t.decompose()

        titre = ""
        if soup.title and soup.title.string:
            titre = soup.title.string.strip()
        h1 = soup.select_one("h1")
        if h1:
            titre = h1.get_text(strip=True) or titre

        texte = soup.get_text("\n", strip=True)
        # Email
        import re
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", texte)
        email = emails[0] if emails else ""

        contrat = ""
        for c in ["CDI", "CDD", "Stage", "Alternance", "Freelance", "Intérim"]:
            if c.lower() in texte.lower():
                contrat = c
                break

        return {
            "titre": titre,
            "entreprise": "",
            "lieu": "",
            "contrat": contrat,
            "description": texte[:3000],
            "url": url,
            "email": email,
        }

    # ============================================================
    # Persistence
    # ============================================================
    def _load(self):
        if os.path.exists(self.offres_path):
            try:
                with open(self.offres_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self, offres, overwrite=False):
        os.makedirs(os.path.dirname(self.offres_path) or ".", exist_ok=True)
        if not overwrite:
            existing = self._load()
            ids = {o.get("id") for o in existing}
            for o in offres:
                if o.get("id") and o["id"] not in ids:
                    existing.append(o)
            offres = existing
        with open(self.offres_path, "w", encoding="utf-8") as f:
            json.dump(offres, f, indent=2, ensure_ascii=False)
