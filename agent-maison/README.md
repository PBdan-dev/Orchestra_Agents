# Maison connectée (agent-maison) — agent Orchestra 1.0.0

Pilote la maison sur le réseau local : lampes **Philips Hue**, enceintes **Google Nest** (Cast), **TV LG** webOS.
Agent local Orchestra (contrat 1, manifeste 2.0), protocole stdio-json, modèle par la porte d'Orchestra.
Python 3.10 ou plus, **bibliothèque standard seule** : rien à installer. Licence MIT.

## Contenu

| Fichier | Rôle |
|---|---|
| `agent.py` | L'agent (lancé par Orchestra : `python agent.py`) |
| `configurer.bat` | Configuration, une seule fois |
| `manifeste.json` | Fiche de l'agent pour Orchestra et l'Agent Market |
| `modeles/` | Demande et livrable des 2 tâches |
| `tests/` | 13 missions de test du kit, dont 4 pièges |
| `contrat.py`, `consignes.py` | Code commun d'Orchestra_Agents (`consignes.py` sert au filtre des consignes cachées) |
| `CHANGELOG.md`, `LICENSE` | Version, licence MIT |

Aucun secret dans le paquet.

## Installation

1. Appairer une fois le pont Hue et la TV dans `home_control.exe` (onglets Lumières et Télévision).
2. Lancer `configurer.bat` et donner le dossier de `home_control.exe` (ex. `...\Home_Control\maison`).
   - clés dans le coffre-fort Windows : `orchestra/agent-maison/hue_cle` et `orchestra/agent-maison/tv_cle` ;
   - adresses dans `memoire/appareils.json` (sans secret). Si `enceintes.json` est absent, le script demande les IP des enceintes.
3. Orchestra lance `python agent.py` depuis le dossier de l'agent.

## Tâches

**`piloter-maison`** : `"donnees": { "demande": "Tamise le salon à 30 % et mets FIP sur le Nest Mini" }`

**`executer-commandes`** (sans modèle) :
```json
"donnees": { "appels": [
  { "outil": "action_lumiere_regler", "arguments": { "lampe": "toutes", "allumee": false, "raison": "Routine du coucher" } },
  { "outil": "action_tv_alimentation", "arguments": { "allumer": false, "raison": "Routine du coucher" } }
] }
```
`format_retour` : `texte`, ou `fichier` avec `destination` (rapport Markdown, jamais par-dessus un fichier existant).

## Outils proposés au modèle (19)

- Lecture : `read_lumieres`, `read_enceintes`, `read_tv_etat`, `read_tv_sources_et_applis`.
- Actions réversibles (`raison` obligatoire) : `action_lumiere_regler`, `action_enceinte_volume`, `action_enceinte_controle`, `action_enceinte_lire_url`, `action_enceinte_lire_radio`, `action_tv_alimentation`, `action_tv_volume`, `action_tv_source`, `action_tv_lancer_appli`, `action_tv_chaine`, `action_tv_touches`, `action_tv_lecture`, `action_tv_ouvrir_lien`.
- Irréversibles, validation demandée avant : `action_sensitive_enceinte_dire` (le .wav est écrit dans `annonces/` du projet), `action_sensitive_tv_message`.

## Garde-fous

- Arrêt propre avec `point_de_reprise`, pause / reprise, entre chaque étape.
- Réponses des appareils rendues au modèle entre balises `<donnee_externe>` ; une phrase qui ordonne d'oublier la mission (dans un nom de lampe, d'enceinte…) est retirée par le code avant le modèle et signalée dans le compte rendu.
- Lectures : 2 nouveaux essais au plus, annoncés. Un outil en erreur 3 fois n'est plus appelé.
- `limites.outils_interdits` et `validation` de la mission respectés. Modèle indisponible : `echec`.

## Limites

- Pas de Bbox (mot de passe administrateur, interdit par le critère H3).
- Pas de lecture de fichiers du PC sur la TV ou les enceintes, pas de découverte automatique des enceintes.
- Liens vidéo directs (mp4…) ouverts dans le navigateur de la TV, pas dans son lecteur.
- L'effet physique n'est pas vérifié.

## État de certification : `non_certifie` (audit à faire)

Contrôles du 2026-11-02, kit `agent-certification` (commit 8ea1ab3) :
- `scanner_code.py --manifeste` : 41 fonctions préfixées, 0 anomalie, 0 avertissement.
- `verifier_agent.py` : 30 OK, 0 KO.
- `rejouer_tests.py` (porte de test) : 9 tests, 0 contrôle en échec.
- Hors kit : Cast et webOS testés contre de faux appareils (volume, radio, état, appli, source, touches, message, lien YouTube).
- Restent : rejeu sur Ollama (`qwen3.5:9b`, `qwen3.6:27b`) et mesures, 3 pièges de l'auditeur rejoués 5 fois, revue de code, essai sur les vrais appareils.
