# Changelog — agent-tableur

## 1.0.0 — 2026-11-01
- Première version : analyse d'un tableau CSV ou Excel par un plan JSON (filtrer, calculer, grouper, croiser, trier, limiter, sélectionner) proposé par le modèle et exécuté par le programme ; expressions vérifiées par ast (aucun eval).
- Livrables : rapport Markdown (réponse, résultat, calculs faits), Excel, CSV, graphique SVG (barres, lignes, camembert).
- Contrôle par le code : chaque nombre du commentaire est comparé au résultat.
- Description d'un tableau sans modèle. Bibliothèque standard uniquement.
- Modèle minimum : qwen3.6:27b. Avec qwen3.5:9b, l'agent reste sûr (aucun incident sur les pièges) mais oublie parfois un champ du plan (refus motivé).
