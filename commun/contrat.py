"""Contrat Orchestra 1, protocole stdio-json : code commun copié tel quel dans chaque agent.

Entrée standard : une ligne JSON par message ; la première est la mission, les suivantes
des messages d'Orchestra (arret, pause, reprendre, validation).
Sortie standard : une ligne JSON par message, {"evenement": {...}} ou {"compte_rendu": {...}}.
Aucune fonction de ce fichier n'a d'effet sensible : pas de préfixe."""
import json, queue, sys, threading
from datetime import datetime, timezone

MESSAGES = queue.Queue()


class Arret(Exception):
    """Levée quand Orchestra demande l'arrêt : l'étape en cours est terminée."""


def maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def envoyer(objet):
    sys.stdout.write(json.dumps(objet, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def evenement(mission, type_, message, **extra):
    envoyer({"evenement": {"mission_id": mission.get("id", "inconnue"), "agent_id": mission.get("agent_id", ""),
                           "type": type_, "message": message, "t": maintenant(), **extra}})


def _lire_entree():
    for ligne in sys.stdin:
        try:
            MESSAGES.put(json.loads(ligne))
        except ValueError:
            pass


def entre_deux_etapes(mission, etape):
    """À appeler avant chaque étape : applique pause et arrêt propre."""
    while not MESSAGES.empty():
        m = MESSAGES.get()
        if m.get("type") == "arret":
            raise Arret(etape)
        if m.get("type") == "pause":
            evenement(mission, "en_pause", f"En pause avant l'étape « {etape} »")
            while True:
                m = MESSAGES.get()
                if m.get("type") == "arret":
                    raise Arret(etape)
                if m.get("type") == "reprendre":
                    break


def demander_validation(mission, action, raison):
    """Avant toute fonction action_sensitive_ : validation_requise, puis attente de la réponse."""
    evenement(mission, "validation_requise", f"Validation demandée : {action}", action=action, raison=raison)
    while True:
        m = MESSAGES.get()
        if m.get("type") == "arret":
            raise Arret(action)
        if m.get("type") == "pause":          # déjà à l'arrêt : on le signale et on continue d'attendre
            evenement(mission, "en_pause", f"En pause pendant l'attente de validation ({action})")
        if m.get("type") == "validation":
            return m.get("decision") == "accepte"


def reponse(mission, etat, texte="", fichiers=None, actions=None, controle=None, non_controle=None,
            motif=None, manquant=None, memoire=None, reprise=None):
    r = {"mission_id": mission.get("id") or "inconnue", "etat": etat,
         "resultat": {"texte": texte, "fichiers": fichiers or []},
         "actions_declarees": actions or [],
         "verification": {"controle": controle or [], "non_controle": non_controle or []},
         "point_de_reprise": reprise}
    if motif:
        r["motif"] = motif
    if manquant:
        r["manquant"] = manquant
    if memoire:
        r["memoire_modifiee"] = memoire
    return r


def champs_manquants(mission, champs):
    """Renvoie le premier champ absent (notation pointée), ou None."""
    for champ in champs:
        v = mission
        for k in champ.split("."):
            if not isinstance(v, dict) or k not in v:
                return champ
            v = v[k]
    return None


def lancer(executer):
    """Boucle principale : lit la mission, démarre l'écoute des messages, envoie le compte rendu."""
    ligne = sys.stdin.readline()
    try:
        mission = json.loads(ligne)
    except ValueError:
        envoyer({"compte_rendu": reponse({}, "echec", motif="mission illisible : JSON invalide",
                                         non_controle=["mission refusée avant exécution"])})
        return
    threading.Thread(target=_lire_entree, daemon=True).start()
    try:
        envoyer({"compte_rendu": executer(mission)})
    except Arret as a:
        envoyer({"compte_rendu": reponse(mission, "arrete_proprement", non_controle=["mission interrompue"],
                                         reprise={"etape": str(a)})})
