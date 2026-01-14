"""
Safe mode: diagnostics minimal, garde le robot en vie.
Pas de WiFi, pas de MQTT. Juste des prints pour debug.
"""

import time

PROGRAM_NAME = "safe"


def run():
    print("SAFE MODE")
    print("Le programme selectionne a crashe ou est invalide.")
    print("Branche-toi en REPL pour debug.")
    print("-" * 50)

    while True:
        print("SAFE: alive")
        time.sleep(2.0)
