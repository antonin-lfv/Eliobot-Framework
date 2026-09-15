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


def _lazy_runner(module_name):
    def run():
        mod = __import__(module_name, None, None, ["*"])
        run_func = getattr(mod, "run", None)
        if not callable(run_func):
            raise ValueError("Programme sans fonction run(): " + module_name)
        return run_func()
    return run


def _declared_name(path, default_name):
    """Lit un alias littéral sans importer ni exécuter le programme."""
    try:
        with open(path) as source:
            for line in source:
                if not line.startswith("PROGRAM_NAME"):
                    continue
                key, separator, value = line.partition("=")
                if separator and key.strip() == "PROGRAM_NAME":
                    value = value.strip()
                    if value and value[0] in ("'", '"'):
                        end = value.find(value[0], 1)
                        if end > 1:
                            return value[1:end]
    except OSError as e:
        print("Program discovery:", e)
    return default_name


def discover_programs():
    """Retourne des lanceurs ; seul le programme choisi sera importé.

    PROGRAM_NAME peut être un alias littéral déclaré au niveau du module.
    Sans alias, le nom du fichier sert de nom de programme.
    """
    programs = {}
    directory = "programs"
    try:
        filenames = os.listdir(directory)
    except OSError:
        directory = "/programs"
        filenames = os.listdir(directory)

    for fn in sorted(filenames):
        if not _is_program_file(fn):
            continue
        name = _declared_name(directory + "/" + fn,
                              _default_program_name_from_file(fn))
        if name in programs:
            print("Program discovery: nom dupliqué ignoré:", name, fn)
            continue
        programs[name] = _lazy_runner(_module_name_from_file(fn))
    return programs
