"""
MQTT Client Program - Control Eliobot via MQTT broker
Subscribes to: elio/commandes
Publishes to: elio/etat/obstacle
"""

import os
import wifi
import socketpool
import time
import board
import pwmio
import analogio
import adafruit_minimqtt.adafruit_minimqtt as MQTT

from .base import Program
from utils import get_eyes_matrices
from elio import Buzzer, ObstacleSensor, EyesMatrix, WiFiConnectivity


class MQTTClient(Program):
    """MQTT client program for remote control via MQTT broker."""

    def __init__(self):
        super().__init__()

        # Initialisation Matériel
        self.matrix = EyesMatrix(board.IO2)
        self.buzzer = Buzzer(pwmio.PWMOut(board.IO17, variable_frequency=True))
        obstacleInput = [analogio.AnalogIn(pin) for pin in (board.IO4, board.IO5, board.IO6, board.IO7)]
        self.obstacleSensor = ObstacleSensor(obstacleInput)

        # Configuration MQTT
        self.BROKER_IP = os.getenv("BROKER_IP")
        self.PORT = int(os.getenv("PORT", 1883))

    def setup_wifi(self):
        """Configure WiFi connection."""
        SSID = os.getenv("SSID")
        PASSWORD = os.getenv("PASSWORD")

        try:
            success, ip, _ = WiFiConnectivity.connect_and_setup(
                ssid=SSID,
                password=PASSWORD,
                hostname=None,  # Pas de mDNS pour MQTT
                buzzer=self.buzzer
            )
            return ip
        except Exception as e:
            print(f"WiFi setup failed: {e}")
            while True: pass

    def on_connected(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        print(f"✅ Connecté au Broker MQTT ({self.BROKER_IP})")
        client.subscribe("elio/commandes")

    def on_disconnected(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker."""
        print("⚠️ Déconnecté du Broker MQTT")

    def on_message(self, client, topic, message):
        """Callback when a message is received."""
        print(f"📩 Message reçu sur {topic} : {message}")

        # Logique de commande
        if message == "on":
            eye_matrix_t0, _ = get_eyes_matrices()
            self.matrix.set_matrix_colors(eye_matrix_t0)
        elif message == "off":
            self.matrix.clear_matrix()

    def run(self):
        """Main program loop."""
        print("📡 Starting MQTT Client program...")

        # Setup WiFi
        ip = self.setup_wifi()

        # Setup MQTT
        pool = socketpool.SocketPool(wifi.radio)
        mqtt_client = MQTT.MQTT(
            broker=self.BROKER_IP,
            port=self.PORT,
            socket_pool=pool,
        )

        mqtt_client.on_connect = self.on_connected
        mqtt_client.on_disconnect = self.on_disconnected
        mqtt_client.on_message = self.on_message

        print(f"Tentative de connexion MQTT vers {self.BROKER_IP}:{self.PORT}...")
        try:
            mqtt_client.connect()
        except Exception as e:
            print(f"❌ Erreur MQTT: {e}")

        # Boucle principale
        last_send_time = 0

        while True:
            try:
                # Maintient la connexion et vérifie les nouveaux messages
                mqtt_client.loop(timeout=0.1)

                # Envoyer l'état du capteur toutes les 2 secondes
                if (time.monotonic() - last_send_time) > 2.0:
                    obstacle = "OUI" if self.obstacleSensor.get_obstacle(1) else "NON"
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
