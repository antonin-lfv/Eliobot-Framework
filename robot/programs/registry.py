"""
Programme registry & auto-discovery pour Eliobot.

Regle simple:
- Tout fichier .py dans programs/ (sauf __init__.py, registry.py, hardware.py)
- Qui definit une fonction run()
- Sera decouvert automatiquement

Le nom du programme = nom du fichier sans .py
Ou PROGRAM_NAME si defini explicitement dans le fichier.
"""

import os


_EXCLUDE = {"__init__.py", "registry.py", "hardware.py"}


def _is_program_file(filename):
    if not filename.endswith(".py"):
        return False
    if filename in _EXCLUDE:
        return False
    return True


def _module_name_from_file(filename):
    # "web_server.py" -> "programs.web_server"
    name = filename[:-3]
    return "programs." + name


def _default_program_name_from_file(filename):
    # "web_server.py" -> "web_server"
    return filename[:-3]


def discover_programs():
    """
    Retourne un dict: program_name -> fonction run()
    """
    programs = {}

    # CircuitPython-friendly directory listing
    try:
        filenames = os.listdir("programs")
    except OSError:
        filenames = os.listdir("/programs")

    for fn in filenames:
        if not _is_program_file(fn):
            continue

        module_name = _module_name_from_file(fn)
        default_name = _default_program_name_from_file(fn)

        try:
            mod = __import__(module_name, None, None, ["*"])
        except Exception as e:
            print(f"Program discovery: failed importing {module_name}: {e}")
            continue

        # Cherche une fonction run()
        if not hasattr(mod, "run"):
            continue

        run_func = getattr(mod, "run")
        if not callable(run_func):
            continue

        # Nom du programme: PROGRAM_NAME si defini, sinon nom du fichier
        name = getattr(mod, "PROGRAM_NAME", default_name)
        if not isinstance(name, str):
            name = default_name

        programs[name] = run_func

    return programs
