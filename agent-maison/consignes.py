"""Consignes cachées dans un contenu externe : repérées et retirées par le code avant que le modèle les lise.
Code commun copié tel quel dans les agents qui en ont besoin (aucun effet sensible : pas de préfixe)."""
import re

# Phrase qui ordonne à l'agent d'oublier sa mission ou ses règles.
ORDRE = re.compile(r"(ignore|oublie|ne tiens pas compte|disregard)\w*\s+(de\s+)?(ta|tes|la|les|vos|toutes?\s+les|ce que|all|previous|your)\s+(\w+\s+)?"
                   r"(mission|consigne|instruction|r[eè]gle)", re.IGNORECASE)
RETRAIT = "[passage retiré par le code : consigne adressée à un agent]"


def retirer_ordres(texte):
    """Remplace chaque phrase d'ordre, et la suite de sa ligne, par un repère. Rend (texte, passages retirés)."""
    lignes, retires = [], []
    for l in str(texte).split("\n"):
        m = ORDRE.search(l)
        if m:
            retires.append(l.strip()[:160])
            lignes.append((l[:m.start()].rstrip() + " " + RETRAIT).strip())
        else:
            lignes.append(l)
    return "\n".join(lignes), retires
