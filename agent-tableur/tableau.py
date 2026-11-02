"""Tableaux de l'agent « Tableur » : lecture (CSV, Excel), types, opérations d'un plan d'analyse,
expressions sûres, graphiques SVG et écriture Excel. Bibliothèque standard uniquement.

Le modèle ne donne jamais de code : il donne un plan en JSON (filtrer, calculer, grouper, croiser,
trier, limiter, sélectionner) que ce module exécute. Les expressions de « calculer » sont analysées
par ast et seules l'arithmétique, les colonnes et quelques fonctions listées sont acceptées."""
import ast, csv, io, math, re, statistics, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

LIGNES_MAX = 100_000
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
FORMATS_DATE = set(range(14, 23)) | {45, 46, 47}


class ErreurPlan(Exception):
    """Plan d'analyse impossible à exécuter (colonne inconnue, opération invalide…), motif en français."""


class Illisible(Exception):
    pass


# --- Lecture ---------------------------------------------------------------------------------------
def _decoder(octets):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return octets.decode(enc)
        except UnicodeDecodeError:
            continue
    return octets.decode("latin-1")


def read_csv(chemin):
    """Lignes d'un CSV (séparateur deviné). Rend [en-tête, lignes…] en texte."""
    with open(chemin, "rb") as f:
        texte = _decoder(f.read())
    try:
        dialecte = csv.Sniffer().sniff(texte[:10000], delimiters=";,\t")
    except csv.Error:
        dialecte = csv.excel
    return [l for l in csv.reader(io.StringIO(texte), dialecte) if any(c.strip() for c in l)]


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_excel(chemin, feuille=None):
    """Valeurs d'une feuille d'un .xlsx (la première, ou celle nommée). Rend (nom, lignes, noms des feuilles)."""
    try:
        with zipfile.ZipFile(chemin) as z:
            classeur = ET.fromstring(z.read("xl/workbook.xml"))
            liens = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(PR + "Relationship")}
            try:
                partagees = ["".join(x.text or "" for x in si.iter(S + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si")]
            except KeyError:
                partagees = []
            dates = set()
            try:
                styles = ET.fromstring(z.read("xl/styles.xml"))
                perso = {int(f.get("numFmtId", 0)): bool(re.search(r"[dyj]", re.sub(r'"[^"]*"|\[[^\]]*\]', "", f.get("formatCode", "")).lower()))
                         for f in styles.iter(S + "numFmt")}
                xfs = styles.find(S + "cellXfs")
                for i, xf in enumerate(list(xfs) if xfs is not None else []):
                    fid = int(xf.get("numFmtId", 0))
                    if fid in FORMATS_DATE or perso.get(fid):
                        dates.add(i)
            except (KeyError, ET.ParseError):
                pass
            feuilles = [(f.get("name"), f.get(R + "id")) for f in classeur.iter(S + "sheet")]
            if not feuilles:
                raise Illisible("classeur sans feuille")
            nom, rid = next(((n, r) for n, r in feuilles if n == feuille), feuilles[0]) if feuille else feuilles[0]
            if feuille and nom != feuille:
                raise Illisible(f"feuille « {feuille} » absente (feuilles : {', '.join(n for n, _ in feuilles)})")
            cible = liens.get(rid, "")
            cible = cible.lstrip("/") if cible.startswith("/") else "xl/" + cible
            lignes = []
            for i, ligne in enumerate(ET.fromstring(z.read(cible)).iter(S + "row")):
                if i > LIGNES_MAX:
                    break
                cellules = {}
                for c in ligne.iter(S + "c"):
                    t, v = c.get("t"), c.find(S + "v")
                    if t == "s" and v is not None:
                        val = partagees[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(S + "t"))
                    elif v is None or v.text is None:
                        val = ""
                    elif t == "b":
                        val = "VRAI" if v.text == "1" else "FAUX"
                    elif t in ("str", "e"):
                        val = v.text
                    elif int(c.get("s", 0)) in dates:
                        jour = datetime(1899, 12, 30) + timedelta(days=float(v.text))
                        val = jour.strftime("%Y-%m-%d") if float(v.text).is_integer() else jour.strftime("%Y-%m-%d %H:%M")
                    else:
                        val = float(v.text)
                    cellules[_col(c.get("r", "A1"))] = val
                if cellules:
                    lignes.append([cellules.get(k, "") for k in range(max(cellules) + 1)])
            return nom, lignes, [n for n, _ in feuilles]
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, AttributeError, IndexError) as err:
        raise Illisible(f"fichier Excel abîmé ou illisible ({err})")


# --- Types -------------------------------------------------------------------------------------------
def nombre(v):
    """Nombre lu à la française ou à l'anglaise (« 1 234,50 € », « 12 % », « 1,234.5 ») ; None sinon."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(" ", " ").replace(" ", " ")
    if not s:
        return None
    s = re.sub(r"[€$£%]|EUR|euros?", "", s, flags=re.I).strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def date_iso(v):
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def typer(entete, lignes):
    """Tableau typé : colonnes (nom, type) et lignes de valeurs (float, « AAAA-MM-JJ » ou texte, None si vide)."""
    noms, vus = [], {}
    for i, n in enumerate(entete):
        n = str(n).strip() or f"colonne {i + 1}"
        vus[n] = vus.get(n, 0) + 1
        noms.append(n if vus[n] == 1 else f"{n} ({vus[n]})")
    lignes = [l + [""] * (len(noms) - len(l)) for l in lignes]
    types = []
    for j in range(len(noms)):
        valeurs = [l[j] for l in lignes if str(l[j]).strip() != ""]
        if valeurs and sum(nombre(v) is not None for v in valeurs) >= 0.9 * len(valeurs):
            types.append("nombre")
        elif valeurs and sum(date_iso(v) is not None for v in valeurs) >= 0.9 * len(valeurs):
            types.append("date")
        else:
            types.append("texte")
    propres = []
    for l in lignes:
        r = []
        for j, t in enumerate(types):
            v = l[j]
            if str(v).strip() == "":
                r.append(None)
            elif t == "nombre":
                r.append(nombre(v))
            elif t == "date":
                r.append(date_iso(v))
            else:
                r.append(str(v).strip() if not isinstance(v, float) else format_nombre(v))
        propres.append(r)
    return {"colonnes": noms, "types": types, "lignes": propres}


def format_nombre(x):
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.4f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def profil(t, exemples=3):
    """Description des colonnes pour le modèle et le rapport."""
    sortie = []
    for j, (n, ty) in enumerate(zip(t["colonnes"], t["types"])):
        valeurs = [l[j] for l in t["lignes"] if l[j] is not None]
        d = {"nom": n, "type": ty, "vides": len(t["lignes"]) - len(valeurs), "distinctes": len(set(valeurs))}
        if ty == "nombre" and valeurs:
            d.update({"min": format_nombre(min(valeurs)), "max": format_nombre(max(valeurs)), "somme": format_nombre(round(sum(valeurs), 6))})
        elif ty == "date" and valeurs:
            d.update({"min": min(valeurs), "max": max(valeurs)})
        d["exemples"] = [format_nombre(v) if isinstance(v, float) else v for v in list(dict.fromkeys(valeurs))[:exemples]]
        sortie.append(d)
    return sortie


# --- Expressions sûres -----------------------------------------------------------------------------------
FONCTIONS = {"arrondi": lambda x, n=0: round(x, int(n)), "abs": abs, "min": min, "max": max,
             "annee": lambda d: int(str(d)[:4]), "mois": lambda d: str(d)[:7], "jour": lambda d: str(d)[:10],
             "racine": math.sqrt}
OPERATEURS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
              ast.Div: lambda a, b: a / b if b else None, ast.Mod: lambda a, b: a % b if b else None}


def compiler(expression, colonnes):
    """Expression du plan → arbre vérifié. Les colonnes s'écrivent entre crochets : [Montant] * 1.2"""
    noms = {}
    def remplacer(m):
        nom = m.group(1).strip()
        if nom not in colonnes:
            raise ErreurPlan(f"colonne « {nom} » inconnue dans l'expression « {expression} »")
        cle = f"c{colonnes.index(nom)}"
        noms[cle] = colonnes.index(nom)
        return cle
    source = re.sub(r"\[([^\]]+)\]", remplacer, expression)
    try:
        arbre = ast.parse(source, mode="eval")
    except SyntaxError:
        raise ErreurPlan(f"expression illisible : « {expression} »")
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name) and n.func.id in ("moyenne", "somme", "mediane", "compte", "total", "sum", "mean", "avg"):
                raise ErreurPlan(f"« {n.func.id} » est un agrégat, pas une fonction de calculer : utilise l'étape grouper, "
                                 "par exemple {\"op\": \"grouper\", \"par\": [], \"agregats\": [{\"colonne\": \"Quantité\", \"fonction\": \"moyenne\"}]}")
            if not isinstance(n.func, ast.Name) or n.func.id not in FONCTIONS or n.keywords:
                raise ErreurPlan(f"fonction non permise dans « {expression} » (permises : {', '.join(FONCTIONS)})")
        elif isinstance(n, ast.Name):
            if n.id not in noms and n.id not in FONCTIONS:
                raise ErreurPlan(f"nom inconnu « {n.id} » dans « {expression} » : écrire les colonnes entre crochets")
        elif isinstance(n, ast.BinOp):
            if type(n.op) not in OPERATEURS:
                raise ErreurPlan(f"opérateur non permis dans « {expression} »")
        elif isinstance(n, ast.UnaryOp):
            if not isinstance(n.op, (ast.USub, ast.UAdd)):
                raise ErreurPlan(f"opérateur non permis dans « {expression} »")
        elif isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float, str)) or isinstance(n.value, bool):
                raise ErreurPlan(f"valeur non permise dans « {expression} »")
        elif not isinstance(n, (ast.Expression, ast.Load, ast.operator, ast.unaryop)):
            raise ErreurPlan(f"élément non permis dans « {expression} » ({type(n).__name__})")
    return arbre.body, noms


