"""Lecture des documents du projet : PDF (pypdf, BSD-3), Word .docx, Excel .xlsx, CSV, texte et Markdown.

Chaque lecteur rend un document découpé en parties : [{"lieu": "p. 3", "texte": "..."}].
Le lieu sert aux renvois du résumé (« [p. 3] ») et aux contrôles par le code.
Word et Excel sont lus avec la bibliothèque standard (zipfile, xml) : aucune dépendance.
Le contenu lu est une donnée externe : il n'est jamais exécuté ni suivi comme une consigne."""
import csv, io, re, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

TAILLE_MAX_OCTETS = 50 * 1024 * 1024
LIGNES_MAX_FEUILLE = 2000
FORMATS = {".pdf": "pdf", ".docx": "word", ".xlsx": "excel", ".xlsm": "excel", ".csv": "csv",
           ".txt": "texte", ".md": "texte", ".markdown": "texte"}

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class Illisible(Exception):
    """Document qu'on ne peut pas lire (format, chiffrement, fichier abîmé, PDF scanné)."""


def format_de(chemin):
    return FORMATS.get(Path(chemin).suffix.lower())


def _decoder(octets):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return octets.decode(enc)
        except UnicodeDecodeError:
            continue
    return octets.decode("latin-1")


def _table_md(lignes):
    """Lignes de cellules → tableau Markdown (largeur = ligne la plus longue)."""
    lignes = [[str(c).replace("|", "\\|").replace("\n", " ").strip() for c in l] for l in lignes]
    lignes = [l for l in lignes if any(l)]
    if not lignes:
        return ""
    n = max(len(l) for l in lignes)
    lignes = [l + [""] * (n - len(l)) for l in lignes]
    md = ["| " + " | ".join(lignes[0]) + " |", "|" + "---|" * n]
    md += ["| " + " | ".join(l) + " |" for l in lignes[1:]]
    return "\n".join(md)


# --- PDF ----------------------------------------------------------------------------------------
def read_pdf(chemin):
    """Texte de chaque page d'un PDF (pypdf). Un PDF sans texte (scanné) est signalé illisible."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        raise Illisible("lecture des PDF impossible : la bibliothèque pypdf n'est pas installée dans l'environnement de l'agent")
    try:
        lecteur = PdfReader(str(chemin))
        if lecteur.is_encrypted and not lecteur.decrypt(""):
            raise Illisible("PDF protégé par un mot de passe")
        parties = []
        for n, page in enumerate(lecteur.pages, 1):
            texte = (page.extract_text() or "").strip()
            if texte:
                parties.append({"lieu": f"p. {n}", "texte": texte})
        nb_pages = len(lecteur.pages)
    except Illisible:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as err:
        raise Illisible(f"PDF abîmé ou illisible ({err})")
    if not parties:
        raise Illisible("PDF sans texte (probablement scanné) : la reconnaissance de caractères n'est pas prise en charge")
    return {"parties": parties, "pages": nb_pages}


# --- Word ---------------------------------------------------------------------------------------
def _texte_paragraphe(p):
    morceaux = []
    for n in p.iter():
        if n.tag == W + "t" and n.text:
            morceaux.append(n.text)
        elif n.tag == W + "tab":
            morceaux.append("\t")
        elif n.tag in (W + "br", W + "cr"):
            morceaux.append("\n")
    return "".join(morceaux).strip()


def _niveau_titre(p):
    style = p.find(f"{W}pPr/{W}pStyle")
    if style is None:
        return 0
    val = (style.get(W + "val") or "").lower()
    m = re.match(r"(?:heading|titre)\s*(\d)", val)
    if m:
        return int(m.group(1))
    return 1 if val in ("title", "titre") else 0


def read_word(chemin):
    """Paragraphes, titres et tableaux d'un .docx, dans l'ordre ; une partie par titre."""
    try:
        with zipfile.ZipFile(chemin) as z:
            racine = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as err:
        raise Illisible(f"fichier Word abîmé ou illisible ({err})")
    corps = racine.find(W + "body")
    parties, courante, lignes, n = [], "début du document", [], 0
    for el in list(corps) if corps is not None else []:
        if el.tag == W + "p":
            niveau, texte = _niveau_titre(el), _texte_paragraphe(el)
            if not texte:
                continue
            if niveau:
                if lignes:
                    parties.append({"lieu": courante, "texte": "\n".join(lignes)})
                n += 1
                courante, lignes = f"section « {texte[:60]} »", ["#" * min(niveau, 6) + " " + texte]
            else:
                lignes.append(texte)
        elif el.tag == W + "tbl":
            tableau =[[" ".join(t for t in (_texte_paragraphe(p) for p in cel.iter(W + "p")) if t)
                        for cel in ligne.iter(W + "tc")] for ligne in el.iter(W + "tr")]
            md = _table_md(tableau)
            if md:
                lignes.append(md)
    if lignes:
        parties.append({"lieu": courante, "texte": "\n".join(lignes)})
    if not parties:
        raise Illisible("document Word vide")
    return {"parties": parties}


# --- Excel --------------------------------------------------------------------------------------
FORMATS_DATE = set(range(14, 23)) | {45, 46, 47}


def _formats_date(z):
    """Indices de styles de cellule qui affichent une date (formats intégrés ou personnalisés)."""
    try:
        styles = ET.fromstring(z.read("xl/styles.xml"))
    except (KeyError, ET.ParseError):
        return set()
    perso = {}
    for f in styles.iter(S + "numFmt"):
        code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", f.get("formatCode", "")).lower()
        perso[int(f.get("numFmtId", 0))] = bool(re.search(r"[dyj]", code)) and "0" not in code and "#" not in code
    xfs = styles.find(S + "cellXfs")
    dates = set()
    for i, xf in enumerate(list(xfs) if xfs is not None else []):
        fid = int(xf.get("numFmtId", 0))
        if fid in FORMATS_DATE or perso.get(fid):
            dates.add(i)
    return dates


def _valeur(c, partagees, dates):
    t, v = c.get("t"), c.find(S + "v")
    if t == "s" and v is not None:
        return partagees[int(v.text)] if v.text and int(v.text) < len(partagees) else ""
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(S + "t"))
    if v is None or v.text is None:
        return ""
    if t == "b":
        return "VRAI" if v.text == "1" else "FAUX"
    if t in ("str", "e"):
        return v.text
    texte = v.text
    if int(c.get("s", 0)) in dates:
        try:
            jour = datetime(1899, 12, 30) + timedelta(days=float(texte))
            return jour.strftime("%Y-%m-%d" if float(texte).is_integer() else "%Y-%m-%d %H:%M")
        except (ValueError, OverflowError):
            return texte
    try:
        f = float(texte)
        return str(int(f)) if f.is_integer() else str(round(f, 10))
    except ValueError:
        return texte


def _colonne(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_excel(chemin):
    """Valeurs de chaque feuille d'un .xlsx (valeurs calculées, pas les formules) ; une partie par feuille."""
    try:
        with zipfile.ZipFile(chemin) as z:
            classeur = ET.fromstring(z.read("xl/workbook.xml"))
            liens = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(PR + "Relationship")}
            try:
                partagees = ["".join(x.text or "" for x in si.iter(S + "t"))
                             for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si")]
            except KeyError:
                partagees = []
            dates = _formats_date(z)
            parties = []
            for feuille in classeur.iter(S + "sheet"):
                cible = liens.get(feuille.get(R + "id"), "")
                cible = cible.lstrip("/") if cible.startswith("/") else "xl/" + cible
                donnees = ET.fromstring(z.read(cible))
                lignes, coupee = [], False
                for i, ligne in enumerate(donnees.iter(S + "row")):
                    if i >= LIGNES_MAX_FEUILLE:
                        coupee = True
                        break
                    cellules = {}
                    for c in ligne.iter(S + "c"):
                        cellules[_colonne(c.get("r", "A1"))] = _valeur(c, partagees, dates)
                    if cellules:
                        lignes.append([cellules.get(k, "") for k in range(max(cellules) + 1)])
                md = _table_md(lignes)
                if coupee:
                    md += f"\n(feuille coupée après {LIGNES_MAX_FEUILLE} lignes)"
                if md:
                    parties.append({"lieu": f"feuille « {feuille.get('name')} »", "texte": md})
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, AttributeError) as err:
        raise Illisible(f"fichier Excel abîmé ou illisible ({err})")
    if not parties:
        raise Illisible("classeur Excel vide")
    return {"parties": parties}


