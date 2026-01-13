"""
Safe mode program: minimal diagnostics & keep robot alive.
No WiFi, no MQTT. Just prints and does not brick boot.
"""

import time
from .base import Program

PROGRAM_NAME = "safe"


class SafeMode(Program):
    def setup(self):
        print("🛟 SAFE MODE")
        print("Le programme sélectionné a crashé ou est invalide.")
        print("➡️  Branche-toi en REPL pour debug et redeploy.")
        print("-" * 50)

    def loop(self):
        # Heartbeat minimal
        print("SAFE: alive")
        time.sleep(2.0)


# Explicit mapping (optional; registry can also find Program subclass automatically)
PROGRAM_CLASS = SafeMode