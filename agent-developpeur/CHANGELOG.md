# Changelog — agent-developpeur

## 1.0.0 — 2026-11-01
- Première version : écrire un programme Python et ses tests dans dev/<nom>/, lancer les tests, corriger jusqu'à 2 fois ; corriger un script existant sur une copie.
- Contrôle ast avant tout lancement (liste blanche de modules, appels dangereux, chemins hors du dossier) ; hors liste blanche : validation de l'utilisateur.
- Tests lancés en Python isolé (-I), dans le dossier de la mission, sans les variables d'Orchestra, 60 s au plus. Bibliothèque standard uniquement.
- Modèle minimum : qwen3.6:27b. Avec qwen3.5:9b, l'agent reste sûr (aucun incident sur les pièges) mais rend souvent un état partiel (tests encore en échec après 2 corrections).
