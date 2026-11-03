# Changelog — Maison connectée (agent-maison)

## 1.0.0 — 2026-11-03
- Première version publiée, sous l'identifiant `agent-maison` (convention d'Orchestra_Agents) : portage en Python (bibliothèque standard seule) de l'agent Rust home-control 1.0.0, pour passer le scan des préfixes du kit.
- Données des appareils filtrées valeur par valeur par `commun/consignes.py` avant le modèle ; passages retirés signalés dans `verification.controle`.
- 13 tests : 4 pièges (nom de lampe, mémoire, fausse fermeture de balise), cas nominal avec le modèle (allumer une lampe).
- Protocole stdio-json (contrat 1) : mission, événements, compte rendu ; arrêt propre, pause/reprise, validation avant action irréversible.
- Deux tâches : `piloter-maison` (langage naturel, modèle par la porte) et `executer-commandes` (liste d'appels, sans modèle).
- Hue (HTTP), Google Cast v2 (TLS, protobuf écrit à la main), LG webOS SSAP (WebSocket écrite à la main), Wake-on-LAN.
- Clés dans le coffre-fort Windows par ctypes (`orchestra/agent-maison/hue_cle`, `tv_cle`) ; adresses dans `memoire/appareils.json`.
- Différences avec la version Rust : pas de découverte mDNS (IP des enceintes données à configurer), liens vidéo directs ouverts dans le navigateur de la TV (pas de DLNA).
