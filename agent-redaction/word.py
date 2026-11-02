"""Conversion d'un texte Markdown simple en document Word (.docx), avec la bibliothèque standard.

Pris en charge : titres (#, ##, ###), paragraphes, puces (- ou *), listes numérotées (1.), gras (**…**),
italique (*…*), citations (>). Les tableaux Markdown sont rendus en tableaux Word. Aucune fonction
de ce fichier n'écrit sur le disque : elles rendent des octets, écrits par l'action de l'agent."""
import io, re, zipfile
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="567"/></w:pPr><w:rPr><w:i/><w:color w:val="555555"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:color="999999"/><w:left w:val="single" w:sz="4" w:color="999999"/><w:bottom w:val="single" w:sz="4" w:color="999999"/>
<w:right w:val="single" w:sz="4" w:color="999999"/><w:insideH w:val="single" w:sz="4" w:color="999999"/><w:insideV w:val="single" w:sz="4" w:color="999999"/>
</w:tblBorders></w:tblPr></w:style>
</w:styles>"""

TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _runs(texte):
    """Texte avec **gras** et *italique* → éléments w:r."""
    morceaux = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", texte)
    sortie = []
    for m in morceaux:
        if not m:
            continue
        gras, ital = m.startswith("**") and m.endswith("**"), not m.startswith("**") and m.startswith("*") and m.endswith("*") and len(m) > 2
        contenu = m[2:-2] if gras else m[1:-1] if ital else m
        prop = "<w:rPr>" + ("<w:b/>" if gras else "") + ("<w:i/>" if ital else "") + "</w:rPr>" if gras or ital else ""
        sortie.append(f'<w:r>{prop}<w:t xml:space="preserve">{escape(contenu)}</w:t></w:r>')
    return "".join(sortie)


def _paragraphe(texte, style=None, retrait=0):
    ppr = ""
    if style or retrait:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + (f'<w:ind w:left="{retrait}" w:hanging="283"/>' if retrait else "") + "</w:pPr>"
    return f"<w:p>{ppr}{_runs(texte)}</w:p>"


def _tableau(lignes):
    cellules = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lignes if not re.match(r"^\s*\|?\s*:?-{2,}", l)]
    xml = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>']
    for i, ligne in enumerate(cellules):
        xml.append("<w:tr>" + "".join(f"<w:tc><w:p>{_runs(f'**{c}**' if i == 0 and c else c)}</w:p></w:tc>" for c in ligne) + "</w:tr>")
    xml.append("</w:tbl><w:p/>")
    return "".join(xml)


def markdown_vers_docx(markdown):
    """Rend les octets d'un .docx à partir d'un texte Markdown simple."""
    corps, tableau = [], []
    for ligne in markdown.split("\n"):
        if ligne.strip().startswith("|"):
            tableau.append(ligne)
            continue
        if tableau:
            corps.append(_tableau(tableau))
            tableau = []
        l = ligne.rstrip()
        if not l.strip():
            continue
        if m := re.match(r"^(#{1,3})\s+(.*)", l):
            niveau = len(m.group(1))
            corps.append(_paragraphe(m.group(2), "Title" if niveau == 1 else f"Heading{niveau - 1}"))
        elif m := re.match(r"^\s*[-*•]\s+(.*)", l):
            corps.append(_paragraphe("• " + m.group(1), retrait=567))
        elif m := re.match(r"^\s*(\d+)[.)]\s+(.*)", l):
            corps.append(_paragraphe(f"{m.group(1)}. " + m.group(2), retrait=567))
        elif l.startswith(">"):
            corps.append(_paragraphe(l.lstrip("> ").strip(), "Quote"))
        else:
            corps.append(_paragraphe(l.strip()))
    if tableau:
        corps.append(_tableau(tableau))
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(corps)}'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" '
                'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/document.xml", document)
    return tampon.getvalue()
