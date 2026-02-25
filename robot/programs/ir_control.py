from elio import IRRemote

from .hardware import (
    setup_motors, setup_buzzer, setup_matrix, setup_ir_remote,
    sleep_ms
)

PROGRAM_NAME = "ir_control"

SPEED = 70
LED_MOVE    = (87, 49, 150)    # Violet : déplacement
LED_NEUTRAL = (60, 60, 60)     # Gris : en attente

# Mapping boutons → (émotion visuelle, son, couleur)
EMOTION_MAP = {
    'signal_1': (lambda m: m.emotionHappy,   lambda b: b.emotion_joie(),      (0, 220, 80)),
    'signal_2': (lambda m: m.emotionAngry,   lambda b: b.emotion_colere(),    (220, 0, 0)),
    'signal_3': (lambda m: m.emotionAmazed,  lambda b: b.emotion_surprise(),  (255, 200, 0)),
    'signal_4': (lambda m: m.emotionLove,    lambda b: b.emotion_amour(),     (255, 0, 100)),
    'signal_5': (lambda m: m.emotionDizzy,   lambda b: b.sound_laser(),       (0, 100, 255)),
    'signal_6': (lambda m: m.emotionSad,     lambda b: b.melody_hmm(),        (0, 80, 180)),
    'signal_7': (lambda m: m.emotionKO,      lambda b: b.sound_explosion(),   (255, 80, 0)),
    'signal_8': (lambda m: m.emotionMusic,   lambda b: b.melody_marseillaise(), (0, 50, 255)),
    'signal_9': (lambda m: m.emotionTired,   lambda b: b.endormi(),           (40, 40, 100)),
}


def run():
    print("Starting IR Control program...")

    matrix = setup_matrix()
    buzzer = setup_buzzer()
    motors = setup_motors()
    ir = setup_ir_remote()

    buzzer.sound_startup()
    matrix.set_matrix_logo(matrix.emotionNeutral, LED_NEUTRAL)

    while True:
        try:
            signal = ir.decode_signal()
        except Exception:
            sleep_ms(50)
            continue

        if signal is None:
            sleep_ms(10)
            continue

        code = tuple(signal)

        # === DÉPLACEMENTS (maintient le moteur en marche) ===
        if code == IRRemote.signals['signal_up']:
            motors.move_forward(SPEED)
            matrix.set_matrix_logo(matrix.arrowUp, LED_MOVE)

        elif code == IRRemote.signals['signal_down']:
            motors.move_backward(SPEED)
            matrix.set_matrix_logo(matrix.arrowDown, LED_MOVE)

        elif code == IRRemote.signals['signal_left']:
            motors.turn_in_place(SPEED, "left")
            matrix.set_matrix_logo(matrix.arrowLeft, LED_MOVE)

        elif code == IRRemote.signals['signal_right']:
            motors.turn_in_place(SPEED, "right")
            matrix.set_matrix_logo(matrix.arrowRight, LED_MOVE)

        # === STOP ===
        elif code == IRRemote.signals['signal_ok']:
            motors.motor_stop()
            matrix.set_matrix_logo(matrix.emotionNeutral, LED_NEUTRAL)

        # === ÉMOTIONS (boutons 1-9) ===
        else:
            for key, (get_emotion, play_sound, color) in EMOTION_MAP.items():
                if code == IRRemote.signals.get(key):
                    motors.motor_stop()
                    matrix.set_matrix_logo(get_emotion(matrix), color)
                    play_sound(buzzer)
                    break

        sleep_ms(20)
