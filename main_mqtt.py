import os
import wifi
import socketpool
import time
import board
import pwmio
import analogio
import adafruit_minimqtt.adafruit_minimqtt as MQTT

# --- Importations spécifiques Elio ---
from utils import *
from elio import Buzzer, ObstacleSensor, EyesMatrix

# --- Initialisation Matériel ---
matrix = EyesMatrix(board.IO2)
buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))
obstacleInput = [analogio.AnalogIn(pin) for pin in (board.IO4, board.IO5, board.IO6, board.IO7)]
obstacleSensor = ObstacleSensor(obstacleInput)

# --- Configuration Réseau & MQTT ---
SSID = os.getenv("SSID")
PASSWORD = os.getenv("PASSWORD")
BROKER_IP = os.getenv("BROKER_IP") # Ton Mac (.local)
PORT = int(os.getenv("PORT", 1883))

print(f"Connexion Wi-Fi...")
wifi.radio.tx_power = 8.5 

try:
    wifi.radio.connect(SSID, PASSWORD)
    print(f"✅ Wi-Fi OK (IP: {wifi.radio.ipv4_address})")
except Exception as e:
    print(f"❌ Erreur Wi-Fi: {e}")
    while True: pass

# --- Fonctions de Rappel MQTT (Callbacks) ---
def connected(client, userdata, flags, rc):
    print(f"✅ Connecté au Broker MQTT ({BROKER_IP})")
    # On s'abonne à un sujet pour recevoir des ordres
    client.subscribe("elio/commandes")

def disconnected(client, userdata, rc):
    print("⚠️ Déconnecté du Broker MQTT")

def message(client, topic, message):
    print(f"📩 Message reçu sur {topic} : {message}")
    
    # Logique de commande simple
    if message == "on":
        eye_matrix_t0, _ = get_eyes_matrices()
        matrix.set_matrix_colors(eye_matrix_t0)
    elif message == "off":
        matrix.clear_matrix()

# --- Setup MQTT ---
pool = socketpool.SocketPool(wifi.radio)
mqtt_client = MQTT.MQTT(
    broker=BROKER_IP,
    port=PORT,
    socket_pool=pool,
)

mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_message = message

print(f"Tentative de connexion MQTT...")
try:
    mqtt_client.connect()
except Exception as e:
    print(f"❌ Erreur MQTT: {e}")

# --- Boucle Principale ---
last_send_time = 0

while True:
    try:
        # Maintient la connexion et vérifie les nouveaux messages
        # timeout=0.1 permet de ne pas bloquer le reste du code
        mqtt_client.loop(timeout=0.1)

        # Exemple : Envoyer l'état du capteur toutes les 2 secondes
        if (time.monotonic() - last_send_time) > 2.0:
            obstacle = "OUI" if obstacleSensor.get_obstacle(1) else "NON"
            print(f"Envoi MQTT: obstacle/{obstacle}")
            mqtt_client.publish("elio/etat/obstacle", obstacle)
            last_send_time = time.monotonic()

    except Exception as e:
        print(f"Erreur boucle: {e}")
        try:
            mqtt_client.reconnect()
        except:
            pass
            
    time.sleep(0.01)