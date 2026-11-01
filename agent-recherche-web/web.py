"""Accès au web de l'agent « Recherche web » : moteurs de recherche officiels (API Brave Search avec une clé,
API de Wikipédia sans clé), lecture de pages, coffre-fort. Aucun moteur n'est lu en contournant ses protections.

Règles : seulement http(s) vers des adresses publiques (réseau local, machine et adresses réservées
refusés, y compris après une redirection) ; robots.txt respecté ; 2 Mo au plus par page ; aucun lien
trouvé dans une page n'est suivi. Le contenu lu est une donnée : il n'est jamais suivi comme un ordre.
La variable ORCHESTRA_TEST_WEB (réservée au rejeu du kit de certification, jamais définie par
Orchestra) remplace le moteur de recherche par le serveur de test et autorise sa seule adresse locale."""
import html, io, ipaddress, json, os, re, socket, urllib.error, urllib.parse, urllib.request, urllib.robotparser
from html.parser import HTMLParser

AGENT = "OrchestraRecherche/1.0 (+https://github.com/PBdan-dev/Orchestra_Agents)"
TAILLE_MAX = 2 * 1024 * 1024
DELAI_S = 15
TEST_WEB = os.environ.get("ORCHESTRA_TEST_WEB", "").rstrip("/")


class Refus(Exception):
    """Adresse ou page refusée (réseau local, robots.txt, type non pris en charge, trop grosse, erreur)."""


def read_adresse_publique(url):
    """Vérifie le schéma et que l'hôte ne désigne pas le réseau local. Lève Refus sinon."""
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Refus(f"adresse refusée (seuls http et https) : {url[:100]}")
    if TEST_WEB and f"{p.scheme}://{p.netloc}" == TEST_WEB:
        return
    try:
        adresses = {i[4][0] for i in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))}
    except OSError:
        raise Refus(f"site introuvable : {p.hostname}")
    for a in adresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise Refus(f"adresse du réseau local refusée : {p.hostname}")


class _Redirections(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        read_adresse_publique(newurl)          # une redirection vers le réseau local est refusée aussi
        return super().redirect_request(req, fp, code, msg, headers, newurl)





def read_http(url, entetes=None, taille=TAILLE_MAX):
    read_adresse_publique(url)
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "fr,en;q=0.7", **(entetes or {})})
    try:
        with urllib.request.build_opener(_Redirections()).open(req, timeout=DELAI_S) as r:
            corps = r.read(taille + 1)
            if len(corps) > taille:
                raise Refus("page de plus de 2 Mo")
            return r.geturl(), r.headers.get("Content-Type", ""), corps
    except urllib.error.HTTPError as e:
        raise Refus(f"le site a répondu {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Refus(f"site injoignable ({getattr(e, 'reason', e)})")


# --- Moteurs de recherche ----------------------------------------------------------------------
def read_recherche_wikipedia(requete, n=8):
    """Articles de Wikipédia en français (API officielle, sans clé) : moteur par défaut sans clé Brave."""
    url = "https://fr.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": requete, "srlimit": n, "format": "json", "utf8": 1})
    _, _, corps = read_http(url)
    return [{"titre": r["title"], "url": "https://fr.wikipedia.org/wiki/" + urllib.parse.quote(r["title"].replace(" ", "_")),
             "extrait": _texte_brut(r.get("snippet", ""))}
            for r in json.loads(corps).get("query", {}).get("search", [])[:n]]



def read_recherche_brave(requete, cle, n=10):
    """Résultats de l'API Brave Search (clé lue dans le coffre-fort)."""
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
        {"q": requete, "count": n, "search_lang": "fr", "country": "FR"})
    _, _, corps = read_http(url, {"Accept": "application/json", "X-Subscription-Token": cle})
    donnees = json.loads(corps)
    return [{"titre": _texte_brut(r.get("title", "")), "url": r.get("url", ""), "extrait": _texte_brut(r.get("description", ""))}
            for r in (donnees.get("web") or {}).get("results", [])[:n] if str(r.get("url", "")).startswith("http")]


def read_recherche_test(requete, n=10):
    """Moteur du rejeu du kit (ORCHESTRA_TEST_WEB) : /recherche rend {"resultats": [...]}."""
    _, _, corps = read_http(f"{TEST_WEB}/recherche?" + urllib.parse.urlencode({"q": requete}))
    return [{"titre": r.get("titre", ""), "url": r.get("url", ""), "extrait": r.get("extrait", "")}
            for r in json.loads(corps).get("resultats", [])[:n]]


