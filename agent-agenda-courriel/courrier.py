"""Accès à Gmail (IMAP et SMTP, mot de passe d'application) et à l'agenda Google (adresse secrète iCal),
avec les identifiants du coffre-fort de Windows (orchestra/agent-agenda-courriel/<nom>).

Lecture seule par défaut. Deux actions modifient le compte : déposer un brouillon (réversible : il se
supprime dans Gmail) et envoyer un mail (irréversible : seulement après validation, voir agent.py).
La variable ORCHESTRA_TEST_WEB (rejeu du kit de certification, jamais définie par Orchestra) remplace
Gmail et l'agenda par le serveur de test : GET /courriels.json, GET /agenda.ics, POST /brouillons, POST /envoi."""
import email, email.policy, imaplib, json, os, re, smtplib, ssl, urllib.parse, urllib.request
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parsedate_to_datetime

TEST_WEB = os.environ.get("ORCHESTRA_TEST_WEB", "").rstrip("/")
IMAP, SMTP = "imap.gmail.com", "smtp.gmail.com"
DELAI_S = 30


class Indisponible(Exception):
    """Compte, agenda ou identifiant indisponible : motif en français."""


# --- Coffre-fort -------------------------------------------------------------------------------------
def secret_lire(nom):
    """Identifiant orchestra/agent-agenda-courriel/<nom> du coffre-fort de Windows, ou None."""
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
    p = ctypes.POINTER(CREDENTIAL)()
    if not advapi.CredReadW(f"orchestra/agent-agenda-courriel/{nom}", 1, 0, ctypes.byref(p)):
        return None
    try:
        brut = bytes(p.contents.CredentialBlob[:p.contents.CredentialBlobSize])
        return (brut.decode("utf-16-le") if len(brut) % 2 == 0 else brut.decode("utf-8", "replace")).strip() or None
    finally:
        advapi.CredFree(p)


# --- Lecture ---------------------------------------------------------------------------------------------
def _texte(msg):
    """Corps texte d'un mail (text/plain de préférence, sinon HTML sans balises), 6 000 caractères au plus."""
    corps = msg.get_body(preferencelist=("plain", "html")) if msg.is_multipart() else msg
    try:
        t = corps.get_content() if corps else ""
    except (LookupError, KeyError):
        t = ""
    if corps is not None and corps.get_content_type() == "text/html":
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
        t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", t)).strip()[:6000]