def evaluer(noeud, ligne, noms):
    if isinstance(noeud, ast.Constant):
        return noeud.value
    if isinstance(noeud, ast.Name):
        return ligne[noms[noeud.id]]
    if isinstance(noeud, ast.UnaryOp):
        v = evaluer(noeud.operand, ligne, noms)
        return None if v is None else (-v if isinstance(noeud.op, ast.USub) else v)
    if isinstance(noeud, ast.BinOp):
        a, b = evaluer(noeud.left, ligne, noms), evaluer(noeud.right, ligne, noms)
        if a is None or b is None:
            return None
        try:
            return OPERATEURS[type(noeud.op)](a, b)
        except TypeError:
            raise ErreurPlan("calcul entre un nombre et un texte")
    if isinstance(noeud, ast.Call):
        args = [evaluer(a, ligne, noms) for a in noeud.args]
        if any(a is None for a in args):
            return None
        try:
            return FONCTIONS[noeud.func.id](*args)
        except (TypeError, ValueError) as err:
            raise ErreurPlan(f"fonction {noeud.func.id} : {err}")
    raise ErreurPlan("expression non permise")


# --- Opérations du plan ------------------------------------------------------------------------------------
AGREGATS = {
    "somme": lambda v: sum(v), "moyenne": lambda v: statistics.fmean(v) if v else None,
    "mediane": lambda v: statistics.median(v) if v else None, "min": lambda v: min(v) if v else None,
    "max": lambda v: max(v) if v else None, "compte": len, "compte_distinct": lambda v: len(set(v)),
}


