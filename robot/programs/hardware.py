import time
import json
import board
import pwmio
import analogio
import digitalio
import pulseio

from elio import Motors, Buzzer, ObstacleSensor, EyesMatrix, LineSensor, IRRemote


# ============================================================
# SETUP HARDWARE
# ============================================================
_motor_outputs = []
_motors = None


def emergency_stop():
    """Freine les sorties déjà initialisées, même après un setup incomplet."""
    for output in _motor_outputs:
        try:
            output.duty_cycle = 65535
        except Exception as e:
            print("Impossible d'arrêter une sortie moteur:", e)


def setup_motors():
    """Initialise une seule instance, conservée pour l'arrêt d'urgence."""
    global _motors
    if _motors is None:
        if _motor_outputs:
            emergency_stop()
            raise RuntimeError("Initialisation moteur incomplète : redémarrer le robot")
        try:
            for pin in (board.IO36, board.IO38, board.IO35, board.IO37):
                _motor_outputs.append(pwmio.PWMOut(pin))
            vBatt_pin = analogio.AnalogIn(board.BATTERY)
            _motors = Motors(_motor_outputs[0], _motor_outputs[1],
                             _motor_outputs[2], _motor_outputs[3], vBatt_pin)
            emergency_stop()
        except BaseException:
            emergency_stop()
            raise
    return _motors


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
    try:
        with open('/config.json') as stream:
            calibration = json.load(stream)
            if not isinstance(calibration, dict):
                raise ValueError('Le fichier doit contenir un objet JSON')
            thresholds = calibration.get('obstacle_thresholds')
    except OSError:
        thresholds = None
    except ValueError as exc:
        print("Calibration obstacles illisible :", exc)
        thresholds = None
    try:
        return ObstacleSensor(obstacleInput, thresholds)
    except ValueError as exc:
        print("Calibration obstacles invalide, seuils par défaut :", exc)
        return ObstacleSensor(obstacleInput)
    # 0: avant gauche, 1: avant, 2: avant droit, 3: arriere


# === PINS CAPTEURS DE LIGNE ET IR ===
# À adapter selon le câblage de votre Eliobot
_LINE_SENSOR_PINS = [board.IO10, board.IO11, board.IO12, board.IO13, board.IO14]
_LINE_CMD_PIN = board.IO33   # LED infrarouge des capteurs de ligne
_IR_RECEIVER_PIN = board.IO9  # Récepteur IR télécommande


def setup_line_sensor(motors):
    """Initialise et retourne le capteur de ligne (5 capteurs).

    Args:
        motors: Instance Motors existante (obtenue via setup_motors()).
                La même instance doit être réutilisée pour éviter les conflits PWM.
    """
    line_inputs = [analogio.AnalogIn(pin) for pin in _LINE_SENSOR_PINS]
    line_cmd = digitalio.DigitalInOut(_LINE_CMD_PIN)
    line_cmd.direction = digitalio.Direction.OUTPUT
    return LineSensor(line_inputs, line_cmd, motors)


def setup_ir_remote():
    """Initialise et retourne le récepteur IR télécommande."""
    ir_pin = pulseio.PulseIn(_IR_RECEIVER_PIN, maxlen=120, idle_state=True)
    return IRRemote(ir_pin)


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
