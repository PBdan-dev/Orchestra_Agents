"""Fabrique de petits documents PDF, Word et Excel pour les tests des agents (bibliothèque standard).

Utilisé par outils/tests_agent_*.py. Les documents sont encodés en « base64:… » dans fichiers_projet (format du kit de certification)."""
import base64, io, zipfile
from xml.sax.saxutils import escape


def pdf(pages):
    """PDF minimal : une liste de pages, chacune une liste de lignes (Helvetica, WinAnsi). Page vide = sans texte."""
    objets = ["<< /Type /Catalog /Pages 2 0 R >>", None,
              "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for lignes in pages:
        flux = ""
        if lignes:
            corps = []
            for l in lignes:
                octets = l.encode("cp1252")
                s = "".join(chr(b) if 32 <= b < 127 and chr(b) not in "()\\" else f"\\{b:03o}" for b in octets)
                corps.append(f"({s}) Tj T*")
            flux = "BT /F1 11 Tf 14 TL 60 780 Td " + " ".join(corps) + " ET"
        else:
            flux = "0.8 g 60 400 200 200 re f"           # un rectangle gris, aucun texte (page « scannée »)
        objets.append(f"<< /Length {len(flux)} >>\nstream\n{flux}\nendstream")
        contenu = len(objets)
        objets.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {contenu} 0 R >>")
        kids.append(len(objets))
    objets[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    sortie, positions = io.BytesIO(), []
    sortie.write(b"%PDF-1.4\n")
    for i, o in enumerate(objets, 1):
        positions.append(sortie.tell())
        sortie.write(f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1"))
    xref = sortie.tell()
    sortie.write(f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode())
    for p in positions:
        sortie.write(f"{p:010d} 00000 n \n".encode())
    sortie.write(f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return sortie.getvalue()


def docx(blocs):
    """Document Word : blocs ("titre", texte, niveau) | ("p", texte) | ("table", [[cellules]])."""
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    corps = []
    for b in blocs:
        if b[0] == "titre":
            corps.append(f'<w:p><w:pPr><w:pStyle w:val="Heading{b[2]}"/></w:pPr><w:r><w:t>{escape(b[1])}</w:t></w:r></w:p>')
        elif b[0] == "p":
            corps.append(f'<w:p><w:r><w:t xml:space="preserve">{escape(b[1])}</w:t></w:r></w:p>')
        else:
            lignes = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{escape(c)}</w:t></w:r></w:p></w:tc>" for c in l) + "</w:tr>"
                             for l in b[1])
            corps.append(f"<w:tbl>{lignes}</w:tbl>")
    fichiers = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{"".join(corps)}</w:body></w:document>',
    }
    return _zip(fichiers)


def xlsx(feuilles):
    """Classeur Excel : {nom: [[cellules]]} ; str = texte partagé, int/float = nombre, ("date", n) = date (série Excel)."""
    partagees, index = [], {}
    def ref(c, l):
        s = ""
        c += 1
        while c:
            c, r = divmod(c - 1, 26)
            s = chr(65 + r) + s
        return f"{s}{l}"
    xml_feuilles = []
    for lignes in feuilles.values():
        rows = []
        for i, l in enumerate(lignes, 1):
            cels = []
            for j, v in enumerate(l):
                if isinstance(v, str):
                    if v not in index:
                        index[v] = len(partagees)
                        partagees.append(v)
                    cels.append(f'<c r="{ref(j, i)}" t="s"><v>{index[v]}</v></c>')
                elif isinstance(v, tuple):
                    cels.append(f'<c r="{ref(j, i)}" s="1"><v>{v[1]}</v></c>')
                else:
                    cels.append(f'<c r="{ref(j, i)}"><v>{v}</v></c>')
            rows.append(f'<row r="{i}">{"".join(cels)}</row>')
        xml_feuilles.append('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                            f'<sheetData>{"".join(rows)}</sheetData></worksheet>')
    S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    noms = list(feuilles)
    fichiers = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(noms) + 1))
        + '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook {S} {R}><sheets>'
        + "".join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(noms, 1)) + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(noms) + 1))
        + f'<Relationship Id="rId{len(noms) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        + f'<Relationship Id="rId{len(noms) + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<?xml version="1.0" encoding="UTF-8"?><sst {S} count="{len(partagees)}" uniqueCount="{len(partagees)}">'
        + "".join(f"<si><t>{escape(s)}</t></si>" for s in partagees) + "</sst>",
        "xl/styles.xml": f'<?xml version="1.0" encoding="UTF-8"?><styleSheet {S}><fonts count="1"><font/></fonts><fills count="1"><fill/></fills>'
        '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14" applyNumberFormat="1"/></cellXfs></styleSheet>',
    }
    for i, x in enumerate(xml_feuilles, 1):
        fichiers[f"xl/worksheets/sheet{i}.xml"] = x
    return _zip(fichiers)


def _zip(fichiers):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, contenu in fichiers.items():
            z.writestr(nom, contenu)
    return tampon.getvalue()


def b64(octets):
    return "base64:" + base64.b64encode(octets).decode()