def _index(t, nom, quoi="colonne"):
    if nom not in t["colonnes"]:
        raise ErreurPlan(f"{quoi} « {nom} » inconnue (colonnes : {', '.join(t['colonnes'])})")
    return t["colonnes"].index(nom)


def _compare(v, cond, ref):
    if cond == "vide":
        return v is None
    if cond == "non_vide":
        return v is not None
    if v is None:
        return False
    if cond == "contient":
        return str(ref).lower() in str(v).lower()
    if isinstance(v, float):
        r = nombre(ref)
        if r is None:
            raise ErreurPlan(f"valeur « {ref} » non numérique pour une colonne de nombres")
    else:
        v, r = str(v).lower(), (date_iso(ref) or str(ref)).lower()
    return {"=": v == r, "!=": v != r, ">": v > r, ">=": v >= r, "<": v < r, "<=": v <= r}[cond]


def appliquer(t, etape):
    """Applique une étape du plan à un tableau typé ; rend le nouveau tableau."""
    op = etape.get("op")
    cols, types, lignes = t["colonnes"], t["types"], t["lignes"]
    if op == "filtrer":
        j = _index(t, etape.get("colonne", ""))
        cond = etape.get("condition", "=")
        if cond not in ("=", "!=", ">", ">=", "<", "<=", "contient", "vide", "non_vide"):
            raise ErreurPlan(f"condition « {cond} » inconnue")
        if cond not in ("vide", "non_vide") and str(etape.get("valeur") if etape.get("valeur") is not None else "").strip() == "":
            raise ErreurPlan("filtrer : « valeur » absente (la valeur à comparer, par exemple \"Est\")")
        return {**t, "lignes": [l for l in lignes if _compare(l[j], cond, etape.get("valeur", ""))]}
    if op == "calculer":
        nom = str(etape.get("nom") or "").strip()
        if not nom and str(etape.get("colonne") or "").strip() not in cols:   # « colonne » donné pour le nom de la nouvelle colonne
            nom = str(etape.get("colonne") or "").strip()
        if not nom:
            raise ErreurPlan("calculer : le champ « nom » (nom de la nouvelle colonne) est absent")
        if nom in cols:
            raise ErreurPlan(f"calculer : la colonne « {nom} » existe déjà, choisis un autre nom")
        arbre, noms = compiler(str(etape.get("expression", "")), cols)
        valeurs = [evaluer(arbre, l, noms) for l in lignes]
        ty = "nombre" if all(isinstance(v, (int, float)) or v is None for v in valeurs) else "texte"
        valeurs = [float(v) if ty == "nombre" and v is not None else v for v in valeurs]
        return {"colonnes": cols + [nom], "types": types + [ty], "lignes": [l + [v] for l, v in zip(lignes, valeurs)]}
    if op == "grouper":
        par = [_index(t, c) for c in etape.get("par") or []]
        agregats = etape.get("agregats") or []
        if not agregats:
            raise ErreurPlan("grouper : aucun agrégat")
        groupes = {}
        for l in lignes:
            groupes.setdefault(tuple(l[j] for j in par), []).append(l)
        nouvelles_cols, nouveaux_types, specs = [cols[j] for j in par], [types[j] for j in par], []
        for a in agregats:
            f = a.get("fonction")
            if f not in AGREGATS:
                raise ErreurPlan(f"fonction d'agrégat « {f} » inconnue ({', '.join(AGREGATS)})")
            if f == "compte" and a.get("colonne") not in cols:     # compter des lignes : la colonne ne sert à rien
                j = None
            else:
                j = _index(t, a["colonne"]) if a.get("colonne") else None
            if j is None and f != "compte":
                raise ErreurPlan(f"agrégat {f} sans « colonne » : indique la colonne à agréger (par exemple celle créée par calculer)")
            if j is not None and types[j] != "nombre" and f not in ("compte", "compte_distinct", "min", "max"):
                raise ErreurPlan(f"{f} demandé sur la colonne « {cols[j]} », qui n'est pas numérique")
            nom = a.get("nom") or (f"{f} de {cols[j]}" if j is not None else "nombre de lignes")
            specs.append((f, j))
            nouvelles_cols.append(nom)
            nouveaux_types.append("nombre" if f in ("somme", "moyenne", "mediane", "compte", "compte_distinct") or (j is not None and types[j] == "nombre") else types[j])
        sortie = []
        for cle, ls in groupes.items():
            r = list(cle)
            for f, j in specs:
                vals = [l[j] for l in ls if l[j] is not None] if j is not None else ls
                v = AGREGATS[f](vals)
                r.append(float(v) if isinstance(v, (int, float)) else v)
            sortie.append(r)
        return {"colonnes": nouvelles_cols, "types": nouveaux_types, "lignes": sortie}
    if op == "croiser":
        jl, jc = _index(t, etape.get("lignes", ""), "colonne des lignes"), _index(t, etape.get("en_colonnes", ""), "colonne des colonnes")
        f = etape.get("fonction") or "somme"
        if f not in AGREGATS:
            raise ErreurPlan(f"fonction « {f} » inconnue")
        if not etape.get("valeur"):        # valeur donnée ailleurs (garder, colonne) : une seule colonne numérique possible
            possibles = {c for c in (etape.get("garder") or []) + [etape.get("colonne")]
                         if c in cols and types[cols.index(c)] == "nombre" and c not in (etape.get("lignes"), etape.get("en_colonnes"))}
            if len(possibles) == 1:
                etape = {**etape, "valeur": possibles.pop()}
        jv = _index(t, etape["valeur"], "colonne des valeurs") if etape.get("valeur") else None
        if jv is None and f != "compte":
            raise ErreurPlan(f"croiser : « valeur » absente (la colonne à agréger avec {f}) ; pour compter des lignes, fonction compte")
        cles_c = sorted({l[jc] for l in lignes if l[jc] is not None}, key=str)
        if len(cles_c) > 50:
            raise ErreurPlan("tableau croisé de plus de 50 colonnes")
        cellules = {}
        for l in lignes:
            cellules.setdefault((l[jl], l[jc]), []).append(l[jv] if jv is not None else 1)
        lignes_cles = sorted({l[jl] for l in lignes}, key=lambda x: (x is None, str(x)))
        sortie = []
        for a in lignes_cles:
            r = [a]
            for b in cles_c:
                vals = [v for v in cellules.get((a, b), []) if v is not None]
                r.append(float(AGREGATS[f](vals)) if vals else None)
            sortie.append(r)
        return {"colonnes": [cols[jl]] + [format_nombre(c) if isinstance(c, float) else str(c) for c in cles_c],
                "types": [types[jl]] + ["nombre"] * len(cles_c), "lignes": sortie}
    if op == "trier":
        j = _index(t, etape.get("colonne", ""))
        inverse = etape.get("ordre") == "decroissant"
        return {**t, "lignes": sorted(lignes, key=lambda l: (l[j] is None, l[j] if l[j] is not None else 0) if types[j] == "nombre"
                                      else (l[j] is None, str(l[j] or "")), reverse=inverse)}
    if op == "limiter":
        n = int(nombre(etape.get("n", 10)) or 10)
        return {**t, "lignes": lignes[:max(1, n)]}
    if op == "selectionner":
        js = [_index(t, c) for c in etape.get("garder") or []]
        if not js:
            raise ErreurPlan("selectionner : aucune colonne")
        return {"colonnes": [cols[j] for j in js], "types": [types[j] for j in js], "lignes": [[l[j] for j in js] for l in lignes]}
    raise ErreurPlan(f"opération « {op} » inconnue")


