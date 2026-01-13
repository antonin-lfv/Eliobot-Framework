"""
Obstacles Avoidance Program - Autonomous navigation
Robot moves forward and avoids obstacles automatically
"""

import time
import board
import pwmio
import analogio

from .base import Program
from elio import Motors, Buzzer, ObstacleSensor, EyesMatrix

LED_COLOR = (87, 49, 150)

PROGRAM_NAME = "obstacles"


class ObstaclesAvoidance(Program):
    """Autonomous obstacle avoidance program."""

    def setup(self):
        print("🚗 Starting Obstacles Avoidance program...")

        # Initialisation Matériel
        self.matrix = EyesMatrix(board.IO2)
        self.buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))

        # Setup des moteurs
        AIN1 = pwmio.PWMOut(board.IO36)
        AIN2 = pwmio.PWMOut(board.IO38)
        BIN1 = pwmio.PWMOut(board.IO35)
        BIN2 = pwmio.PWMOut(board.IO37)
        vBatt_pin = analogio.AnalogIn(board.BATTERY)
        self.motors = Motors(AIN1, AIN2, BIN1, BIN2, vBatt_pin)

        # Setup capteurs d'obstacles
        obstacleInput = [analogio.AnalogIn(pin) for pin in (board.IO4, board.IO5, board.IO6, board.IO7)]
        self.obstacleSensor = ObstacleSensor(obstacleInput)
        # 0: avant gauche, 1: avant, 2: avant droit, 3: arrière

        self.buzzer.sound_startup()

        # Petit état interne pour gérer une "manœuvre" en cours
        self._maneuver_until_ms = 0
        self._maneuver_action = None  # str ou None

    def _start_maneuver(self, action: str, duration_ms: int):
        self._maneuver_action = action
        self._maneuver_until_ms = self.now_ms() + duration_ms

    def loop(self):
        now = self.now_ms()

        # Si une manœuvre est en cours, on attend sa fin
        if self._maneuver_action is not None:
            if now >= self._maneuver_until_ms:
                self._maneuver_action = None
                self.matrix.clear_matrix()
            else:
                self.sleep_ms(10)
                return

        # Mode normal : avance + check obstacles
        self.matrix.set_matrix_logo(self.matrix.emotionConfused, LED_COLOR)
        self.motors.move_forward()

        if self.obstacleSensor.get_obstacle(0):
            self.motors.motor_stop()
            self.buzzer.sound_bump()
            print("obstacle 0 detected")
            self.matrix.set_matrix_logo(self.matrix.arrowRight, LED_COLOR)
            self.motors.turn_in_place(direction="left")
            self._start_maneuver("turn_left", 1000)

        elif self.obstacleSensor.get_obstacle(1):
            self.motors.motor_stop()
            self.buzzer.sound_bump()
            print("obstacle 1 detected")
            self.matrix.set_matrix_logo(self.matrix.arrowDown, LED_COLOR)
            self.motors.move_backward()
            self.motors.turn_in_place(direction="right")
            self._start_maneuver("back_and_turn_right", 1000)

        elif self.obstacleSensor.get_obstacle(2):
            self.motors.motor_stop()
            self.buzzer.sound_bump()
            print("obstacle 2 detected")
            self.matrix.set_matrix_logo(self.matrix.arrowLeft, LED_COLOR)
            self.motors.turn_in_place(direction="right")
            self._start_maneuver("turn_right", 1000)

        elif self.obstacleSensor.get_obstacle(3):
            self.motors.motor_stop()
            self.buzzer.sound_bump()
            print("obstacle 3 detected")
            self.matrix.set_matrix_logo(self.matrix.arrowUp, LED_COLOR)
            self.motors.move_forward()
            self._start_maneuver("forward", 1000)

        # Respire
        self.sleep_ms(10)