def secret_cle_brave():
    """Clé de l'API Brave Search dans le coffre-fort de Windows (orchestra/agent-recherche-web/brave_api_key), ou None."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    pointeur = ctypes.POINTER(CREDENTIAL)()
    if not advapi.CredReadW("orchestra/agent-recherche-web/brave_api_key", 1, 0, ctypes.byref(pointeur)):
        return None
    try:
        c = pointeur.contents
        brut = bytes(c.CredentialBlob[:c.CredentialBlobSize])
        return (brut.decode("utf-16-le") if len(brut) % 2 == 0 else brut.decode("utf-8", "replace")).strip() or None
    finally:
        advapi.CredFree(pointeur)


# --- Lecture d'une page ---------------------------------------------------------------------------
_ROBOTS = {}


def read_robots_autorise(url):
    """robots.txt du site (lu une fois par site) : True si notre agent peut lire cette page (pas de robots.txt = autorisé)."""
    p = urllib.parse.urlsplit(url)
    site = f"{p.scheme}://{p.netloc}"
    if site not in _ROBOTS:
        try:
            _, _, corps = read_http(f"{site}/robots.txt", taille=512 * 1024)
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(corps.decode("utf-8", "replace").splitlines())
            _ROBOTS[site] = rp
        except Refus:
            _ROBOTS[site] = None
    return _ROBOTS[site] is None or _ROBOTS[site].can_fetch(AGENT, url)


def read_page(url):
    """Lit une page web publique : {"url", "titre", "date", "texte"}. Lève Refus avec un motif en français."""
    if not read_robots_autorise(url):
        raise Refus("le site interdit sa lecture aux robots (robots.txt)")
    finale, type_, corps = read_http(url)
    type_ = type_.lower()
    if "pdf" in type_ or corps[:5] == b"%PDF-":
        texte = _pdf(corps)
        premiere = next((l.strip() for l in texte.splitlines() if l.strip() and not l.startswith("[p.")), "")
        titre = premiere[:120] if 5 <= len(premiere) else urllib.parse.unquote(finale.rsplit("/", 1)[-1])
        return {"url": finale, "titre": f"{titre} (PDF)", "date": "", "texte": texte}
    if not any(t in type_ for t in ("html", "text/plain", "xml")) and type_:
        raise Refus(f"type de contenu non pris en charge ({type_.split(';')[0]})")
    texte = corps.decode(_encodage(type_, corps), "replace")
    if "html" not in type_ and "<html" not in texte[:2000].lower():
        return {"url": finale, "titre": finale, "date": "", "texte": texte.strip()}
    lecteur = _Lecteur()
    lecteur.feed(texte)
    contenu = "\n".join(l for l in lecteur.lignes if l)
    if len(contenu) < 200:
        raise Refus("page sans texte lisible (probablement construite en JavaScript)")
    return {"url": finale, "titre": lecteur.titre.strip() or finale, "date": lecteur.date, "texte": contenu}


def _pdf(corps):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise Refus("PDF non lu : la bibliothèque pypdf n'est pas installée dans l'environnement de l'agent")
    try:
        lecteur = PdfReader(io.BytesIO(corps))
        pages = [f"[p. {n}]\n{(p.extract_text() or '').strip()}" for n, p in enumerate(lecteur.pages, 1)]
    except Exception as e:      # pypdf lève des erreurs variées sur un PDF abîmé
        raise Refus(f"PDF illisible ({type(e).__name__})")
    texte = "\n\n".join(p for p in pages if len(p) > 10)
    if not texte:
        raise Refus("PDF sans texte (probablement scanné)")
    return texte


def _encodage(type_, corps):
    m = re.search(r"charset=([\w-]+)", type_) or re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', corps[:3000], re.I)
    nom = m.group(1) if m else "utf-8"
    nom = nom.decode() if isinstance(nom, bytes) else nom
    try:
        "".encode(nom)
        return nom
    except LookupError:
        return "utf-8"


def _date(texte):
    """Garde une date lisible (AAAA, AAAA-MM ou AAAA-MM-JJ), sinon rien."""
    return texte if re.fullmatch(r"(19|20)\d{2}(-\d{2}(-\d{2})?)?", texte) else ""


def _texte_brut(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


class _Lecteur(HTMLParser):
    """Texte principal d'une page : titres, paragraphes, listes, tableaux ; menus, scripts et pieds de page ignorés."""
    IGNORES = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button", "iframe", "template"}
    BLOCS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "pre", "blockquote", "div", "section", "article", "br", "dd", "dt", "td", "th"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lignes, self.courante, self.ignore, self.titre, self.dans_titre, self.date = [], "", 0, "", False, ""
        self.commentaires = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.IGNORES:
            self.ignore += 1
        if tag == "title":
            self.dans_titre = True
        if tag == "meta" and (a.get("property") or a.get("name") or "").lower() in ("article:published_time", "date", "dc.date"):
            self.date = _date((a.get("content") or "")[:10])
        if tag == "time" and not self.date and a.get("datetime"):
            self.date = _date(a["datetime"][:10])
        if tag in self.BLOCS:
            self._couper()
            if tag in ("h1", "h2", "h3"):
                self.courante = "#" * int(tag[1]) + " "
            elif tag == "li":
                self.courante = "- "

    def handle_endtag(self, tag):
        if tag in self.IGNORES and self.ignore:
            self.ignore -= 1
        if tag == "title":
            self.dans_titre = False
        if tag in self.BLOCS:
            self._couper()

    def handle_data(self, data):
        if self.dans_titre:
            self.titre += data
        elif not self.ignore:
            self.courante += data

    def _couper(self):
        ligne = re.sub(r"\s+", " ", self.courante).strip()
        if ligne and ligne not in ("-", "#", "##", "###"):
            self.lignes.append(ligne)
        self.courante = ""
