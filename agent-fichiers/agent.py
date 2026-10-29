"""Agent « Fichiers » : renomme, déplace et supprime définitivement des fichiers ou dossiers du projet.
Renommer et déplacer sont réversibles (rien n'est écrasé). Supprimer définitivement est irréversible :
validation demandée à Orchestra avant chaque suppression."""
import shutil
from pathlib import Path

from contrat import Arret, champs_manquants, demander_validation, entre_deux_etapes, evenement, lancer, maintenant, reponse

TYPES = ("renommer", "deplacer", "supprimer_definitivement")


def dans_projet(projet, chemin):
    """Résout un chemin relatif et refuse tout ce qui sort du dossier du projet."""
    racine = Path(projet).resolve()
    cible = (racine / chemin).resolve()
    if cible != racine and racine not in cible.parents:
        raise ValueError(f"« {chemin} » est hors du dossier du projet")
    if cible == racine:
        raise ValueError("le dossier du projet lui-même ne peut pas être visé")
    return cible


def lister(racine, cible):
    """Fichiers concernés (chemins relatifs au projet), pour les annoncer dans le compte rendu."""
    if cible.is_dir():
        return [str(f.relative_to(racine)).replace("\\", "/") for f in sorted(cible.rglob("*")) if f.is_file()]
    return [str(cible.relative_to(racine)).replace("\\", "/")]


def action_deplacer(projet, source, destination, raison):
    """Renomme ou déplace un fichier ou un dossier. Réversible : refuse d'écraser une destination existante."""
    racine = Path(projet).resolve()
    src, dst = dans_projet(projet, source), dans_projet(projet, destination)
    if not src.exists():
        raise FileNotFoundError(f"« {source} » n'existe pas")
    if dst.exists():
        raise FileExistsError(f"« {destination} » existe déjà : rien n'est écrasé")
    avant = lister(racine, src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    apres = lister(racine, dst)
    return avant + apres


def action_sensitive_supprimer(projet, chemin, raison):
    """Supprime définitivement un fichier ou un dossier (pas de corbeille). Irréversible."""
    racine = Path(projet).resolve()
    cible = dans_projet(projet, chemin)
    if not cible.exists():
        raise FileNotFoundError(f"« {chemin} » n'existe pas")
    touches = lister(racine, cible)
    if cible.is_dir():
        shutil.rmtree(cible)
    else:
        cible.unlink()
    return touches


def executer(mission):
    manque = champs_manquants(mission, ["id", "agent_id", "projet", "donnees.operations"])
    if manque:
        return reponse(mission, "echec", motif=f"mission mal formée : champ « {manque} » absent",
                       non_controle=["mission refusée avant exécution"])
    ops = mission["donnees"]["operations"]
    if not isinstance(ops, list) or not ops:
        return reponse(mission, "echec", motif="mission mal formée : donnees.operations doit être une liste non vide",
                       non_controle=["mission refusée avant exécution"])
    for i, op in enumerate(ops, 1):
        if op.get("type") not in TYPES or not op.get("source") \
                or (op["type"] != "supprimer_definitivement" and not op.get("destination")):
            return reponse(mission, "echec", motif=f"mission mal formée : opération {i} incomplète ou de type inconnu",
                           non_controle=["mission refusée avant exécution"])

    evenement(mission, "demarrage", f"{len(ops)} opération(s) à faire")
    fichiers, actions, faites, manquant = [], [], [], []
    for i, op in enumerate(ops, 1):
        etape = f"opération {i}/{len(ops)} : {op['type']} {op['source']}"
        try:
            entre_deux_etapes(mission, etape)
        except Arret:
            return reponse(mission, "arrete_proprement", fichiers=fichiers, actions=actions,
                           controle=[f"{len(faites)} opération(s) faite(s) avant l'arrêt"],
                           non_controle=["opérations restantes non faites"],
                           reprise={"prochaine_operation": i})
        raison = op.get("raison") or f"demandé par la mission ({op['type']})"
        evenement(mission, "etape", etape)
        try:
            if op["type"] == "supprimer_definitivement":
                try:
                    accepte = demander_validation(mission, "action_sensitive_supprimer", raison)
                except Arret:
                    return reponse(mission, "arrete_proprement", fichiers=fichiers, actions=actions,
                                   controle=[f"{len(faites)} opération(s) faite(s) avant l'arrêt"],
                                   non_controle=["opérations restantes non faites"],
                                   reprise={"prochaine_operation": i})
                if not accepte:
                    manquant.append(f"{etape} : refusée par l'utilisateur")
                    continue
                touches = action_sensitive_supprimer(mission["projet"], op["source"], raison)
                nom = "action_sensitive_supprimer"
            else:
                touches = action_deplacer(mission["projet"], op["source"], op["destination"], raison)
                nom = "action_deplacer"
        except (OSError, ValueError) as err:
            manquant.append(f"{etape} : {err}")
            continue
        fichiers += [f for f in touches if f not in fichiers]
        actions.append({"t": maintenant(), "action": nom, "detail": f"{op['source']} → {op.get('destination', '(supprimé)')}",
                        "raison": raison, "essai": 1})
        faites.append(etape)

    controle = ["chaque chemin vérifié dans le dossier du projet", "aucune destination existante écrasée"]
    if not faites:
        return reponse(mission, "echec", motif="aucune opération n'a pu être faite", manquant=manquant,
                       controle=controle, non_controle=[])
    etat = "partiel" if manquant else "termine"
    evenement(mission, "termine", f"{len(faites)} opération(s) faite(s) sur {len(ops)}")
    return reponse(mission, etat, texte="\n".join(faites), fichiers=fichiers, actions=actions,
                   controle=controle, non_controle=[], manquant=manquant or None,
                   motif=f"{len(manquant)} opération(s) non faite(s)" if manquant else None)


if __name__ == "__main__":
    lancer(executer)
