# Changelog — agent-documents

## 1.0.0 — 2026-11-01
- Première version : extraire le texte, résumer, extraire des données de documents PDF, Word (.docx), Excel (.xlsx), CSV, texte et Markdown.
- Reprend les opérations d'agent-fichiers 1.0.1 (renommer, déplacer, supprimer après validation, reprise).
- Contrôles par le code : pages citées et nombres du résumé comparés au document ; chaque valeur extraite recherchée dans le document.
- Dépendance : pypdf (BSD-3-Clause) pour les PDF ; Word et Excel lus avec la bibliothèque standard.
