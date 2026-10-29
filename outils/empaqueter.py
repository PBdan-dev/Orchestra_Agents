"""Fabrique les paquets <id>-<version>.zip de chaque agent et l'entrée de catalogue correspondante.

Usage : python outils/empaqueter.py [agent ...]      (sans argument : tous les dossiers agent-*)
Sortie : dist/<id>-<version>.zip et dist/<id>-<version>.catalogue.json (à coller dans agents.json
après la publication de la Release). Copie d'abord commun/contrat.py dans chaque agent."""
import hashlib, json, shutil, sys, zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
EXCLUS = {"__pycache__", "memoire", "resultats"}


def empaqueter(dossier):
    shutil.copy2(RACINE / "commun" / "contrat.py", dossier / "contrat.py")
    m = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    nom = f"{m['id']}-{m['version']}"
    dist = RACINE / "dist"
    dist.mkdir(exist_ok=True)
    zp = dist / f"{nom}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dossier.rglob("*")):
            if f.is_file() and not (set(f.relative_to(dossier).parts) & EXCLUS):
                z.write(f, f"{m['id']}/{f.relative_to(dossier).as_posix()}")
    entree = {k: v for k, v in m.items()}
    entree["paquet"] = {
        "url": f"https://github.com/PBdan-dev/Agent_Market/releases/download/{nom}/{nom}.zip",
        "taille_octets": zp.stat().st_size,
        "sha256": hashlib.sha256(zp.read_bytes()).hexdigest(),
    }
    (dist / f"{nom}.catalogue.json").write_text(json.dumps(entree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{zp.name}  {entree['paquet']['taille_octets']} octets  sha256 {entree['paquet']['sha256']}")


if __name__ == "__main__":
    noms = sys.argv[1:] or sorted(p.name for p in RACINE.glob("agent-*") if p.is_dir())
    for n in noms:
        empaqueter(RACINE / n)
