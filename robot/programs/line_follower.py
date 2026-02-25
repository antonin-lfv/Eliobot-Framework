import json

from .hardware import (
    setup_motors, setup_buzzer, setup_matrix, setup_line_sensor,
    sleep_ms, every_ms
)

PROGRAM_NAME = "line_follower"

LED_CENTER   = (0, 200, 80)    # Vert : centré sur la ligne
LED_TURN     = (255, 150, 0)   # Orange : virage en cours
LED_LOST     = (200, 0, 0)     # Rouge : ligne perdue


def run():
    print("Starting Line Follower program...")

    matrix = setup_matrix()
    buzzer = setup_buzzer()
    motors = setup_motors()
    line_sensor = setup_line_sensor(motors)

    # Charger le threshold de calibration (config.json)
    try:
        with open("config.json") as f:
            config = json.load(f)
        threshold = config.get("line_threshold", 75000)
    except Exception:
        threshold = 75000
    print(f"Threshold: {threshold}")

    buzzer.sound_startup()
    matrix.set_matrix_logo(matrix.emotionHappy, LED_CENTER)

    last_state = None

    while True:
        # Lecture capteurs en court-circuit (du centre vers les bords)
        # Chaque get_line prend ~40ms (2 mesures x 20ms)
        if line_sensor.get_line(2) < threshold:
            state = "center"
        elif line_sensor.get_line(1) < threshold:
            state = "slight_left"
        elif line_sensor.get_line(0) < threshold:
            state = "far_left"
        elif line_sensor.get_line(3) < threshold:
            state = "slight_right"
        elif line_sensor.get_line(4) < threshold:
            state = "far_right"
        else:
            state = "lost"

        # === MOUVEMENT ===
        if state == "center":
            motors.move_forward(60)

        elif state == "slight_left":
            motors.motor_stop()
            motors.spin_right_wheel_forward(60)

        elif state == "far_left":
            motors.motor_stop()
            motors.spin_right_wheel_forward(60)
            sleep_ms(100)

        elif state == "slight_right":
            motors.motor_stop()
            motors.spin_left_wheel_forward(60)

        elif state == "far_right":
            motors.motor_stop()
            motors.spin_left_wheel_forward(60)
            sleep_ms(100)

        else:  # lost
            motors.motor_stop()

        # === EXPRESSION (mise à jour uniquement au changement d'état) ===
        if state != last_state:
            if state == "center":
                matrix.set_matrix_logo(matrix.emotionHappy, LED_CENTER)

            elif state in ("slight_left", "far_left"):
                matrix.set_matrix_logo(matrix.arrowLeft, LED_TURN)

            elif state in ("slight_right", "far_right"):
                matrix.set_matrix_logo(matrix.arrowRight, LED_TURN)

            else:  # lost
                matrix.set_matrix_logo(matrix.emotionConfused, LED_LOST)
                if every_ms("lost_sound", 2000):
                    buzzer.sound_question()

            last_state = state
