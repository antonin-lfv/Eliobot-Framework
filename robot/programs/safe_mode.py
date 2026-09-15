import time
import sys

PROGRAM_NAME = "safe_mode"


def run():
    hardware = sys.modules.get("programs.hardware")
    if hardware is not None:
        hardware.emergency_stop()
    print("SAFE MODE")
    print("Le programme selectionne a crashe ou est invalide.")
    print("Branche-toi en REPL pour debug.")
    print("-" * 50)

    while True:
        print("SAFE: alive")
        time.sleep(2.0)
