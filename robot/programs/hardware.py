import time
import board
import pwmio
import analogio

from elio import Motors, Buzzer, ObstacleSensor, EyesMatrix


# ============================================================
# SETUP HARDWARE
# ============================================================

def setup_motors():
    """Initialise et retourne les moteurs."""
    AIN1 = pwmio.PWMOut(board.IO36)
    AIN2 = pwmio.PWMOut(board.IO38)
    BIN1 = pwmio.PWMOut(board.IO35)
    BIN2 = pwmio.PWMOut(board.IO37)
    vBatt_pin = analogio.AnalogIn(board.BATTERY)
    return Motors(AIN1, AIN2, BIN1, BIN2, vBatt_pin)


def setup_buzzer():
    """Initialise et retourne le buzzer."""
    return Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))


def setup_matrix():
    """Initialise et retourne la matrice LED des yeux."""
    return EyesMatrix(board.IO2)


def setup_obstacle_sensors():
    """Initialise et retourne les capteurs d'obstacles."""
    pins = [board.IO4, board.IO5, board.IO6, board.IO7]
    obstacleInput = [analogio.AnalogIn(pin) for pin in pins]
    return ObstacleSensor(obstacleInput)
    # 0: avant gauche, 1: avant, 2: avant droit, 3: arriere


# ============================================================
# HELPERS
# ============================================================

def sleep_ms(ms):
    """Pause en millisecondes."""
    time.sleep(ms / 1000.0)


def now_ms():
    """Retourne le temps actuel en millisecondes."""
    return int(time.monotonic() * 1000)


# Timer simple pour executions periodiques
_timers = {}

def every_ms(name, period_ms):
    """
    Retourne True quand le timer nomme est echu.
    Utile pour executer du code periodiquement sans bloquer.

    Exemple:
        while True:
            if every_ms("check_sensors", 100):
                # Execute toutes les 100ms
                check_sensors()
            if every_ms("update_leds", 500):
                # Execute toutes les 500ms
                update_leds()
            sleep_ms(10)
    """
    t = now_ms()
    due = _timers.get(name)
    if due is None or t >= due:
        _timers[name] = t + period_ms
        return True
    return False