def decrire_etape(e):
    """L'étape en français, écrite par le code (et non par le modèle) pour le rapport."""
    op = e.get("op")
    if op == "filtrer":
        return f"garder les lignes où « {e.get('colonne')} » {e.get('condition', '=')} {e.get('valeur', '')}".rstrip()
    if op == "calculer":
        return f"ajouter la colonne « {e.get('nom')} » = {e.get('expression')}"
    if op == "grouper":
        ag = ", ".join(f"{a.get('fonction')} de « {a.get('colonne')} »" if a.get("colonne") else a.get("fonction", "") for a in e.get("agregats") or [])
        return f"regrouper par {', '.join(f'« {c} »' for c in e.get('par') or []) or 'tout le tableau'} : {ag}"
    if op == "croiser":
        return f"tableau croisé : lignes « {e.get('lignes')} », colonnes « {e.get('en_colonnes')} », {e.get('fonction', 'somme')} de « {e.get('valeur') or 'lignes'} »"
    if op == "trier":
        return f"trier par « {e.get('colonne')} » ({e.get('ordre', 'croissant')})"
    if op == "limiter":
        return f"garder les {e.get('n')} premières lignes"
    if op == "selectionner":
        return "garder les colonnes " + ", ".join(f"« {c} »" for c in e.get("garder") or [])
    return str(op)


