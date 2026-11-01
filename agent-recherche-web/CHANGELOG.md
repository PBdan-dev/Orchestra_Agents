# Changelog — agent-recherche-web

## 1.0.0 — 2026-11-01
- Première version : recherche par l'API Brave Search (clé dans le coffre-fort) ou, sans clé, par l'API de Wikipédia, choix des pages par le modèle, lecture de 4 à 12 pages (HTML, texte, PDF), rapport sourcé [S1] dans rapports/.
- Sécurité : adresses du réseau local refusées (y compris après redirection), robots.txt respecté, aucun lien suivi depuis une page, contenu du web balisé comme donnée.
- Contrôles par le code : sources citées, paragraphes sans source, nombres absents des pages.
