import os
import time
import sys

from programs.registry import discover_programs


def _stop_hardware():
    # Ne charge pas de dépendances matérielles si le programme n'en a pas utilisé.
    hardware = sys.modules.get("programs.hardware")
    if hardware is not None:
        hardware.emergency_stop()


def _print_header(selected, programs):
    print("=" * 50)
    print("ELIOBOT FRAMEWORK v1.3")
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
    Retourne True si le programme s'est lance sans erreur.
    Retourne False s'il est introuvable ou s'il crashe au demarrage/en execution.
    """
    if program_name not in programs:
        print(f"ERREUR: Programme inconnu '{program_name}'")
        return False

    run_func = programs[program_name]
    print(f"Chargement: {program_name}")

    try:
        run_func()
        return True
    except Exception as e:
        print(f"ERREUR: Programme '{program_name}' crashe: {e}")
        return False
    finally:
        # Également exécuté lors d'un retour normal ou d'une interruption REPL.
        _stop_hardware()


def _run_safe_mode(programs):
    print("Fallback vers 'safe_mode'")
    if "safe_mode" in programs:
        _run_program("safe_mode", programs)
    else:
        print("Pas de safe mode. Arret.")
        while True:
            time.sleep(1)


def main():
    # Decouvre les programmes
    programs = discover_programs()

    # Lit la selection
    program_name = os.getenv("PROGRAM", "web_server")

    _print_header(program_name, programs)

    # Execute le programme; fallback en safe mode si invalide ou crash
    ok = _run_program(program_name, programs)
    if not ok:
        _run_safe_mode(programs)


main()
