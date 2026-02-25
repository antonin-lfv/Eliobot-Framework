from .hardware import setup_motors, setup_buzzer, setup_matrix, sleep_ms

PROGRAM_NAME = "dance"

# Palette de couleurs
LED_GOLD   = (255, 180, 0)
LED_CYAN   = (0, 200, 255)
LED_RED    = (220, 30, 30)
LED_PURPLE = (130, 0, 255)
LED_GREEN  = (0, 200, 80)
LED_PINK   = (255, 0, 120)
LED_BLUE   = (0, 80, 255)


def _perform_dance(motors, buzzer, matrix):
    """Une chorégraphie complète (~25 secondes)."""

    # ============================================================
    # INTRO : réveil et annonce
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionClosedEyes, LED_GOLD)
    sleep_ms(600)
    matrix.set_matrix_logo(matrix.emotionOpenedEyes, LED_GOLD)
    sleep_ms(200)
    buzzer.sound_startup()
    matrix.set_matrix_logo(matrix.emotionAmazed, LED_GOLD)
    sleep_ms(800)

    # ============================================================
    # MOVE 1 : aller-retour x2 (bounce)
    # ============================================================
    for i in range(2):
        matrix.set_matrix_logo(matrix.arrowUp, LED_CYAN)
        buzzer.play_tone(660, 0.1, 80)
        motors.move_one_step("forward", 12)
        sleep_ms(80)

        matrix.set_matrix_logo(matrix.arrowDown, LED_CYAN)
        buzzer.play_tone(440, 0.1, 80)
        motors.move_one_step("backward", 12)
        sleep_ms(80)

    # ============================================================
    # MOVE 2 : shimmy (oscillation rapide gauche-droite)
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionHappy, LED_GREEN)
    buzzer.sound_happy()
    sleep_ms(300)

    for _ in range(4):
        motors.turn_one_step("left", 28)
        buzzer.play_tone(520, 0.05, 50)
        motors.turn_one_step("right", 28)
        buzzer.play_tone(520, 0.05, 50)

    # ============================================================
    # MOVE 3 : spin 360° avec son laser
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionDizzy, LED_RED)
    buzzer.sound_laser()
    motors.turn_one_step("left", 360)
    sleep_ms(100)

    # ============================================================
    # MOVE 4 : moonwalk (reculer par petits pas saccadés)
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionConfused, LED_PURPLE)
    notes = [300, 340, 380, 420]
    for freq in notes:
        motors.move_one_step("backward", 7)
        buzzer.play_tone(freq, 0.08, 70)
        sleep_ms(60)

    # ============================================================
    # MOVE 5 : spin inverse + son explosion
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionAngry, LED_RED)
    motors.turn_one_step("right", 360)
    buzzer.sound_explosion()
    sleep_ms(200)

    # ============================================================
    # FINALE : Marseillaise + expressions enchaînées
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionMusic, LED_BLUE)
    buzzer.melody_marseillaise()

    # ============================================================
    # OUTRO : révérence
    # ============================================================
    matrix.set_matrix_logo(matrix.emotionLove, LED_PINK)
    motors.move_one_step("forward", 5)
    sleep_ms(250)
    motors.move_one_step("backward", 5)

    buzzer.emotion_joie()
    matrix.set_matrix_logo(matrix.emotionHappy, LED_GOLD)
    sleep_ms(600)

    matrix.set_matrix_logo(matrix.emotionClosedEyes, LED_GOLD)
    sleep_ms(400)


def run():
    print("Starting Dance program...")

    matrix = setup_matrix()
    buzzer = setup_buzzer()
    motors = setup_motors()

    while True:
        _perform_dance(motors, buzzer, matrix)
        # Pause entre deux représentations
        matrix.clear_matrix()
        sleep_ms(4000)
