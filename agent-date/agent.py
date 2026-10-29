"""Agent « Date du jour » : renvoie la date et l'heure, sans modèle ni fichier.
Sert de premier test du contrat Orchestra (lot T1) : lancement, événements, compte rendu."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from contrat import champs_manquants, entre_deux_etapes, evenement, lancer, reponse

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
FORMATS = ("iso", "long", "court")


def formater(d, fmt):
    if fmt == "iso":
        return d.isoformat(timespec="seconds")
    if fmt == "court":
        return d.strftime("%d/%m/%Y")
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}, {d.hour:02d} h {d.minute:02d}"


def executer(mission):
    manque = champs_manquants(mission, ["id", "agent_id", "donnees", "format_retour"])
    if manque:
        return reponse(mission, "echec", motif=f"mission mal formée : champ « {manque} » absent",
                       non_controle=["mission refusée avant exécution"])
    fmt = mission["donnees"].get("format", "long")
    fuseau = mission["donnees"].get("fuseau", "Europe/Paris")
    if fmt not in FORMATS:
        return reponse(mission, "echec", motif=f"format « {fmt} » inconnu (attendu : {', '.join(FORMATS)})",
                       non_controle=["mission refusée avant exécution"])
    try:
        zone = ZoneInfo(fuseau)
    except (ZoneInfoNotFoundError, ValueError):
        return reponse(mission, "echec", motif=f"fuseau horaire « {fuseau} » inconnu",
                       non_controle=["mission refusée avant exécution"])

    evenement(mission, "demarrage", "Lecture de l'horloge du système")
    entre_deux_etapes(mission, "lecture de l'horloge")
    texte = formater(datetime.now(zone), fmt)
    evenement(mission, "termine", texte)
    return reponse(mission, "termine", texte=texte,
                   controle=[f"date lue sur l'horloge du système, fuseau {fuseau}"],
                   non_controle=["exactitude de l'horloge du système"])


if __name__ == "__main__":
    lancer(executer)