def read_courriels(adresse, mot_de_passe, libelles, jours, maximum, recherche=""):
    """Mails Gmail portant l'un des libellés (ou répondant à la recherche Gmail), du plus récent au plus ancien."""
    if TEST_WEB:
        with urllib.request.urlopen(f"{TEST_WEB}/courriels.json", timeout=DELAI_S) as r:
            tous = json.loads(r.read())["courriels"]
        mots = [m.lower() for m in re.findall(r"\w+", recherche)]
        garde = [c for c in tous if (not libelles or set(c.get("libelles", [])) & set(libelles))
                 and all(m in json.dumps(c, ensure_ascii=False).lower() for m in mots)]
        return garde[:maximum]
    critere = (recherche or " OR ".join(f'label:"{l}"' for l in libelles)) + f" newer_than:{int(jours)}d"
    try:
        with imaplib.IMAP4_SSL(IMAP, ssl_context=ssl.create_default_context(), timeout=DELAI_S) as m:
            m.login(adresse, mot_de_passe)
            m.select('"[Gmail]/All Mail"', readonly=True)
            typ, data = m.search("UTF-8", "X-GM-RAW", f'"{critere}"'.encode("utf-8"))
            ids = (data[0] or b"").split()[::-1][:maximum]
            sortie = []
            for i in ids:
                typ, d = m.fetch(i, "(BODY.PEEK[] X-GM-LABELS)")
                brut = next((x[1] for x in d if isinstance(x, tuple)), b"")
                entete = next((x[0] for x in d if isinstance(x, tuple)), b"").decode("utf-8", "replace")
                msg = email.message_from_bytes(brut, policy=email.policy.default)
                try:
                    quand = parsedate_to_datetime(msg["Date"]).strftime("%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    quand = ""
                sortie.append({"id": i.decode(), "de": str(msg["From"] or ""), "a": str(msg["To"] or ""),
                               "objet": str(msg["Subject"] or "(sans objet)"), "date": quand, "message_id": str(msg["Message-ID"] or ""),
                               "libelles": _libelles(entete),
                               "texte": _texte(msg)})
            return sortie
    except (imaplib.IMAP4.error, OSError) as err:
        raise Indisponible(f"Gmail injoignable ou connexion refusée ({err}) : vérifie l'adresse et le mot de passe d'application")


def _libelles(entete):
    m = re.search(r"X-GM-LABELS \((.*?)\)", entete)
    return [a or b for a, b in re.findall(r'"([^"]*)"|([^\s"]+)', m.group(1))] if m else []


def read_agenda(adresse_ical):
    """Texte iCalendar de l'agenda (adresse secrète iCal de Google Agenda)."""
    url = f"{TEST_WEB}/agenda.ics" if TEST_WEB else adresse_ical
    if not url or not url.startswith("https://") and not TEST_WEB:
        raise Indisponible("adresse secrète iCal de l'agenda absente ou invalide (elle commence par https://calendar.google.com/)")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OrchestraAgenda/1.0"})
        with urllib.request.urlopen(req, timeout=DELAI_S) as r:
            return r.read(10 * 1024 * 1024).decode("utf-8", "replace")
    except (OSError, ValueError) as err:
        raise Indisponible(f"agenda injoignable ({getattr(err, 'reason', err)})")


# --- Messages ----------------------------------------------------------------------------------------------
def message(expediteur, destinataires, objet, corps, en_reponse_a=None, ics=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = expediteur, ", ".join(destinataires), objet
    m["Date"] = format_datetime(_maintenant())
    m["Message-ID"] = make_msgid(domain="orchestra.local")
    if en_reponse_a:
        m["In-Reply-To"] = en_reponse_a
        m["References"] = en_reponse_a
    m.set_content(corps)
    if ics:
        m.add_attachment(ics.encode("utf-8"), maintype="text", subtype="calendar", filename="invitation.ics",
                         params={"method": "REQUEST", "charset": "utf-8"})
    return m


def _maintenant():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# --- Actions sur le compte -------------------------------------------------------------------------------------
def action_deposer_brouillon(adresse, mot_de_passe, msg, raison):
    """Dépose le message dans les Brouillons de Gmail (réversible : le brouillon se supprime dans Gmail)."""
    if TEST_WEB:
        req = urllib.request.Request(f"{TEST_WEB}/brouillons", data=msg.as_bytes(), method="POST")
        with urllib.request.urlopen(req, timeout=DELAI_S) as r:
            r.read()
        return
    try:
        with imaplib.IMAP4_SSL(IMAP, ssl_context=ssl.create_default_context(), timeout=DELAI_S) as m:
            m.login(adresse, mot_de_passe)
            m.append('"[Gmail]/Drafts"', "\\Draft", imaplib.Time2Internaldate(_maintenant()), msg.as_bytes())
    except (imaplib.IMAP4.error, OSError) as err:
        raise Indisponible(f"brouillon non déposé dans Gmail ({err})")


def action_sensitive_envoyer(adresse, mot_de_passe, msg, raison):
    """Envoie le message par Gmail (SMTP). Irréversible : appelé seulement après validation de l'utilisateur."""
    if TEST_WEB:
        req = urllib.request.Request(f"{TEST_WEB}/envoi", data=msg.as_bytes(), method="POST")
        with urllib.request.urlopen(req, timeout=DELAI_S) as r:
            r.read()
        return
    try:
        with smtplib.SMTP_SSL(SMTP, 465, context=ssl.create_default_context(), timeout=DELAI_S) as s:
            s.login(adresse, mot_de_passe)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as err:
        raise Indisponible(f"envoi refusé par Gmail ({err})")
