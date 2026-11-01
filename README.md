# Orchestra Agents

Agents de base et agents de test pour [Orchestra](https://github.com/PBdan-dev/Orchestra), construits avec le kit de certification de l'[Agent Market](https://github.com/PBdan-dev/Agent_Market/tree/main/agent-certification). Ils servent de banc d'essai pendant le développement d'Orchestra (lots T1, T2, T4) ; ce dépôt est temporaire.

| Agent | Ce qu'il fait | Ce qu'il teste dans Orchestra |
|---|---|---|
| `agent-date` | Date et heure du jour (long, court, ISO), sans modèle | Lancement, contrat, événements, compte rendu, catalogue |
| `agent-fichiers` | Renomme, déplace (sans écraser), supprime définitivement après validation | Actions réversibles, `action_sensitive_` et validation (4 portées), plusieurs étapes, arrêt, pause, état `partiel` |
| `agent-brouillons` | Brouillon de mail en `.md`, en réponse éventuelle à un mail reçu ; n'envoie rien | Modèle par la porte (minimum `qwen3.5:9b`, recommandé `qwen3.6:27b`), contenu piégé, mémoire propre (signature, ton), mémoire empoisonnée |

## Agents de base

| Agent | Ce qu'il fait | Dépendances |
|---|---|---|
| `agent-documents` | Extrait le texte, résume, extrait des données de documents PDF, Word, Excel, CSV, texte ; renomme, déplace, supprime après validation (reprend `agent-fichiers`) | `pypdf` (BSD-3), voir `requirements.txt` |

Un agent qui a un `requirements.txt` s'installe dans son propre environnement, dans son dossier d'installation (`agents/installes/<id>/`) :
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```
Orchestra lance `.venv\Scripts\python.exe` quand ce dossier existe. Pour rejouer les tests, lancer `rejouer_tests.py` avec ce même Python.
Les tests d'`agent-documents` sont fabriqués par `outils/tests_agent_documents.py` (documents PDF, Word et Excel en `base64:`, voir `outils/documents_de_test.py`).

Non couverts par les agents de test : secrets (`secret_`), réseau, agents hébergés.

## Structure

```
commun/contrat.py     code commun du contrat (stdio-json, arrêt, pause, validation), copié dans chaque agent
agent-*/              un agent = manifeste.json, agent.py, contrat.py, modeles/, tests/, CHANGELOG.md
outils/empaqueter.py  fabrique dist/<id>-<version>.zip et l'entrée de catalogue
```

## Tester

Depuis un clone de `Agent_Market` (scripts du kit) :
```
python agent-certification/scripts/verifier_agent.py ../Orchestra_Agents/agent-fichiers
python agent-certification/scripts/rejouer_tests.py ../Orchestra_Agents/agent-fichiers
python agent-certification/scripts/rejouer_tests.py ../Orchestra_Agents/agent-brouillons --ollama http://127.0.0.1:11434 --modele qwen3.5:9b
```

## Publier

1. `python outils/empaqueter.py` → `dist/<id>-<version>.zip` et `dist/<id>-<version>.catalogue.json`.
2. Release `<id>-<version>` sur `Agent_Market`, avec le `.zip` **tel quel** (l'empreinte change si on le refabrique).
3. Entrée du catalogue dans `agents.json` : seulement quand Orchestra lit le manifeste 2.0 (lots T1 et T4). Avant, Orchestra V1 rejette tout le catalogue.

Python 3.10 ou plus, bibliothèque standard uniquement. Licence MIT (voir chaque manifeste).
