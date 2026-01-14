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
