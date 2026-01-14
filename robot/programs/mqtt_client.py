import os
import wifi
import socketpool
import time
import adafruit_minimqtt.adafruit_minimqtt as MQTT

from .hardware import setup_buzzer, setup_matrix, setup_obstacle_sensors
from utils import get_eyes_matrices
from elio import WiFiConnectivity

PROGRAM_NAME = "mqtt_client"


def run():
    print("Starting MQTT Client program...")

    # Setup hardware
    matrix = setup_matrix()
    buzzer = setup_buzzer()
    obstacle_sensor = setup_obstacle_sensors()

    # Configuration MQTT
    BROKER_IP = os.getenv("BROKER_IP")
    PORT = int(os.getenv("PORT", 1883))

    # Setup WiFi
    SSID = os.getenv("SSID")
    PASSWORD = os.getenv("PASSWORD")

    try:
        success, ip, _ = WiFiConnectivity.connect_and_setup(
            ssid=SSID,
            password=PASSWORD,
            hostname=None,  # Pas de mDNS pour MQTT
            buzzer=buzzer
        )
    except Exception as e:
        print(f"WiFi setup failed: {e}")
        while True:
            pass

    # Callbacks MQTT
    def on_connected(client, userdata, flags, rc):
        print(f"Connecte au Broker MQTT ({BROKER_IP})")
        client.subscribe("elio/commandes")

    def on_disconnected(client, userdata, rc):
        print("Deconnecte du Broker MQTT")

    def on_message(client, topic, message):
        print(f"Message recu sur {topic}: {message}")

        if message == "on":
            eye_matrix_t0, _ = get_eyes_matrices()
            matrix.set_matrix_colors(eye_matrix_t0)
        elif message == "off":
            matrix.clear_matrix()

    # Setup MQTT client
    pool = socketpool.SocketPool(wifi.radio)
    mqtt_client = MQTT.MQTT(
        broker=BROKER_IP,
        port=PORT,
        socket_pool=pool,
    )

    mqtt_client.on_connect = on_connected
    mqtt_client.on_disconnect = on_disconnected
    mqtt_client.on_message = on_message

    print(f"Tentative de connexion MQTT vers {BROKER_IP}:{PORT}...")
    try:
        mqtt_client.connect()
    except Exception as e:
        print(f"Erreur MQTT: {e}")

    # Boucle principale
    last_send_time = 0

    while True:
        try:
            # Maintient la connexion et verifie les nouveaux messages
            mqtt_client.loop(timeout=0.1)

            # Envoyer l'etat du capteur toutes les 2 secondes
            if (time.monotonic() - last_send_time) > 2.0:
                obstacle = "OUI" if obstacle_sensor.get_obstacle(1) else "NON"
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