# --- Sorties -----------------------------------------------------------------------------------------------
def tableau_md(t, n=50):
    def cel(v):
        return (format_nombre(v) if isinstance(v, float) else "" if v is None else str(v)).replace("|", "\\|")
    lignes = ["| " + " | ".join(t["colonnes"]) + " |", "|" + "---|" * len(t["colonnes"])]
    lignes += ["| " + " | ".join(cel(v) for v in l) + " |" for l in t["lignes"][:n]]
    if len(t["lignes"]) > n:
        lignes.append(f"\n({len(t['lignes']) - n} ligne(s) de plus dans le fichier Excel)")
    return "\n".join(lignes)


def csv_texte(t):
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    w.writerow(t["colonnes"])
    for l in t["lignes"]:
        w.writerow([format_nombre(v).replace(".", ",") if isinstance(v, float) else "" if v is None else v for v in l])
    return tampon.getvalue()


def xlsx_octets(t, nom_feuille="Résultat"):
    """Classeur Excel : une feuille, en-tête en gras, nombres en nombres."""
    def ref(c, r):
        s, c = "", c + 1
        while c:
            c, x = divmod(c - 1, 26)
            s = chr(65 + x) + s
        return f"{s}{r}"
    partagees, index = [], {}
    def chaine(v):
        if v not in index:
            index[v] = len(partagees)
            partagees.append(v)
        return index[v]
    rows = ['<row r="1">' + "".join(f'<c r="{ref(j, 1)}" t="s" s="1"><v>{chaine(str(c))}</v></c>' for j, c in enumerate(t["colonnes"])) + "</row>"]
    for i, l in enumerate(t["lignes"], 2):
        cels = []
        for j, v in enumerate(l):
            if v is None:
                continue
            if isinstance(v, float):
                cels.append(f'<c r="{ref(j, i)}"><v>{format_nombre(v)}</v></c>')
            else:
                cels.append(f'<c r="{ref(j, i)}" t="s"><v>{chaine(str(v))}</v></c>')
        rows.append(f'<row r="{i}">{"".join(cels)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    fichiers = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(nom_feuille[:31])}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData>{"".join(rows)}</sheetData></worksheet>',
        "xl/sharedStrings.xml": f'<?xml version="1.0" encoding="UTF-8"?><sst {ns} count="{len(partagees)}" uniqueCount="{len(partagees)}">'
        + "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in partagees) + "</sst>",
        "xl/styles.xml": f'<?xml version="1.0" encoding="UTF-8"?><styleSheet {ns}><fonts count="2"><font/><font><b/></font></fonts>'
        '<fills count="1"><fill/></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="0" fontId="1" applyFont="1"/></cellXfs></styleSheet>',
    }
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, contenu in fichiers.items():
            z.writestr(nom, contenu)
    return tampon.getvalue()


