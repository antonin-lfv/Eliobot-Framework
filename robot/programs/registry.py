"""
Program registry & auto-discovery for Eliobot.

Rule:
- any file in programs/ ending with .py (excluding __init__.py, base.py, registry.py)
- that defines either:
    A) PROGRAM_NAME (str) and PROGRAM_CLASS (class)
  or
    B) a class inheriting Program, and optionally PROGRAM_NAME
will be discoverable.

This avoids editing main.py and programs/__init__.py every time.
"""

import os

from .base import Program


_EXCLUDE = {"__init__.py", "base.py", "registry.py"}


def _is_program_file(filename: str) -> bool:
    if not filename.endswith(".py"):
        return False
    if filename in _EXCLUDE:
        return False
    return True


def _module_name_from_file(filename: str) -> str:
    # "web_server.py" -> "programs.web_server"
    name = filename[:-3]
    return "programs." + name


def _default_program_name_from_file(filename: str) -> str:
    # "web_server.py" -> "web_server"
    return filename[:-3]


def discover_programs():
    """
    Returns dict: program_name -> ProgramClass
    """
    programs = {}

    # CircuitPython-friendly directory listing
    try:
        filenames = os.listdir("programs")
    except OSError:
        # If working dir differs, try absolute-ish
        filenames = os.listdir("/programs")

    for fn in filenames:
        if not _is_program_file(fn):
            continue

        module_name = _module_name_from_file(fn)
        default_name = _default_program_name_from_file(fn)

        try:
            mod = __import__(module_name, None, None, ["*"])
        except Exception as e:
            # Don't kill boot if one module fails to import
            print(f"⚠️  Program discovery: failed importing {module_name}: {e}")
            continue

        # Strategy A: explicit declaration
        if hasattr(mod, "PROGRAM_NAME") and hasattr(mod, "PROGRAM_CLASS"):
            name = getattr(mod, "PROGRAM_NAME")
            cls = getattr(mod, "PROGRAM_CLASS")
            if isinstance(name, str) and isinstance(cls, type):
                programs[name] = cls
                continue

        # Strategy B: find first Program subclass
        chosen_cls = None
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if isinstance(obj, type) and issubclass(obj, Program) and obj is not Program:
                chosen_cls = obj
                break

        if chosen_cls is None:
            continue

        name = getattr(mod, "PROGRAM_NAME", default_name)
        if not isinstance(name, str):
            name = default_name

        programs[name] = chosen_cls

    return programs