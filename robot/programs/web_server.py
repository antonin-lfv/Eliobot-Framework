import os
import wifi
import socketpool
from adafruit_httpserver import Server, Request, FileResponse, Response

from .hardware import setup_motors, setup_buzzer, setup_matrix, sleep_ms
from utils import get_eyes_matrices
from elio import WiFiConnectivity

LED_COLOR = (87, 49, 150)

PIANO_NOTES = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
    "G4": 392.00, "A4": 440.00, "B4": 493.88, "C5": 523.25
}

PROGRAM_NAME = "web_server"


def run():
    print("Starting Web Server program...")

    # Setup hardware
    matrix = setup_matrix()
    buzzer = setup_buzzer()
    motors = setup_motors()
    matrix.clear_matrix()

    # Setup WiFi
    SSID = os.getenv("SSID")
    PASSWORD = os.getenv("PASSWORD")

    try:
        _, _, server_mdns = WiFiConnectivity.connect_and_setup(
            ssid=SSID,
            password=PASSWORD,
            hostname="elio",
            mdns_service_port=5000,
            buzzer=buzzer
        )
    except Exception as e:
        print(f"WiFi setup failed: {e}")
        raise

    # Setup serveur HTTP
    pool = socketpool.SocketPool(wifi.radio)
    server = Server(pool, "/www", debug=False)
    
    # Accessible via http://elio.local:5000

    # ============================================================
    # ROUTES
    # ============================================================

    @server.route("/")
    def base(request: Request):
        return FileResponse(request, "index.html", "/www")

    @server.route("/on", methods=["POST"])
    def eyes_on(request: Request):
        eye_matrix_t0, _ = get_eyes_matrices()
        matrix.set_matrix_colors(eye_matrix_t0)
        return Response(request, "OK")

    @server.route("/off", methods=["POST"])
    def eyes_off(request: Request):
        matrix.clear_matrix()
        return Response(request, "OK")

    @server.route("/sound", methods=["POST"])
    def play_sound(request: Request):
        name = request.query_params.get("name")
        print(f"WEB: Son demande -> {name}")

        if name == "laser": buzzer.sound_laser()
        elif name == "happy": buzzer.sound_happy()
        elif name == "win": buzzer.sound_win()
        elif name == "alert": buzzer.sound_alert()
        elif name == "jump": buzzer.sound_jump()
        elif name == "hello": buzzer.sound_hello()
        elif name == "startup": buzzer.sound_startup()
        elif name == "question": buzzer.sound_question()
        elif name == "error": buzzer.sound_error()
        elif name == "explosion": buzzer.sound_explosion()
        elif name == "land": buzzer.sound_land()
        elif name == "bump": buzzer.sound_bump()
        elif name == "blink": buzzer.sound_blink()
        elif name == "joie": buzzer.emotion_joie()
        elif name == "colere": buzzer.emotion_colere()
        elif name == "surprise": buzzer.emotion_surprise()
        elif name == "amour": buzzer.emotion_amour()
        elif name == "degout": buzzer.emotion_degoût()
        elif name == "confusion": buzzer.emotion_confusion()
        elif name == "reveur": buzzer.emotion_reveur()
        elif name == "detente": buzzer.emotion_detente()
        elif name == "peur": buzzer.melody_robot_peur()
        elif name == "hmm": buzzer.melody_hmm()
        elif name == "melody_alert": buzzer.melody_alert()
        elif name == "marseillaise": buzzer.melody_marseillaise()
        elif name == "endormi": buzzer.endormi()

        return Response(request, "OK")

    @server.route("/eye", methods=["POST"])
    def set_eye_expression(request: Request):
        emotion = request.query_params.get("type")
        print(f"WEB: Expression demandee -> {emotion}")

        if emotion == "happy":
            matrix.set_matrix_logo(matrix.emotionHappy, LED_COLOR)
        elif emotion == "love":
            matrix.set_matrix_logo(matrix.emotionLove, LED_COLOR)
        elif emotion == "angry":
            matrix.set_matrix_logo(matrix.emotionAngry, LED_COLOR)
        elif emotion == "amazed":
            matrix.set_matrix_logo(matrix.emotionAmazed, LED_COLOR)
        elif emotion == "music":
            matrix.set_matrix_logo(matrix.emotionMusic, LED_COLOR)
        elif emotion == "ko":
            matrix.set_matrix_logo(matrix.emotionKO, LED_COLOR)
        elif emotion == "dizzy":
            matrix.set_matrix_logo(matrix.emotionDizzy, LED_COLOR)
        elif emotion == "tired":
            matrix.set_matrix_logo(matrix.emotionTired, LED_COLOR)

        return Response(request, "Expression OK")

    @server.route("/piano", methods=["POST"])
    def play_piano(request: Request):
        note = request.query_params.get("note")
        print(f"WEB: Note de piano demandee -> {note}")
        if note in PIANO_NOTES:
            buzzer.play_tone(PIANO_NOTES[note], 0.2, 100)
        return Response(request, "Note jouee")

    @server.route("/move_step", methods=["POST"])
    def move_step(request: Request):
        direction = request.query_params.get("dir", "")
        value_str = request.query_params.get("value", "")

        default_value = 15 if direction in ("forward", "backward") else 25

        try:
            value = int(value_str) if value_str else default_value
        except Exception:
            value = default_value

        if direction in ("forward", "backward"):
            if value < 1: value = 1
            if value > 100: value = 100
        else:
            if value < 5: value = 5
            if value > 180: value = 180

        print(f"WEB: MOVE_STEP dir={direction} value={value}")

        if direction == "forward":
            motors.move_one_step("forward", distance=value)
        elif direction == "backward":
            motors.move_one_step("backward", distance=value)
        elif direction == "left":
            motors.turn_one_step("left", angle=value)
        elif direction == "right":
            motors.turn_one_step("right", angle=value)

        return Response(request, "OK")

    # ============================================================
    # DEMARRAGE SERVEUR
    # ============================================================

    server.start(str(wifi.radio.ipv4_address))
    print(f"Serveur actif sur http://{wifi.radio.ipv4_address}:5000")

    while True:
        try:
            server.poll()
        except Exception as e:
            print(f"Erreur serveur: {e}")

        sleep_ms(50)
