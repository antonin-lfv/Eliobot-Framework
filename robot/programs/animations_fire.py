
from .hardware import setup_matrix, setup_buzzer, sleep_ms, every_ms
from utils import get_eyes_matrices

PROGRAM_NAME = "animations_fire"


def run():
    print("Starting Animations program...")

    # Setup hardware
    matrix = setup_matrix()
    buzzer = setup_buzzer()

    buzzer.sound_startup()

    # State
    toggle = False
    t0, t1 = None, None

    # Boucle principale
    while True:
        # Alterne les 2 matrices toutes les 500 ms
        if every_ms("blink", 500):
            if t0 is None:
                t0, t1 = get_eyes_matrices()

            if not toggle:
                matrix.set_matrix_colors(t0)
            else:
                matrix.set_matrix_colors(t1)

            toggle = not toggle

        sleep_ms(10)
