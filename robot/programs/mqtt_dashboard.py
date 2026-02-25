import json
import os
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT

from .hardware import (
    setup_motors, setup_buzzer, setup_matrix, setup_obstacle_sensors,
    sleep_ms, now_ms, every_ms,
)
from elio import WiFiConnectivity

PROGRAM_NAME = "mqtt_dashboard"

# Couleurs LED par mode
LED_IDLE    = (50, 50, 50)     # Gris foncé : veille
LED_MANUAL  = (87, 49, 150)    # Violet : contrôle manuel
LED_EXPLORE = (0, 180, 80)     # Vert : exploration

# Exploration — vitesse et distance d'un pas
EXPLORE_SPEED = 60
STEP_CM       = 15
TURN_DEG      = 90

# Offsets de déplacement selon le heading : N=0, E=1, S=2, W=3
HEADING_DX = {0: 0, 1: 1, 2: 0, 3: -1}
HEADING_DY = {0: 1, 1: 0, 2: -1, 3: 0}


def run():
    print("Starting MQTT Dashboard program...")

    matrix  = setup_matrix()
    buzzer  = setup_buzzer()
    motors  = setup_motors()
    sensors = setup_obstacle_sensors()

    BROKER_IP = os.getenv("BROKER_IP")
    PORT      = int(os.getenv("PORT", 1883))
    SSID      = os.getenv("SSID")
    PASSWORD  = os.getenv("PASSWORD")

    buzzer.sound_startup()
    matrix.set_matrix_logo(matrix.emotionConfused, LED_IDLE)

    # ── WiFi ──────────────────────────────────────────────
    try:
        WiFiConnectivity.connect_and_setup(
            ssid=SSID, password=PASSWORD, hostname=None, buzzer=buzzer,
        )
    except Exception as e:
        print(f"WiFi failed: {e}")
        while True:
            sleep_ms(1000)

    # ── État global ────────────────────────────────────────
    # Accessible depuis les callbacks MQTT et la boucle principale.
    state = {
        # Mode courant
        "mode":        "idle",   # "idle" | "manual" | "exploration"

        # Mode manuel
        "manual_cmd":   None,    # dernière commande reçue
        "manual_until": 0,       # validité de la commande (ms) — dead-man's switch
        "manual_speed": 70,

        # State machine exploration
        "ex_state":    "check",  # "check" | "moving" | "turning_right" | "turning_left" | "uturn"
        "ex_until":    0,        # timestamp de fin d'action
        "ex_heading":  0,        # 0=N 1=E 2=S 3=W
        "ex_x":        0,
        "ex_y":        0,
        # Capteurs du dernier check (utilisés dans le step publié)
        "ex_front": False,
        "ex_left":  False,
        "ex_right": False,
        # Dernière action terminée (pour le log du dashboard)
        "ex_last_action": "start",
    }

    # ── Callbacks MQTT ─────────────────────────────────────

    def on_connected(client, userdata, flags, rc):
        print(f"MQTT connecté ({BROKER_IP}:{PORT})")
        client.subscribe("elio/command/#")
        matrix.set_matrix_logo(matrix.emotionHappy, LED_IDLE)
        buzzer.sound_blink()
        # Annoncer le mode initial
        client.publish("elio/telemetry/mode", state["mode"])

    def on_disconnected(client, userdata, rc):
        print("MQTT déconnecté — arrêt sécurité")
        motors.motor_stop()

    def on_message(client, topic, message):
        # ── Changement de mode ──
        if topic == "elio/command/mode":
            if message in ("idle", "manual", "exploration"):
                old = state["mode"]
                state["mode"] = message
                if message != old:
                    motors.motor_stop()
                    state["manual_cmd"]   = None
                    state["manual_until"] = 0
                    print(f"Mode: {old} → {message}")
                # Reset exploration si on y entre
                if message == "exploration":
                    state["ex_state"]       = "check"
                    state["ex_until"]       = 0
                    state["ex_last_action"] = "start"
                try:
                    client.publish("elio/telemetry/mode", message)
                except Exception:
                    pass

        # ── Commande manuelle ──
        elif topic == "elio/command/move" and state["mode"] == "manual":
            if message in ("forward", "backward", "left", "right", "stop"):
                state["manual_cmd"]   = message
                state["manual_until"] = now_ms() + 800  # valide 800ms (dead-man's switch)

        # ── Vitesse ──
        elif topic == "elio/command/speed":
            try:
                spd = int(message)
                if 0 <= spd <= 100:
                    state["manual_speed"] = spd
            except ValueError:
                pass

        # ── Reset carte d'exploration ──
        elif topic == "elio/command/reset_map":
            state["ex_x"]           = 0
            state["ex_y"]           = 0
            state["ex_heading"]     = 0
            state["ex_state"]       = "check"
            state["ex_until"]       = 0
            state["ex_last_action"] = "start"
            print("Carte réinitialisée")

    # ── Setup MQTT ─────────────────────────────────────────
    pool = socketpool.SocketPool(wifi.radio)
    mqtt_client = MQTT.MQTT(broker=BROKER_IP, port=PORT, socket_pool=pool,
                            socket_timeout=0.1)
    mqtt_client.on_connect    = on_connected
    mqtt_client.on_disconnect = on_disconnected
    mqtt_client.on_message    = on_message

    try:
        mqtt_client.connect()
    except Exception as e:
        print(f"MQTT connect failed: {e}")

    # ── Fonctions de comportement ──────────────────────────

    def publish_telemetry():
        try:
            if every_ms("batt", 5000):
                v = motors.get_battery_voltage()
                mqtt_client.publish("elio/telemetry/battery", f"{v:.2f}")

            if every_ms("obs", 400):
                obs = {
                    "left":  bool(sensors.get_obstacle(0)),
                    "front": bool(sensors.get_obstacle(1)),
                    "right": bool(sensors.get_obstacle(2)),
                    "back":  bool(sensors.get_obstacle(3)),
                }
                mqtt_client.publish("elio/telemetry/obstacles", json.dumps(obs))

        except Exception as e:
            print(f"Telemetry error: {e}")

    def publish_step(action: str):
        try:
            step = {
                "x":       state["ex_x"],
                "y":       state["ex_y"],
                "heading": state["ex_heading"],
                "action":  action,
                "front":   state["ex_front"],
                "left":    state["ex_left"],
                "right":   state["ex_right"],
            }
            mqtt_client.publish("elio/telemetry/step", json.dumps(step))
        except Exception as e:
            print(f"Step publish error: {e}")

    def handle_manual(now: int):
        """Mode manuel : exécute la commande reçue. Arrêt automatique si timeout."""
        cmd = state.get("manual_cmd")
        if cmd is None or now >= state["manual_until"]:
            motors.motor_stop()
            if every_ms("idle_expr_m", 2000):
                matrix.set_matrix_logo(matrix.emotionNeutral, LED_MANUAL)
            return

        spd = state["manual_speed"]
        if cmd == "forward":
            motors.move_forward(spd)
            matrix.set_matrix_logo(matrix.arrowUp, LED_MANUAL)
        elif cmd == "backward":
            motors.move_backward(spd)
            matrix.set_matrix_logo(matrix.arrowDown, LED_MANUAL)
        elif cmd == "left":
            motors.turn_in_place(spd, "left")
            matrix.set_matrix_logo(matrix.arrowLeft, LED_MANUAL)
        elif cmd == "right":
            motors.turn_in_place(spd, "right")
            matrix.set_matrix_logo(matrix.arrowRight, LED_MANUAL)
        elif cmd == "stop":
            motors.motor_stop()
            state["manual_cmd"] = None
            matrix.set_matrix_logo(matrix.emotionNeutral, LED_MANUAL)

    def exploration_tick(now: int):
        """
        State machine non-bloquante — règle de la main droite.

        États :
          check          → lire capteurs, publier step, lancer l'action
          turning_right  → attendre fin de rotation, puis passer en moving
          turning_left   → idem
          uturn          → demi-tour, retour à check
          moving         → attendre fin de déplacement, mettre à jour position
        """
        ex = state

        # Action en cours : attendre
        if now < ex["ex_until"]:
            return

        es = ex["ex_state"]

        # ── CHECK ────────────────────────────────────────
        if es == "check":
            front = bool(sensors.get_obstacle(1))
            left  = bool(sensors.get_obstacle(0))
            right = bool(sensors.get_obstacle(2))

            ex["ex_front"] = front
            ex["ex_left"]  = left
            ex["ex_right"] = right

            # Publier l'état courant
            publish_step(ex["ex_last_action"])

            # Calculer les durées de manœuvre en fonction de la batterie
            rps       = motors.repetition_per_second()
            gear      = motors.SPACE_BETWEEN_WHEELS / motors.WHEEL_DIAMETER
            move_ms   = int((STEP_CM / motors.DISTANCE_PER_REVOLUTION / rps) * 1000) + 100
            turn_ms   = int((TURN_DEG / (360.0 * rps)) * gear * 1000) + 100
            uturn_ms  = int((180.0    / (360.0 * rps)) * gear * 1000) + 100

            # Règle de la main droite
            if not right:
                motors.turn_right(EXPLORE_SPEED)
                ex["ex_state"]  = "turning_right"
                ex["ex_until"]  = now + turn_ms
                matrix.set_matrix_logo(matrix.arrowRight, LED_EXPLORE)

            elif not front:
                motors.move_forward(EXPLORE_SPEED)
                ex["ex_state"] = "moving"
                ex["ex_until"] = now + move_ms
                matrix.set_matrix_logo(matrix.arrowUp, LED_EXPLORE)

            elif not left:
                motors.turn_left(EXPLORE_SPEED)
                ex["ex_state"]  = "turning_left"
                ex["ex_until"]  = now + turn_ms
                matrix.set_matrix_logo(matrix.arrowLeft, LED_EXPLORE)

            else:
                # Impasse — demi-tour
                motors.turn_right(EXPLORE_SPEED)
                ex["ex_state"]  = "uturn"
                ex["ex_until"]  = now + uturn_ms
                matrix.set_matrix_logo(matrix.emotionAngry, LED_EXPLORE)
                buzzer.sound_bump()

        # ── TURNING RIGHT ─────────────────────────────────
        elif es == "turning_right":
            motors.motor_stop()
            ex["ex_heading"]     = (ex["ex_heading"] + 1) % 4
            ex["ex_last_action"] = "turned_right"
            # Avancer d'un pas dans la nouvelle direction
            rps    = motors.repetition_per_second()
            move_ms = int((STEP_CM / motors.DISTANCE_PER_REVOLUTION / rps) * 1000) + 100
            motors.move_forward(EXPLORE_SPEED)
            ex["ex_state"]  = "moving"
            ex["ex_until"]  = now + move_ms

        # ── TURNING LEFT ──────────────────────────────────
        elif es == "turning_left":
            motors.motor_stop()
            ex["ex_heading"]     = (ex["ex_heading"] + 3) % 4  # -1 mod 4
            ex["ex_last_action"] = "turned_left"
            rps    = motors.repetition_per_second()
            move_ms = int((STEP_CM / motors.DISTANCE_PER_REVOLUTION / rps) * 1000) + 100
            motors.move_forward(EXPLORE_SPEED)
            ex["ex_state"]  = "moving"
            ex["ex_until"]  = now + move_ms

        # ── UTURN ─────────────────────────────────────────
        elif es == "uturn":
            motors.motor_stop()
            ex["ex_heading"]     = (ex["ex_heading"] + 2) % 4
            ex["ex_last_action"] = "uturn"
            ex["ex_state"]       = "check"

        # ── MOVING ────────────────────────────────────────
        elif es == "moving":
            motors.motor_stop()
            h = ex["ex_heading"]
            ex["ex_x"]           += HEADING_DX[h]
            ex["ex_y"]           += HEADING_DY[h]
            ex["ex_last_action"]  = "moved_forward"
            ex["ex_state"]        = "check"

    # ── BOUCLE PRINCIPALE ─────────────────────────────────
    reconnect_wait = 1

    while True:
        now = now_ms()

        # MQTT loop (non-bloquant, 50ms max)
        try:
            mqtt_client.loop(timeout=0.1)
            reconnect_wait = 1
        except Exception as e:
            print(f"Loop error: {e}")
            motors.motor_stop()
            sleep_ms(reconnect_wait * 1000)
            try:
                mqtt_client.reconnect()
            except Exception:
                reconnect_wait = min(reconnect_wait * 2, 30)

        # Télémétrie périodique
        publish_telemetry()

        # ── Comportement par mode ──
        mode = state["mode"]

        if mode == "idle":
            if every_ms("idle_stop", 2000):
                motors.motor_stop()
            if every_ms("idle_expr", 6000):
                matrix.set_matrix_logo(matrix.emotionNeutral, LED_IDLE)

        elif mode == "manual":
            handle_manual(now)

        elif mode == "exploration":
            exploration_tick(now)

        sleep_ms(20)
