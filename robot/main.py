import os
import time

from programs.registry import discover_programs


def _print_header(selected, programs):
    print("=" * 50)
    print("ELIOBOT FRAMEWORK v1.2")
    print("=" * 50)
    print(f"Programme selectionne: {selected}")
    print("-" * 50)
    if programs:
        print("Programmes disponibles:")
        for k in sorted(programs.keys()):
            print(" -", k)
    else:
        print("Aucun programme trouve dans /programs")
    print("-" * 50)


def _run_program(program_name, programs):
    """
    Retourne True si le programme s'est lance (ne retourne jamais normalement).
    Retourne False s'il n'a pas pu demarrer.
    """
    if program_name not in programs:
        print(f"ERREUR: Programme inconnu '{program_name}'")
        return False

    run_func = programs[program_name]
    print(f"Chargement: {program_name}")

    run_func()
    return True


def main():
    # Decouvre les programmes
    programs = discover_programs()

    # Lit la selection
    program_name = os.getenv("PROGRAM", "web_server")

    _print_header(program_name, programs)

    # Execute le programme; fallback en safe si invalide
    ok = _run_program(program_name, programs)
    if not ok:
        print("Fallback vers 'safe'")
        if "safe" in programs:
            _run_program("safe", programs)
        else:
            print("Pas de safe mode. Arret.")
            while True:
                time.sleep(1)


main()
