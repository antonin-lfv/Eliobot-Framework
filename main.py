import os
import wifi
import socketpool
import time
import mdns
import board
import pwmio
import analogio
from adafruit_httpserver import Server, Request, FileResponse, Response

# --- Importations spécifiques Elio ---
from utils import *
from elio import Buzzer, EyesMatrix, Motors

LED_COLOR = (87, 49, 150)

# Fréquences musicales (en Hz)
PIANO_NOTES = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
    "G4": 392.00, "A4": 440.00, "B4": 493.88, "C5": 523.25
}

# --- Initialisation Matériel ---
matrix = EyesMatrix(board.IO2)
buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))
matrix.clear_matrix()

# ----- setup des moteurs
AIN1 = pwmio.PWMOut(board.IO36)
AIN2 = pwmio.PWMOut(board.IO38)
BIN1 = pwmio.PWMOut(board.IO35)
BIN2 = pwmio.PWMOut(board.IO37)
vBatt_pin = analogio.AnalogIn(board.BATTERY)
motors = Motors(AIN1, AIN2, BIN1, BIN2, vBatt_pin)

# --- Configuration Réseau ---
SSID = os.getenv("SSID")
PASSWORD = os.getenv("PASSWORD")

print(f"Connexion Wi-Fi à {SSID}...")
wifi.radio.tx_power = 8.5 

try:
    wifi.radio.connect(SSID, PASSWORD)
    print("✅ Wi-Fi connecté ! IP:", wifi.radio.ipv4_address)
    
    server_mdns = mdns.Server(wifi.radio)
    server_mdns.hostname = "elio" # Pour accéder via elio.local et non via l'IP qui est dynamique
    server_mdns.advertise_service(service_type="_http", protocol="_tcp", port=5000)

    print("Robot accessible sur http://elio.local:5000")
    
    buzzer.sound_startup()
except Exception as e:
    print(f"❌ Erreur Wi-Fi: {e}")
    buzzer.sound_error()
    while True: pass

# --- Configuration Serveur Web ---
pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, "/www", debug=False)

@server.route("/")
def base(request: Request):
    """Sert la page HTML principale"""
    return FileResponse(request, "index.html", "/www")

# Route pour les Yeux ON
@server.route("/on", methods=['POST'])
def eyes_on(request: Request):
    eye_matrix_t0, _ = get_eyes_matrices()
    matrix.set_matrix_colors(eye_matrix_t0)
    return Response(request, "OK")

# Route pour les Yeux OFF
@server.route("/off", methods=['POST'])
def eyes_off(request: Request):
    matrix.clear_matrix()
    return Response(request, "OK")

# Route générique pour les Sons
@server.route("/sound", methods=['POST'])
def play_sound(request: Request):
    name = request.query_params.get("name")
    if name == "laser": buzzer.sound_laser()
    elif name == "happy": buzzer.sound_happy()
    elif name == "win": buzzer.sound_win()
    elif name == "alert": buzzer.sound_alert()
    elif name == "jump": buzzer.sound_jump()
    elif name == "hello": buzzer.sound_hello()
    elif name == "startup": buzzer.sound_startup()
    return Response(request, "OK")

@server.route("/eye", methods=['POST'])
def set_eye_expression(request: Request):
    # On récupère le type d'émotion
    emotion = request.query_params.get("type")
    print(f"WEB: Expression demandée -> {emotion}")

    # On fait le lien entre le nom reçu et l'attribut de l'objet matrix
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

@server.route("/piano", methods=['POST'])
def play_piano(request: Request):
    note = request.query_params.get("note")
    print(f"WEB: Note de piano demandée -> {note}")
    if note in PIANO_NOTES:
        print(f"Piano: {note}")
        # On joue la note pendant 0.2 seconde à volume 100
        buzzer.play_tone(PIANO_NOTES[note], 0.2, 100)
    return Response(request, "Note jouée")

@server.route("/move_step", methods=["POST"])
def move_step(request: Request):
    """
    Déplacement 'one-shot' : le robot bouge puis s'arrête tout seul.
    - forward/backward : distance en cm
    - left/right : angle en degrés
    """
    direction = request.query_params.get("dir", "")
    value_str = request.query_params.get("value", "")

    # Valeurs par défaut (évite de bloquer si l’UI n’envoie rien)
    if direction in ("forward", "backward"):
        default_value = 15  # cm
    else:
        default_value = 25  # degrés

    try:
        value = int(value_str) if value_str else default_value
    except:
        value = default_value

    # Clamp raisonnable
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

# Démarrage sans blocage
server.start(str(wifi.radio.ipv4_address))
print(f"🌐 Serveur actif sur http://{wifi.radio.ipv4_address}:5000")

# --- Boucle Principale ---
while True:
    try:
        # On vérifie uniquement s'il y a un clic sur un bouton
        server.poll()
        
        # if obstacleSensor.get_obstacle(1):
            # Si un obstacle est détecté, on éteint tout par sécurité 
            # ou on fait reculer le robot
            # matrix.clear_matrix()
            # buzzer.beep(0.1) # Optionnel : petit bip d'alerte
            
    except Exception as e:
        print(f"Erreur : {e}")
    
    # On garde un petit sleep pour la stabilité WiFi
    time.sleep(0.1)
    