COULEURS = ["#3b82c4", "#e08a3c", "#4aa36c", "#c94f4f", "#8a6cc4", "#3fa7a7", "#c4a23b", "#7d7d7d"]


def svg_graphique(t, g):
    """Graphique SVG (barres, lignes ou camembert) depuis un tableau résultat ; lève ErreurPlan si impossible."""
    type_ = g.get("type")
    if type_ not in ("barres", "lignes", "camembert"):
        raise ErreurPlan(f"type de graphique « {type_} » inconnu (barres, lignes, camembert)")
    jx = _index(t, g.get("x", ""), "colonne x du graphique")
    ys = g.get("y") if isinstance(g.get("y"), list) else [g.get("y")]
    jys = [_index(t, y, "colonne y du graphique") for y in ys if y]
    if not jys or any(t["types"][j] != "nombre" for j in jys):
        raise ErreurPlan("le graphique demande au moins une colonne y numérique")
    lignes = t["lignes"][:30]
    etiquettes = [format_nombre(l[jx]) if isinstance(l[jx], float) else str(l[jx] if l[jx] is not None else "(vide)") for l in lignes]
    titre = escape(str(g.get("titre") or ""))[:120]
    L, H, gauche, bas, haut = 760, 420, 70, 90, 50
    parties = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {L} {H}" font-family="Segoe UI, Arial, sans-serif" font-size="12">',
               f'<rect width="{L}" height="{H}" fill="#ffffff"/>', f'<text x="{L / 2}" y="28" text-anchor="middle" font-size="16" font-weight="600">{titre}</text>']
    if type_ == "camembert":
        valeurs = [max(0.0, l[jys[0]] or 0.0) for l in lignes]
        total = sum(valeurs) or 1
        cx, cy, r, angle = 260, 235, 150, -math.pi / 2
        for i, (v, e) in enumerate(zip(valeurs, etiquettes)):
            a2 = angle + 2 * math.pi * v / total
            x1, y1, x2, y2 = cx + r * math.cos(angle), cy + r * math.sin(angle), cx + r * math.cos(a2), cy + r * math.sin(a2)
            grand = 1 if a2 - angle > math.pi else 0
            chemin = f"M{cx},{cy} L{x1:.1f},{y1:.1f} A{r},{r} 0 {grand} 1 {x2:.1f},{y2:.1f} Z" if v < total else f"M{cx - r},{cy} a{r},{r} 0 1 0 {2 * r},0 a{r},{r} 0 1 0 {-2 * r},0"
            parties.append(f'<path d="{chemin}" fill="{COULEURS[i % 8]}" stroke="#fff"/>')
            parties.append(f'<rect x="460" y="{70 + i * 20}" width="12" height="12" fill="{COULEURS[i % 8]}"/>'
                           f'<text x="478" y="{80 + i * 20}">{escape(e[:30])} : {format_nombre(round(v, 2))} ({100 * v / total:.1f} %)</text>')
            angle = a2
        parties.append("</svg>")
        return "\n".join(parties)
    tout = [l[j] for l in lignes for j in jys if l[j] is not None]
    vmin, vmax = min(0.0, min(tout, default=0.0)), max(tout, default=1.0) or 1.0
    zone_h, zone_l = H - haut - bas, L - gauche - 30
    def y(v):
        return haut + zone_h * (1 - (v - vmin) / (vmax - vmin or 1))
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4
        parties.append(f'<line x1="{gauche}" x2="{L - 30}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e5e5e5"/>'
                       f'<text x="{gauche - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#555">{format_nombre(round(v, 2)).replace(".", ",")}</text>')
    n = max(1, len(lignes))
    pas = zone_l / n
    for i, e in enumerate(etiquettes):
        x = gauche + pas * (i + 0.5)
        parties.append(f'<text transform="translate({x:.1f},{H - bas + 14}) rotate(35)" fill="#333">{escape(e[:18])}</text>')
    for k, j in enumerate(jys):
        couleur = COULEURS[k % 8]
        if type_ == "barres":
            largeur = pas * 0.8 / len(jys)
            for i, l in enumerate(lignes):
                if l[j] is None:
                    continue
                x = gauche + pas * i + pas * 0.1 + largeur * k
                y0, y1 = y(max(0.0, vmin)), y(l[j])
                parties.append(f'<rect x="{x:.1f}" y="{min(y0, y1):.1f}" width="{largeur:.1f}" height="{abs(y0 - y1):.1f}" fill="{couleur}"/>')
        else:
            points = " ".join(f"{gauche + pas * (i + 0.5):.1f},{y(l[j]):.1f}" for i, l in enumerate(lignes) if l[j] is not None)
            parties.append(f'<polyline points="{points}" fill="none" stroke="{couleur}" stroke-width="2.5"/>')
        parties.append(f'<rect x="{gauche + k * 160}" y="38" width="12" height="12" fill="{couleur}"/>'
                       f'<text x="{gauche + 16 + k * 160}" y="48">{escape(t["colonnes"][j][:22])}</text>')
    parties.append("</svg>")
    return "\n".join(parties)
