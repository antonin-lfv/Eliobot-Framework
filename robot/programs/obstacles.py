from .hardware import (
    setup_motors, setup_buzzer, setup_matrix, setup_obstacle_sensors,
    sleep_ms, now_ms
)

LED_COLOR = (87, 49, 150)

PROGRAM_NAME = "obstacles"


def run():
    print("Starting Obstacles Avoidance program...")

    # Setup hardware
    matrix = setup_matrix()
    buzzer = setup_buzzer()
    motors = setup_motors()
    obstacle_sensor = setup_obstacle_sensors()

    buzzer.sound_startup()

    # Etat pour gerer une manoeuvre en cours
    maneuver_until_ms = 0
    maneuver_action = None

    # Boucle principale
    while True:
        now = now_ms()

        # Si une manoeuvre est en cours, on attend sa fin
        if maneuver_action is not None:
            if now >= maneuver_until_ms:
                maneuver_action = None
                matrix.clear_matrix()
            else:
                sleep_ms(10)
                continue

        # Mode normal: avance + check obstacles
        matrix.set_matrix_logo(matrix.emotionConfused, LED_COLOR)
        motors.move_forward()

        if obstacle_sensor.get_obstacle(0):
            motors.motor_stop()
            buzzer.sound_bump()
            print("obstacle 0 detected")
            matrix.set_matrix_logo(matrix.arrowRight, LED_COLOR)
            motors.turn_in_place(direction="left")
            maneuver_action = "turn_left"
            maneuver_until_ms = now + 1000

        elif obstacle_sensor.get_obstacle(1):
            motors.motor_stop()
            buzzer.sound_bump()
            print("obstacle 1 detected")
            matrix.set_matrix_logo(matrix.arrowDown, LED_COLOR)
            motors.move_backward()
            motors.turn_in_place(direction="right")
            maneuver_action = "back_and_turn_right"
            maneuver_until_ms = now + 1000

        elif obstacle_sensor.get_obstacle(2):
            motors.motor_stop()
            buzzer.sound_bump()
            print("obstacle 2 detected")
            matrix.set_matrix_logo(matrix.arrowLeft, LED_COLOR)
            motors.turn_in_place(direction="right")
            maneuver_action = "turn_right"
            maneuver_until_ms = now + 1000

        elif obstacle_sensor.get_obstacle(3):
            motors.motor_stop()
            buzzer.sound_bump()
            print("obstacle 3 detected")
            matrix.set_matrix_logo(matrix.arrowUp, LED_COLOR)
            motors.move_forward()
            maneuver_action = "forward"
            maneuver_until_ms = now + 1000

        sleep_ms(10)
