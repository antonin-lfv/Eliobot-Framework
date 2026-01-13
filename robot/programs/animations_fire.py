"""
Animations Program
Simple demo program with LED animations
"""

import time
import board
import pwmio

from .base import Program
from utils import get_eyes_matrices
from elio import Buzzer, EyesMatrix


# Nom côté settings.toml
PROGRAM_NAME = "animations_fire"


class Animations(Program):
    """Simple LED animation program."""

    def setup(self):
        print("✨ Starting Animations program...")

        # Initialisation Matériel
        self.matrix = EyesMatrix(board.IO2)
        self.buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))

        self.buzzer.sound_startup()

        # State pour alterner
        self._toggle = False
        self._t0 = None
        self._t1 = None

    def loop(self):
        # Alterne les 2 matrices toutes les 500 ms
        if self.every_ms("blink", 500):
            if self._t0 is None:
                self._t0, self._t1 = get_eyes_matrices()

            if not self._toggle:
                self.matrix.set_matrix_colors(self._t0)
            else:
                self.matrix.set_matrix_colors(self._t1)

            self._toggle = not self._toggle

        # Laisse respirer la boucle
        self.sleep_ms(10)