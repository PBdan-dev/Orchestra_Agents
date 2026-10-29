# Orchestra Agents

Agents de test pour [Orchestra](https://github.com/PBdan-dev/Orchestra), construits avec le kit de certification de l'[Agent Market](https://github.com/PBdan-dev/Agent_Market/tree/main/agent-certification). Ils servent de banc d'essai pendant le développement d'Orchestra (lots T1, T2, T4) ; ce dépôt est temporaire.

| Agent | Ce qu'il fait | Ce qu'il teste dans Orchestra |
|---|---|---|
| `agent-date` | Date et heure du jour (long, court, ISO), sans modèle | Lancement, contrat, événements, compte rendu, catalogue |
| `agent-fichiers` | Renomme, déplace (sans écraser), supprime définitivement après validation | Actions réversibles, `action_sensitive_` et validation (4 portées), plusieurs étapes, arrêt, pause, état `partiel` |
| `agent-brouillons` | Brouillon de mail en `.md`, en réponse éventuelle à un mail reçu ; n'envoie rien | Modèle par la porte (`qwen3.5:9b`, changement de modèle), contenu piégé, mémoire propre (signature, ton), mémoire empoisonnée |

Non couverts : secrets (`secret_`), réseau, agents hébergés.

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