# --- CSV, texte, Markdown -------------------------------------------------------------------------
def read_csv(chemin):
    """Tableau CSV (séparateur deviné : ; , ou tabulation)."""
    with open(chemin, "rb") as f:
        texte = _decoder(f.read())
    try:
        dialecte = csv.Sniffer().sniff(texte[:5000], delimiters=";,\t")
    except csv.Error:
        dialecte = csv.excel
    lignes = list(csv.reader(io.StringIO(texte), dialecte))
    coupee = len(lignes) > LIGNES_MAX_FEUILLE
    md = _table_md(lignes[:LIGNES_MAX_FEUILLE]) + (f"\n(tableau coupé après {LIGNES_MAX_FEUILLE} lignes)" if coupee else "")
    if not md.strip():
        raise Illisible("fichier CSV vide")
    return {"parties": [{"lieu": "tableau", "texte": md}]}


def read_texte(chemin):
    """Fichier texte ou Markdown."""
    with open(chemin, "rb") as f:
        texte = _decoder(f.read()).strip()
    if not texte:
        raise Illisible("fichier vide")
    return {"parties": [{"lieu": "texte", "texte": texte}]}


LECTEURS = {"pdf": read_pdf, "word": read_word, "excel": read_excel, "csv": read_csv, "texte": read_texte}


def read_document(chemin):
    """Lit un document du projet selon son extension. Lève Illisible avec un motif en français."""
    fmt = format_de(chemin)
    if not fmt:
        raise Illisible(f"format « {Path(chemin).suffix or 'sans extension'} » non pris en charge "
                        "(pris en charge : PDF, Word .docx, Excel .xlsx, CSV, texte, Markdown)")
    if not Path(chemin).is_file():
        raise Illisible("fichier introuvable")
    if Path(chemin).stat().st_size > TAILLE_MAX_OCTETS:
        raise Illisible("fichier de plus de 50 Mo")
    doc = LECTEURS[fmt](chemin)
    doc["format"] = fmt
    doc["caracteres"] = sum(len(p["texte"]) for p in doc["parties"])
    return doc
