"""Agenda : lecture d'un calendrier iCalendar (.ics), répétitions simples, créneaux libres, écriture d'un
événement .ics. Bibliothèque standard ; heure de Paris calculée sans base de fuseaux (règle européenne).
Aucune fonction de ce fichier n'a d'effet : elles transforment du texte."""
import re, uuid
from datetime import date, datetime, timedelta, timezone

JOURS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
NOMS_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _dernier_dimanche(annee, mois):
    d = date(annee, mois + 1, 1) - timedelta(days=1) if mois < 12 else date(annee, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def decalage_paris(instant_utc):
    """Décalage de l'heure de Paris (UTC+1, UTC+2 du dernier dimanche de mars au dernier dimanche d'octobre, 1 h UTC)."""
    a = instant_utc.year
    debut = datetime.combine(_dernier_dimanche(a, 3), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    fin = datetime.combine(_dernier_dimanche(a, 10), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    return timedelta(hours=2) if debut <= instant_utc < fin else timedelta(hours=1)


def vers_local(instant_utc):
    """Instant UTC → heure de Paris, sans fuseau (naïve)."""
    return (instant_utc + decalage_paris(instant_utc)).replace(tzinfo=None)


def vers_utc(local):
    """Heure de Paris (naïve) → UTC."""
    essai = local.replace(tzinfo=timezone.utc) - timedelta(hours=1)
    return (local.replace(tzinfo=timezone.utc) - decalage_paris(essai))


def _lignes(texte):
    """Lignes « dépliées » d'un .ics (une ligne qui commence par une espace continue la précédente)."""
    lignes = []
    for l in texte.replace("\r\n", "\n").split("\n"):
        if l[:1] in (" ", "\t") and lignes:
            lignes[-1] += l[1:]
        elif l:
            lignes.append(l)
    return lignes


def _valeur(v):
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _date_ics(params, v):
    """DTSTART/DTEND → (datetime local Paris, journee_entiere)."""
    v = v.strip()
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", v):
        return datetime.strptime(v[:8], "%Y%m%d"), True
    if v.endswith("Z"):
        return vers_local(datetime.strptime(v[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)), False
    return datetime.strptime(v[:15], "%Y%m%dT%H%M%S"), False      # TZID ou heure flottante : lue comme heure de Paris


def _duree(v):
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v.strip())
    if not m:
        return timedelta(hours=1)
    s, w, d, h, mi, se = m.groups()
    t = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(se or 0))
    return -t if s == "-" else t


def lire_ics(texte):
    """Événements d'un calendrier : [{titre, debut, fin, journee, lieu, description, uid, rrule, exdates, recurrence_id}]."""
    evenements, courant = [], None
    for l in _lignes(texte):
        if l == "BEGIN:VEVENT":
            courant = {"titre": "(sans titre)", "lieu": "", "description": "", "exdates": set(), "rrule": None,
                       "recurrence_id": None, "statut": ""}
            continue
        if l == "END:VEVENT" and courant is not None:
            if "debut" in courant:
                if "fin" not in courant:
                    courant["fin"] = courant["debut"] + (courant.pop("duree", None) or (timedelta(days=1) if courant["journee"] else timedelta(hours=1)))
                courant.pop("duree", None)
                if courant["statut"] != "CANCELLED":
                    evenements.append(courant)
            courant = None
            continue
        if courant is None or ":" not in l:
            continue
        tete, v = l.split(":", 1)
        nom, *params = tete.split(";")
        params = ";".join(params)
        nom = nom.upper()
        try:
            if nom == "SUMMARY":
                courant["titre"] = _valeur(v)[:200]
            elif nom == "LOCATION":
                courant["lieu"] = _valeur(v)[:200]
            elif nom == "DESCRIPTION":
                courant["description"] = _valeur(v)[:1000]
            elif nom == "UID":
                courant["uid"] = v
            elif nom == "STATUS":
                courant["statut"] = v.strip().upper()
            elif nom == "DTSTART":
                courant["debut"], courant["journee"] = _date_ics(params, v)
            elif nom == "DTEND":
                courant["fin"] = _date_ics(params, v)[0]
            elif nom == "DURATION":
                courant["duree"] = _duree(v)
            elif nom == "RRULE":
                courant["rrule"] = dict(p.split("=", 1) for p in v.split(";") if "=" in p)
            elif nom == "EXDATE":
                for x in v.split(","):
                    courant["exdates"].add(_date_ics(params, x)[0])
            elif nom == "RECURRENCE-ID":
                courant["recurrence_id"] = _date_ics(params, v)[0]
        except ValueError:
            continue
    return evenements


def _occurrences(e, debut, fin, maximum=2000):
    """Dates de début d'un événement (répétitions DAILY, WEEKLY avec BYDAY, MONTHLY, YEARLY ; INTERVAL, COUNT, UNTIL)."""
    r = e["rrule"]
    if not r:
        return [e["debut"]] if e["debut"] < fin and e["fin"] > debut else []
    freq, pas = r.get("FREQ", ""), max(1, int(r.get("INTERVAL", "1") or 1))
    compte = int(r["COUNT"]) if r.get("COUNT", "").isdigit() else None
    jusqua = None
    if r.get("UNTIL"):
        try:
            jusqua = _date_ics("", r["UNTIL"])[0]
        except ValueError:
            jusqua = None
    jours = [JOURS.index(j[-2:]) for j in r.get("BYDAY", "").split(",") if j[-2:] in JOURS] if freq == "WEEKLY" else []
    sortie, n, courant, i = [], 0, e["debut"], 0
    while i < maximum:
        i += 1
        candidats = [courant]
        if freq == "WEEKLY" and jours:
            lundi = courant - timedelta(days=courant.weekday())
            candidats = sorted(lundi + timedelta(days=j) for j in jours)
            candidats = [c for c in candidats if c >= e["debut"]]
        for c in candidats:
            if (jusqua and c > jusqua) or (compte is not None and n >= compte) or c >= fin:
                return sortie
            n += 1
            if c not in e["exdates"] and c + (e["fin"] - e["debut"]) > debut:
                sortie.append(c)
        if freq == "DAILY":
            courant += timedelta(days=pas)
        elif freq == "WEEKLY":
            courant += timedelta(weeks=pas)
        elif freq == "MONTHLY":
            m = courant.month - 1 + pas
            try:
                courant = courant.replace(year=courant.year + m // 12, month=m % 12 + 1)
            except ValueError:
                courant = courant.replace(year=courant.year + m // 12, month=m % 12 + 1, day=28)
        elif freq == "YEARLY":
            courant = courant.replace(year=courant.year + pas)
        else:
            return sortie
    return sortie


def evenements_entre(evenements, debut, fin):
    """Occurrences comprises entre deux dates (datetime locales), triées, remplacements (RECURRENCE-ID) appliqués."""
    remplaces = {(e.get("uid"), e["recurrence_id"]) for e in evenements if e["recurrence_id"]}
    sortie = []
    for e in evenements:
        if e["recurrence_id"]:
            if e["debut"] < fin and e["fin"] > debut:
                sortie.append({**e})
            continue
        duree = e["fin"] - e["debut"]
        for c in _occurrences(e, debut, fin):
            if (e.get("uid"), c) not in remplaces:
                sortie.append({**e, "debut": c, "fin": c + duree})
    return sorted(sortie, key=lambda x: x["debut"])


def creneaux_libres(occupes, debut, fin, heures=(9, 18), duree_min=60, jours_ouvres=True):
    """Créneaux libres d'au moins duree_min minutes, dans les heures de travail, du lundi au vendredi par défaut."""
    libres, jour = [], debut.replace(hour=0, minute=0, second=0, microsecond=0)
    while jour < fin:
        if not jours_ouvres or jour.weekday() < 5:
            a, b = max(jour.replace(hour=heures[0]), debut), min(jour.replace(hour=heures[1]), fin)
            pris = sorted((max(o["debut"], a), min(o["fin"], b)) for o in occupes if o["debut"] < b and o["fin"] > a)
            curseur = a
            for p, q in pris:
                if p - curseur >= timedelta(minutes=duree_min):
                    libres.append((curseur, p))
                curseur = max(curseur, q)
            if b - curseur >= timedelta(minutes=duree_min):
                libres.append((curseur, b))
        jour += timedelta(days=1)
    return libres


def chevauchements(evenements, debut, fin):
    return [e for e in evenements if e["debut"] < fin and e["fin"] > debut and not e.get("journee")]


def _echapper(t):
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _plier(ligne):
    octets, sortie = ligne.encode("utf-8"), []
    while len(octets) > 74:
        coupe = 74
        while coupe > 0 and (octets[coupe] & 0xC0) == 0x80:
            coupe -= 1
        sortie.append(octets[:coupe].decode("utf-8"))
        octets = b" " + octets[coupe:]
    sortie.append(octets.decode("utf-8"))
    return "\r\n".join(sortie)


def ecrire_ics(titre, debut, fin, lieu="", description="", organisateur="", invites=(), methode="PUBLISH"):
    """Texte d'un fichier .ics d'un événement (heures en UTC). methode REQUEST pour une invitation."""
    def utc(d):
        return vers_utc(d).strftime("%Y%m%dT%H%M%SZ")
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Orchestra//agent-agenda-courriel//FR", f"METHOD:{methode}",
              "BEGIN:VEVENT", f"UID:{uuid.uuid4()}@orchestra", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
              f"DTSTART:{utc(debut)}", f"DTEND:{utc(fin)}", f"SUMMARY:{_echapper(titre)}"]
    if lieu:
        lignes.append(f"LOCATION:{_echapper(lieu)}")
    if description:
        lignes.append(f"DESCRIPTION:{_echapper(description)}")
    if organisateur:
        lignes.append(f"ORGANIZER:mailto:{organisateur}")
    for i in invites:
        lignes.append(f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{i}")
    lignes += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_plier(l) for l in lignes) + "\r\n"


def jour_fr(d):
    return f"{NOMS_JOURS[d.weekday()]} {d.day:02d}/{d.month:02d}/{d.year}"


def heure(d):
    return d.strftime("%H:%M")
