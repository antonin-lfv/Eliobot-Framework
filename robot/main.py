"""
Eliobot Main Entry Point (Framework v1.1)
- Reads PROGRAM from settings.toml env (os.getenv)
- Auto-discovers programs in /programs
- Runs selected program
- Falls back to safe mode if invalid/crash
"""

import os
import time

from programs.registry import discover_programs


def _print_header(selected: str, programs: dict):
    print("=" * 50)
    print("🤖 ELIOBOT FRAMEWORK v1.1")
    print("=" * 50)
    print(f"Selected program: {selected}")
    print("-" * 50)
    if programs:
        print("Available programs:")
        for k in sorted(programs.keys()):
            print(" -", k)
    else:
        print("No programs discovered in /programs")
    print("-" * 50)


def _run_program(program_name: str, programs: dict) -> bool:
    """
    Returns True if program ran (never returns normally).
    Returns False if it couldn't start.
    """
    if program_name not in programs:
        print(f"❌ ERROR: Unknown program '{program_name}'")
        return False

    ProgramClass = programs[program_name]
    print(f"✅ Loading: {ProgramClass.__name__} ({program_name})")

    program = ProgramClass()
    program.run()
    return True


def main():
    # Discover programs
    programs = discover_programs()

    # Read selection
    program_name = os.getenv("PROGRAM", "web_server")

    _print_header(program_name, programs)

    # Try run selected; fallback to safe if invalid
    ok = _run_program(program_name, programs)
    if not ok:
        print("➡️  Falling back to 'safe' program")
        if "safe" in programs:
            _run_program("safe", programs)
        else:
            print("❌ No safe mode available. Stopping.")
            while True:
                time.sleep(1)

# Top-level execution
main()