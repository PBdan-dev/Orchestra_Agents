# Changelog — agent-brouillons

## 1.0.2 — 2026-10-29
- Contrôle par le code après la rédaction : pièce jointe annoncée sans `pieces_jointes`, nombres, jours et mois absents de la demande. Signalés en tête du brouillon (« À vérifier avant envoi ») et dans `verification.non_controle`.
- Points à aborder écrits à la première personne (modèle de demande et consigne) : corrige le contresens « confirmer la présence » vu sur Zeus.
- Nouveau champ facultatif `pieces_jointes`.

## 1.0.1 — 2026-10-29
- Réflexion du modèle coupée (`think: false`) : le test 02 dépassait 120 s avec qwen3.5:9b sur Zeus.
- Délai d'attente du modèle aligné sur `limites.duree_max_s` de la mission (600 s au plus).
- Consigne : ton amical = tutoiement ; aucun fait inventé, `[à compléter]` si une information manque.

## 1.0.0 — 2026-10-29
- Première version : brouillon de mail en .md, réponse à un mail reçu, mémoire de la signature et du ton.
