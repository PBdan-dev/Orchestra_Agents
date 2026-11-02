"""Contrôle statique du code écrit par le modèle, avant toute exécution (module ast, rien n'est exécuté).

Règle : un script n'est lancé sans validation que s'il n'importe que des modules de la liste blanche
(calcul, texte, dates, formats de fichiers, tests) et n'appelle aucune fonction dangereuse. Sinon
l'agent demande la validation de l'utilisateur (action_sensitive_), avec la liste des raisons."""
import ast, re

MODULES_SURS = {
    "abc", "argparse", "array", "base64", "bisect", "calendar", "collections", "colorsys", "copy", "csv", "dataclasses",
    "datetime", "decimal", "difflib", "enum", "fractions", "functools", "hashlib", "heapq", "html", "io", "itertools", "json",
    "math", "numbers", "operator", "pathlib", "pprint", "random", "re", "statistics", "string", "struct", "textwrap", "time",
    "typing", "unicodedata", "unittest", "uuid", "zoneinfo", "xml", "zipfile", "gzip", "sqlite3", "secrets", "locale", "os", "sys",
}
APPELS_DANGEREUX = {"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr",
                    "breakpoint", "input"}
# toujours dangereux, quel que soit l'objet
ATTRIBUTS_DANGEREUX = {"system", "popen", "spawn", "spawnv", "startfile", "unlink", "rmdir", "rmtree", "chmod", "chown", "kill",
                       "fork", "execv", "execve", "symlink_to", "hardlink_to", "__subclasses__", "__globals__", "__builtins__",
                       "__code__", "__bases__", "__mro__"}
# dangereux sur os / shutil / un chemin (Path(...)), anodin ailleurs (str.replace, list.remove)
ATTRIBUTS_FICHIERS = {"remove", "rename", "replace", "link", "symlink", "removedirs", "renames", "move", "copy", "copyfile",
                      "copytree", "write_text", "write_bytes", "touch", "mkdir", "makedirs"}
RECEVEURS_FICHIERS = {"os", "shutil", "pathlib", "Path", "PurePath"}
# os et sys sont permis, mais seulement pour ces attributs (chemins, arguments, sorties standard)
PERMIS = {"os": {"path", "getcwd", "listdir", "scandir", "walk", "sep", "linesep", "environ", "getenv", "makedirs", "mkdir", "name"},
          "sys": {"argv", "exit", "stdin", "stdout", "stderr", "version", "version_info", "platform", "maxsize"}}


def analyser(code, nom="script.py", locaux=()):
    """Rend (raisons, imports). `raisons` vide = script sûr selon la liste blanche. `locaux` : modules du même dossier."""
    raisons, imports = [], set()
    try:
        arbre = ast.parse(code, filename=nom)
    except SyntaxError as err:
        return [f"{nom} : erreur de syntaxe ligne {err.lineno} ({err.msg})"], imports
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            for a in n.names:
                imports.add(a.name.split(".")[0])
                if a.asname and a.name.split(".")[0] in PERMIS and a.name != "os.path":
                    raisons.append(f"{nom}:{n.lineno} : import {a.name} as {a.asname} (alias non permis pour os et sys)")
        elif isinstance(n, ast.ImportFrom):
            if n.level == 0 and n.module:
                imports.add(n.module.split(".")[0])
                if n.module in PERMIS:
                    for a in n.names:
                        if a.name not in PERMIS[n.module]:
                            raisons.append(f"{nom}:{n.lineno} : from {n.module} import {a.name} hors des usages permis")
                elif n.module.split(".")[0] in PERMIS and n.module != "os.path":
                    raisons.append(f"{nom}:{n.lineno} : from {n.module} import … hors des usages permis")
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in APPELS_DANGEREUX:
                raisons.append(f"{nom}:{n.lineno} : appel à {f.id}()")
            if isinstance(f, ast.Attribute) and f.attr in ATTRIBUTS_DANGEREUX:
                raisons.append(f"{nom}:{n.lineno} : appel à .{f.attr}()")
            if isinstance(f, ast.Attribute) and f.attr in ATTRIBUTS_FICHIERS:
                v = f.value
                receveur = v.id if isinstance(v, ast.Name) else v.func.id if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) else ""
                if receveur in RECEVEURS_FICHIERS:
                    raisons.append(f"{nom}:{n.lineno} : opération sur des fichiers {receveur}.{f.attr}()")
            if isinstance(f, ast.Name) and f.id == "open" and n.args and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str) and (":" in n.args[0].value or n.args[0].value.startswith(("/", "\\", ".."))):
                raisons.append(f"{nom}:{n.lineno} : ouverture d'un fichier hors du dossier ({n.args[0].value})")
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in PERMIS and n.attr not in PERMIS[n.value.id]:
            raisons.append(f"{nom}:{n.lineno} : {n.value.id}.{n.attr} hors des usages permis")
        elif isinstance(n, ast.Attribute) and n.attr.startswith("__") and n.attr not in ("__init__", "__name__", "__doc__", "__dict__"):
            raisons.append(f"{nom}:{n.lineno} : accès à {n.attr}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and (
                n.value.startswith(("..\\", "../", "~")) or re.match(r"^[A-Za-z]:[\\/]|^\\\\|^/(etc|usr|home|Users)\b", n.value)):
            raisons.append(f"{nom}:{n.lineno} : chemin hors du dossier « {n.value[:60]} »")
    hors_liste = sorted(i for i in imports if i not in MODULES_SURS and i not in locaux)
    return raisons + [f"{nom} : module hors de la liste blanche « {i} »" for i in hors_liste], imports
